from __future__ import annotations

from datetime import UTC, datetime

import pytest

from api import catalog
from api.contract import Cutouts, Discovery
from api.conventions import (
    assign_tess_ids,
    flare_id,
    normalize_rubin,
    period_match_error,
)
from api.storage.sqlite import SqliteStorage

TIC = 1234
T = datetime(2026, 9, 1, tzinfo=UTC)


def d(did: str, source="tess", **raw) -> Discovery:
    return Discovery(
        id=did,
        type="planet_candidate",
        confidence=0.5,
        source=source,
        origin="test",
        ra_deg=1,
        dec_deg=1,
        detected_at=T,
        known_status="unchecked",
        cutouts=Cutouts(),
        explanation="Best guess.",
        raw=raw,
    )


@pytest.mark.parametrize(
    ("new", "old", "match"),
    [
        (10.0, 10.0, True),
        (10.09, 10.0, True),
        (9.91, 10.0, True),
        (10.2, 10.0, False),
        (20.1, 10.0, True),  # 2x alias
        (5.04, 10.0, True),  # 1/2 alias
        (30.2, 10.0, True),  # 3x alias
        (3.34, 10.0, True),  # 1/3 alias
        (15.0, 10.0, False),  # 3/2 is not a clean alias
        (40.0, 10.0, False),
    ],
)
def test_period_matching(new, old, match):
    assert (period_match_error(new, old) is not None) == match


def test_signals_match_existing_or_get_next_number():
    existing = [d(f"tess:{TIC}:sig:1", period_days=3.0), d(f"tess:{TIC}:sig:2", period_days=11.0)]
    found = [
        d(f"tess:{TIC}:sig:1", period_days=11.05),  # matches sig:2
        d(f"tess:{TIC}:sig:2", period_days=7.0),  # new
        d(f"tess:{TIC}:sig:3", period_days=6.01),  # 2x alias of sig:1
    ]
    final, rejected = assign_tess_ids(TIC, found, existing)
    assert [x.id for x in final] == [
        f"tess:{TIC}:sig:2",
        f"tess:{TIC}:sig:3",
        f"tess:{TIC}:sig:1",
    ]
    assert rejected == []


def test_two_results_for_one_signal_keep_the_closer():
    existing = [d(f"tess:{TIC}:sig:1", period_days=5.0)]
    found = [
        d(f"tess:{TIC}:sig:1", period_days=5.04),
        d(f"tess:{TIC}:sig:2", period_days=5.001),
    ]
    final, rejected = assign_tess_ids(TIC, found, existing)
    assert [(x.id, x.raw["period_days"]) for x in final] == [(f"tess:{TIC}:sig:1", 5.001)]
    assert rejected == [f"tess:{TIC}:sig:1"]


def test_first_hunt_numbers_from_one():
    found = [d(f"tess:{TIC}:sig:7", period_days=2.0), d(f"tess:{TIC}:sig:9", period_days=4.5)]
    final, _ = assign_tess_ids(TIC, found, [])
    assert [x.id for x in final] == [f"tess:{TIC}:sig:1", f"tess:{TIC}:sig:2"]


def test_flare_ids_from_peak_time():
    assert flare_id(TIC, 2345.6749) == f"tess:{TIC}:flare:2345.67"
    assert flare_id(TIC, 2345.6) == f"tess:{TIC}:flare:2345.60"
    found = [d(f"tess:{TIC}:flare:whatever", peak_btjd=2345.6751)]
    final, _ = assign_tess_ids(TIC, found, [])
    assert final[0].id == f"tess:{TIC}:flare:2345.68"


def test_bad_tess_results_rejected():
    found = [
        d(f"tess:{TIC}:sig:1"),  # no period
        d(f"tess:{TIC}:flare:1"),  # no peak
        d("tess:999:sig:1", period_days=1.0),  # other star
        d(f"tess:{TIC}:sig:1", source="rubin", period_days=1.0),
        d(f"tic{TIC}-1", period_days=1.0),
    ]
    final, rejected = assign_tess_ids(TIC, found, [])
    assert final == [] and len(rejected) == 5


def test_rubin_ids():
    ok = [d("rubin:obj:123", source="rubin"), d("rubin:ss:abc_1", source="rubin")]
    bad = [d("rubin:alert:1", source="rubin"), d("rubin:obj:", source="rubin"), d("rubin:obj:1")]
    kept, rejected = normalize_rubin(ok + bad)
    assert kept == ok and len(rejected) == 3


def test_ingest_update_rules():
    storage = SqliteStorage()
    first = d("rubin:obj:1", source="rubin", mag=19)
    r = catalog.ingest(storage, "p", None, [first], T)
    assert (r.created, r.new_catches) == (1, 1)

    same = first.model_copy(update={"detected_at": datetime(2026, 9, 5, tzinfo=UTC)})
    r = catalog.ingest(storage, "p", None, [same], datetime(2026, 9, 6, tzinfo=UTC))
    assert (r.created, r.updated, r.new_catches) == (0, 0, 0)
    assert "updated_at" not in storage.get_discovery("rubin:obj:1").raw

    changed = first.model_copy(update={"raw": {"mag": 18}})
    later = datetime(2026, 9, 7, tzinfo=UTC)
    r = catalog.ingest(storage, "q", None, [changed], later)
    assert (r.updated, r.new_catches) == (1, 1)
    stored = storage.get_discovery("rubin:obj:1")
    assert stored.raw == {"mag": 18, "updated_at": later.isoformat(timespec="microseconds")}
    assert stored.detected_at == T

    # Re-sending the same update writes nothing, including updated_at.
    r = catalog.ingest(storage, "q", None, [changed], datetime(2026, 9, 8, tzinfo=UTC))
    assert r.updated == 0
    assert storage.get_discovery("rubin:obj:1").raw["updated_at"] == later.isoformat(
        timespec="microseconds"
    )

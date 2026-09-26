"""Planet finder: ingest, re-check dismissal, pixel vets, votes, list/detail, funnel, sensitivity,
admin export. Every storage-touching test runs on SQLite and Postgres."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from api import finder_ingest, honesty
from api.fakes.finder import FakeKnownLists, FakePixelVetter
from api.finder import known_match
from api.finder_export import COLUMNS
from api.ports import KnownMatch

TIC_A, TIC_B, TIC_C = 150428135, 283722336, 71268730
C = "/finder/candidates"
KEY = "voter-key-aaaaaaaaaaaaaaaa"
KEY2 = "voter-key-bbbbbbbbbbbbbbbb"


def candidate(tic: int, n: int = 1, **over) -> dict:
    rec = {
        "tic": tic,
        "period_d": 3.5 + n,
        "t0_btjd": 2100.25,
        "duration_h": 2.4,
        "depth_ppm": 850.0,
        "snr": 11.3,
        "sde": 14.2,
        "n_transits": 7,
        "sectors": [14, 15],
        "radius_rjup": 0.42,
        "radius_low": 0.38,
        "radius_high": 0.47,
        "checks": [{"name": "odd_even", "value": 0.4, "passed": True, "reason": "odd and even"
                    " transits have the same depth"}],
        "score": 0.5,
        "score_parts": {"snr": 0.3, "shape": 0.2},
        "known_lists": [],
        "folded": {"phase": [-0.1, 0.0, 0.1], "flux": [1.0, 0.9991, 1.0]},
        "unfolded": {"time_btjd": [2100.0, 2100.5], "flux": [1.0, 1.0]},
        "created_at": "2026-09-25T02:00:00Z",
    }  # fmt: skip
    rec.update(over)
    return rec


def write(folder: Path, tic: int, n: int = 1, **over) -> dict:
    rec = candidate(tic, n, **over)
    (folder / f"{tic}_{n}.json").write_text(json.dumps(rec))
    return rec


@pytest.fixture
def cands(tmp_path) -> Path:
    folder = tmp_path / "candidates"
    folder.mkdir()
    write(folder, TIC_A, score=0.9)
    write(folder, TIC_B, score=0.7, radius_rjup=1.1)
    write(folder, TIC_C, score=0.3, period_d=20.0)
    return folder


@pytest.fixture
def vetter() -> FakePixelVetter:
    return FakePixelVetter()


@pytest.fixture
def known() -> FakeKnownLists:
    return FakeKnownLists()


@pytest.fixture
def run(storage, vetter, known):
    def go(folder: Path, **kw) -> dict:
        kw.setdefault("vetter", vetter)
        kw.setdefault("known", known)
        return finder_ingest.ingest(storage, folder, **kw)

    return go


def _ids(body: dict) -> list[str]:
    return [c["id"] for c in body["items"]]


# ingest --------------------------------------------------------------------------------------


def test_ingest_is_idempotent(storage, run, cands, vetter):
    first = run(cands)
    assert first["candidates"] == {"created": 3, "updated": 0, "unchanged": 0}
    assert first["pixels"]["vetted"] == 3 and sorted(vetter.calls) == sorted([TIC_A, TIC_B, TIC_C])
    before = storage.get_candidate(f"{TIC_A}_1")

    again = run(cands)
    assert again["candidates"] == {"created": 0, "updated": 0, "unchanged": 3}
    assert again["pixels"]["vetted"] == 0 and len(vetter.calls) == 3  # nothing re-vetted
    assert storage.get_candidate(f"{TIC_A}_1") == before  # not rewritten (same updated_at)

    # A nightly re-run that only restamps created_at is still "unchanged".
    write(cands, TIC_A, score=0.9, created_at="2026-09-26T02:00:00Z")
    assert run(cands)["candidates"]["unchanged"] == 3


def test_changed_candidate_is_rewritten_and_keeps_status_and_votes(storage, run, cands, vetter):
    run(cands)
    storage.put_vote(f"{TIC_A}_1", "k" * 64, "planet", [], storage.get_candidate(
        f"{TIC_A}_1")["created_at"])  # fmt: skip
    write(cands, TIC_A, score=0.95, depth_ppm=900.0)  # new depth, same ephemeris
    out = run(cands)
    assert out["candidates"] == {"created": 0, "updated": 1, "unchanged": 2}
    row = storage.get_candidate(f"{TIC_A}_1")
    assert row["record"]["depth_ppm"] == 900.0 and row["score"] == 0.95
    assert row["status"] == "under review" and row["votes"]["planet"] == 1
    assert out["pixels"]["vetted"] == 0  # ephemeris unchanged: the vet still holds

    write(cands, TIC_A, score=0.95, depth_ppm=900.0, period_d=4.9)  # new period: vet again
    assert storage.get_pixel_vet(f"{TIC_A}_1")["current"] is True
    out = run(cands, vetter=None)
    assert storage.get_pixel_vet(f"{TIC_A}_1")["current"] is False
    assert run(cands)["pixels"]["vetted"] == 1 and vetter.calls[-1] == TIC_A
    assert storage.get_pixel_vet(f"{TIC_A}_1")["current"] is True


def test_invalid_files_are_reported_and_others_stored(storage, run, cands, tmp_path):
    (cands / "999_1.json").write_text("{not json")
    (cands / "998_1.json").write_text(json.dumps({"tic": 998, "period_d": 1.0}))
    (cands / "997_1.json").write_text(json.dumps(candidate(12345)))  # tic != file name
    (cands / "notes.json").write_text("{}")  # not <tic>_<n>: ignored
    out = run(cands)
    assert sorted(i["file"] for i in out["invalid"]) == ["997_1.json", "998_1.json", "999_1.json"]
    assert out["candidates"]["created"] == 3


def test_cli_exit_code_and_summary(tmp_path, cands, capsys):
    db = str(tmp_path / "f.db")
    (cands.parent / "summary.json").write_text(json.dumps({"funnel": {"stars searched": 9}}))
    assert finder_ingest.main(["--dir", str(cands), "--db", db, "--no-recheck"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["candidates"]["created"] == 3 and out["summary_stored"] is True
    (cands / "5_1.json").write_text("[]")
    assert finder_ingest.main(["--dir", str(cands), "--db", db, "--no-pixels"]) == 1


def test_pixel_failures_are_retried_up_to_the_limit(storage, run, cands, vetter):
    vetter.fail.add(TIC_B)
    for expected_failed in (1, 1, 1, 0):
        out = run(cands, max_vet_attempts=3)
        assert out["pixels"]["failed"] == expected_failed
    assert vetter.calls.count(TIC_B) == 3
    assert storage.get_pixel_vet(f"{TIC_B}_1") is None
    vetter.fail.clear()
    write(cands, TIC_B, score=0.7, radius_rjup=1.1, t0_btjd=2101.0)  # new ephemeris: fresh tries
    assert run(cands)["pixels"]["vetted"] == 1


def test_pixel_limit_and_time_budget(storage, run, cands, vetter):
    out = run(cands, pixel_limit=1)
    assert out["pixels"]["vetted"] == 1 and vetter.calls == [TIC_A]  # best score first
    t = [0.0]

    def clock():
        t[0] += 10
        return t[0]

    out = run(cands, time_budget_s=15, clock=clock, known=None)
    assert out["pixels"] == {"vetted": 1, "failed": 0, "skipped_for_time": 1}


# dismissal on re-check -----------------------------------------------------------------------


def test_known_lists_in_the_candidate_dismiss_it(storage, run, cands):
    run(cands)
    write(cands, TIC_B, score=0.7, radius_rjup=1.1,
          known_lists=[{"list": "TOI", "name": "TOI-1234.01", "alias": "same period"}])  # fmt: skip
    out = run(cands)
    assert out["dismissed"] == [
        {"id": f"{TIC_B}_1", "reason": "matches TOI TOI-1234.01 (same period)"}
    ]
    row = storage.get_candidate(f"{TIC_B}_1")
    assert row["status"] == "dismissed" and row["status_reason"].startswith("matches TOI")
    assert run(cands)["dismissed"] == []  # already dismissed: not repeated


def test_recheck_dismisses_and_skips_exported(storage, run, cands, known, vetter):
    run(cands)
    storage.mark_exported([f"{TIC_C}_1"], storage.get_candidate(f"{TIC_C}_1")["created_at"])
    known.matches[TIC_A] = KnownMatch("CTOI", "TIC150428135.01", None)
    known.matches[TIC_C] = KnownMatch("CTOI", "our own export", None)
    known.calls.clear()
    out = run(cands)
    assert [d["id"] for d in out["dismissed"]] == [f"{TIC_A}_1"]
    assert storage.get_candidate(f"{TIC_A}_1")["status"] == "dismissed"
    assert storage.get_candidate(f"{TIC_C}_1")["status"] == "exported"
    assert TIC_C not in known.calls  # exported candidates are not re-checked
    assert out["recheck"]["checked"] == 2
    # Dismissed candidates are not pixel-vetted, voted on, or listed by default.
    assert storage.candidates_to_vet(10, 3) == []


def test_recheck_when_lists_are_down_keeps_candidates_open(storage, run, cands, known):
    known.down = True
    out = run(cands)
    assert out["recheck"] == {"checked": 0, "errors": 3} and out["dismissed"] == []
    assert {r[0] for r in storage.candidates_to_recheck(10)} == {
        f"{TIC_A}_1", f"{TIC_B}_1", f"{TIC_C}_1"
    }  # fmt: skip
    known.down = False
    run(cands, recheck_limit=1)
    # The one just checked goes to the back of the queue.
    assert storage.candidates_to_recheck(10)[-1][0] == f"{TIC_A}_1"


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        ([], None),
        ({}, None),
        ([{"list": "TOI", "name": "TOI-1.01", "matched": False}], None),
        ({"status": "not_on_lists"}, None),
        ({"status": "known", "list_name": "EB", "name": "TIC 5", "alias": "same period"},
         "matches EB TIC 5 (same period)"),
        ({"toi": [], "confirmed": [{"name": "WASP-18 b"}]}, "matches confirmed WASP-18 b"),
        ([{"list": "CTOI", "name": "TIC1.02"}], "matches CTOI TIC1.02"),
        # the web client's shape: {confirmed, toi, ctoi, eb}, each bool or {matched, id}
        ({"confirmed": False, "toi": {"matched": False, "id": None}, "ctoi": False, "eb": False},
         None),
        ({"confirmed": False, "toi": True, "ctoi": False, "eb": False}, "matches the toi list"),
        ({"confirmed": False, "toi": False, "ctoi": False, "eb": {"matched": True, "id": "EB 7"}},
         "matches eb EB 7"),
    ],
)  # fmt: skip
def test_known_match_shapes(value, expected):
    m = known_match(value)
    assert (m.reason() if m else None) == expected


# votes ---------------------------------------------------------------------------------------


@pytest.fixture
def ingested(run, cands):
    run(cands)
    return cands


def test_vote_cast_change_and_uniqueness(client, ingested):
    cid = f"{TIC_A}_1"
    chips = ["clean-dip", "Clean-Dip", "on-target"]
    r = client.post(f"{C}/{cid}/vote", json={"vote": "planet", "reason_chips": chips},
                    headers={"X-Voter-Key": KEY})  # fmt: skip
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["previous_vote"] is None and body["status"] == "under review"
    assert body["reason_chips"] == ["clean-dip", "on-target"]
    assert body["votes"] == {"planet": 1, "fake": 0, "unsure": 0, "total": 1}

    r = client.post(f"{C}/{cid}/vote", json={"vote": "fake", "reason_chips": ["v-shape"]},
                    headers={"X-Voter-Key": KEY})  # fmt: skip
    assert r.json()["previous_vote"] == "planet"
    assert r.json()["votes"] == {"planet": 0, "fake": 1, "unsure": 0, "total": 1}

    client.post(f"{C}/{cid}/vote", json={"vote": "unsure"}, headers={"X-Voter-Key": KEY2})
    detail = client.get(f"{C}/{cid}", headers={"X-Voter-Key": KEY}).json()
    assert detail["votes"]["total"] == 2
    assert detail["votes"]["reasons"] == {"fake": {"v-shape": 1}}
    assert detail["my_vote"]["vote"] == "fake" and detail["my_vote"]["reason_chips"] == ["v-shape"]
    assert client.get(f"{C}/{cid}").json()["my_vote"] is None


def test_vote_errors(client, ingested, storage, backend):
    cid = f"{TIC_A}_1"
    assert client.post(f"{C}/{cid}/vote", json={"vote": "planet"}).status_code == 400
    bad_key = client.post(f"{C}/{cid}/vote", json={"vote": "planet"},
                          headers={"X-Voter-Key": "short"})  # fmt: skip
    assert bad_key.status_code == 422
    h = {"X-Voter-Key": KEY}
    assert client.post(f"{C}/{cid}/vote", json={"vote": "maybe"}, headers=h).status_code \
        == 422  # fmt: skip
    assert client.post(f"{C}/{cid}/vote", json={"vote": "planet", "reason_chips":
                       ["<script>"]}, headers=h).status_code == 422  # fmt: skip
    assert client.post(f"{C}/{cid}/vote", json={"vote": "planet", "reason_chips":
                       [f"c{i}" for i in range(9)]}, headers=h).status_code == 422  # fmt: skip
    assert client.post(f"{C}/1_9/vote", json={"vote": "planet"}, headers=h).status_code \
        == 404  # fmt: skip
    assert client.post(f"{C}/x/vote", json={"vote": "planet"}, headers=h).status_code \
        == 404  # fmt: skip
    storage.dismiss_candidate(cid, "matches TOI TOI-1.01", storage.get_candidate(cid)["created_at"])
    assert client.post(f"{C}/{cid}/vote", json={"vote": "planet"}, headers=h).status_code \
        == 409  # fmt: skip
    # Only a hash of the key is stored.
    assert KEY not in json.dumps(storage.vote_reasons(cid)) + str(storage.get_vote(cid, KEY))


def test_concurrent_votes_are_all_counted(client, ingested, storage):
    cid = f"{TIC_A}_1"
    errors: list = []

    def cast(i: int) -> None:
        r = client.post(f"{C}/{cid}/vote", json={"vote": "planet" if i % 2 else "fake"},
                        headers={"X-Voter-Key": f"concurrent-voter-{i:04d}"})  # fmt: skip
        if r.status_code != 200:
            errors.append(r.text)

    threads = [threading.Thread(target=cast, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert storage.get_candidate(cid)["votes"] == {"planet": 8, "fake": 8, "unsure": 0,
                                                   "total": 16}  # fmt: skip


def test_vote_rate_limit_is_per_ip_and_separate_from_reads(make_client, ingested, clock):
    client = make_client(rate_vote_per_min=2, rate_read_per_min=100)
    cid = f"{TIC_A}_1"

    def vote(key: str) -> int:
        return client.post(f"{C}/{cid}/vote", json={"vote": "planet"},
                           headers={"X-Voter-Key": key}).status_code  # fmt: skip

    assert [vote(KEY), vote(KEY2)] == [200, 200]
    r = client.post(f"{C}/{cid}/vote", json={"vote": "planet"},
                    headers={"X-Voter-Key": "a-third-voter-key-xyz"})  # fmt: skip
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1  # new keys don't help
    assert client.get(f"{C}/{cid}").status_code == 200
    clock.t += 30
    assert vote(KEY) == 200


# list, detail, funnel, sensitivity -----------------------------------------------------------


def test_list_filters_sorts_and_cursor(client, ingested, storage, vetter, run):
    body = client.get(f"{C}").json()
    assert _ids(body) == [f"{TIC_A}_1", f"{TIC_B}_1", f"{TIC_C}_1"]  # by score
    item = body["items"][0]
    assert item["pixel_verdict"] == "on target" and item["status"] == "new"
    assert "folded" not in item and item["radius_rjup"] == 0.42
    assert _ids(client.get(f"{C}?min_radius=1").json()) == [f"{TIC_B}_1"]
    assert _ids(client.get(f"{C}?max_radius=0.5&max_period=10").json()) == [f"{TIC_A}_1"]
    assert _ids(client.get(f"{C}?min_period=10").json()) == [f"{TIC_C}_1"]
    assert _ids(client.get(f"{C}?pixel_verdict=off_target").json()) == []
    assert len(client.get(f"{C}?pixel_verdict=on target,unvetted").json()["items"]) == 3
    assert client.get(f"{C}?pixel_verdict=bogus").status_code == 422
    assert client.get(f"{C}?status=nope").status_code == 422

    h = {"X-Voter-Key": KEY}
    client.post(f"{C}/{TIC_C}_1/vote", json={"vote": "planet"}, headers=h)
    assert _ids(client.get(f"{C}?sort=votes").json())[0] == f"{TIC_C}_1"
    assert _ids(client.get(f"{C}?status=under review").json()) == [f"{TIC_C}_1"]
    assert f"{TIC_C}_1" in _ids(client.get(f"{C}?needs_votes=true").json())
    many = make_votes(client, f"{TIC_C}_1", 5)
    assert many and f"{TIC_C}_1" not in _ids(client.get(f"{C}?needs_votes=true").json())

    storage.dismiss_candidate(f"{TIC_B}_1", "matches TOI x", storage.get_candidate(
        f"{TIC_B}_1")["created_at"])  # fmt: skip
    assert f"{TIC_B}_1" not in _ids(client.get(f"{C}").json())
    assert _ids(client.get(f"{C}?status=dismissed").json()) == [f"{TIC_B}_1"]

    for n in range(2, 9):
        write(ingested, TIC_A, n, score=0.5, created_at=f"2026-09-{10 + n:02d}T00:00:00Z")
    run(ingested)
    for sort in ("score", "newest", "votes"):
        seen, cursor = [], None
        while True:
            url = f"{C}?sort={sort}&limit=3" + (f"&cursor={cursor}" if cursor else "")
            page = client.get(url).json()
            seen += _ids(page)
            cursor = page["next_cursor"]
            if not cursor:
                break
        assert len(seen) == len(set(seen)) == 9, sort
    newest = _ids(client.get(f"{C}?sort=newest&limit=2").json())
    # Same created_at: newest id first. TIC_B is dismissed, so not listed.
    assert newest == [f"{TIC_C}_1", f"{TIC_A}_1"]
    assert client.get(f"{C}?cursor=garbage").status_code == 422
    score_cursor = client.get(f"{C}?limit=1").json()["next_cursor"]
    assert client.get(f"{C}?sort=newest&cursor={score_cursor}").status_code == 422


def make_votes(client, cid: str, n: int) -> bool:
    return all(
        client.post(f"{C}/{cid}/vote", json={"vote": "unsure"},
                    headers={"X-Voter-Key": f"bulk-voter-key-{i:04d}"}).status_code == 200
        for i in range(n)
    )  # fmt: skip


def test_detail(client, ingested):
    body = client.get(f"{C}/{TIC_A}_1").json()
    c = body["candidate"]
    assert c["id"] == f"{TIC_A}_1" and c["status"] == "new" and c["folded"]["flux"]
    assert c["checks"][0]["name"] == "odd_even"
    vet = body["pixel_vet"]
    assert vet["verdict"] == "on target" and vet["current"] is True
    assert set(vet["images"]) == {"out_of_transit", "difference", "markers"}
    assert body["votes"]["total"] == 0 and body["my_vote"] is None
    assert client.get(f"{C}/1_1").status_code == 404
    assert client.get(f"{C}/not-an-id").status_code == 404


def test_funnel_and_sensitivity(client, storage, run, cands, tmp_path):
    assert client.get("/finder/sensitivity").status_code == 404
    empty = client.get("/finder/funnel").json()
    assert empty["sweep_at"] is None and empty["stages"][0] == {
        "stage": "candidates in the finder", "count": 0, "source": "finder"
    }  # fmt: skip
    summary = tmp_path / "sweep.json"
    summary.write_text(json.dumps({"stages": [
        {"stage": "stars searched", "count": 12000}, {"stage": "signals", "count": 800},
        {"stage": "passed checks", "count": 3}]}))  # fmt: skip
    sens = tmp_path / "sens.json"
    sens.write_text(json.dumps({"grid": {"period_d": [1, 10], "radius_rjup": [0.1, 1]},
                                "recovery": [[0.2, 0.9], [0.1, 0.8]]}))  # fmt: skip
    run(cands, summary=summary, sensitivity=sens)
    f = client.get("/finder/funnel").json()
    assert f["sweep_at"] is not None
    assert [(s["stage"], s["count"], s["source"]) for s in f["stages"]][:4] == [
        ("stars searched", 12000, "sweep"), ("signals", 800, "sweep"),
        ("passed checks", 3, "sweep"), ("candidates in the finder", 3, "finder"),
    ]  # fmt: skip
    assert f["by_pixel_verdict"]["on target"] == 3 and f["by_status"]["new"] == 3
    s = client.get("/finder/sensitivity").json()
    assert s["sensitivity"]["recovery"][0] == [0.2, 0.9] and s["updated_at"]


# admin export --------------------------------------------------------------------------------

TOKEN = "s3cret-admin-token-0123456789"


def test_admin_token(make_client, ingested):
    body = {"ids": [f"{TIC_A}_1"]}
    off = make_client()  # PH_ADMIN_TOKEN unset
    assert off.post("/finder/export/ctoi", json=body,
                    headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 404  # fmt: skip
    on = make_client(admin_token=TOKEN)
    assert on.post("/finder/export/ctoi", json=body).status_code == 403
    assert on.post("/finder/export/ctoi", json=body,
                   headers={"Authorization": f"Bearer {TOKEN}x"}).status_code == 403  # fmt: skip
    assert on.post("/finder/export/ctoi", json=body,
                   headers={"Authorization": TOKEN}).status_code == 403  # fmt: skip
    ok = on.post("/finder/export/ctoi", json=body, headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/plain")
    assert "/finder/export/ctoi" not in on.get("/openapi.json").text
    assert on.post("/finder/export/ctoi", json=body,
                   headers={"Authorization": f"Basic {TOKEN}"}).status_code == 403  # fmt: skip


def test_old_paths_are_gone(make_client, ingested):
    client = make_client(admin_token=TOKEN)
    assert client.get("/candidates").status_code == 404
    assert client.get(f"/candidates/{TIC_A}_1").status_code == 404
    assert client.post(f"/candidates/{TIC_A}_1/vote", json={"vote": "planet"},
                       headers={"X-Voter-Key": KEY}).status_code == 404  # fmt: skip
    assert client.post("/admin/candidates/export", json={"ids": [f"{TIC_A}_1"]},
                       headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 404  # fmt: skip


def test_export_refuses_off_target_and_exports_nothing(make_client, storage, run, cands, vetter):
    vetter.verdicts[TIC_B] = "off target"
    vetter.verdicts[TIC_C] = "inconclusive"
    run(cands)
    client = make_client(admin_token=TOKEN)
    h = {"Authorization": f"Bearer {TOKEN}"}
    ids = [f"{TIC_A}_1", f"{TIC_B}_1", f"{TIC_C}_1"]
    r = client.post("/finder/export/ctoi", headers=h, json={"ids": ids})
    assert r.status_code == 422
    assert r.json()["detail"] == {"reason": "Dip comes from a neighbour; not exportable",
                                  "ids": [f"{TIC_B}_1"]}  # fmt: skip
    assert {storage.get_candidate(i)["status"] for i in ids} == {"new"}  # nothing exported

    write(cands, TIC_A, 2, score=0.1)  # a fresh candidate, not pixel-checked yet
    run(cands, vetter=None)
    ok = client.post("/finder/export/ctoi", headers=h,
                     json={"ids": [f"{TIC_A}_1", f"{TIC_C}_1", f"{TIC_A}_2"]})  # fmt: skip
    assert ok.status_code == 200, ok.text
    data = [ln for ln in ok.text.splitlines() if not ln.startswith("\\")]
    notes = {row.split("|")[0]: row.split("|")[-1] for row in data[1:]}
    assert "pixel check: on target" in notes[f"TIC{TIC_A}.01"]
    assert "pixel check inconclusive" in notes[f"TIC{TIC_C}.01"]
    assert "no pixel check yet" in notes[f"TIC{TIC_A}.02"]
    assert all(len(n) <= 120 for n in notes.values())


def test_export_file_columns_and_status(make_client, ingested, storage):
    client = make_client(admin_token=TOKEN)
    h = {"Authorization": f"Bearer {TOKEN}"}
    ids = [f"{TIC_A}_1", f"{TIC_B}_1"]
    r = client.post("/finder/export/ctoi", headers=h,
                    json={"ids": ids, "tag": "20260926_owner_finder",
                          "paper_url": "https://doi.org/10.0000/x"})  # fmt: skip
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith('attachment; filename="params_planet_')
    lines = r.text.splitlines()
    data = [ln for ln in lines if not ln.startswith("\\")]
    header, rows = data[0].split("|"), [ln.split("|") for ln in data[1:]]
    assert header == list(COLUMNS) and len(header) == 46
    assert header[:8] == ["target", "flag", "disp", "discovery", "candname", "period",
                          "period_unc", "epoch"]  # fmt: skip
    assert header[-5:] == ["tag", "group", "prop_period", "paper", "notes"]
    assert len(rows) == 2 and all(len(row) == 46 for row in rows)
    row = dict(zip(header, rows[0], strict=True))
    assert row["target"] == f"TIC{TIC_A}.01" and row["flag"] == "newctoi" and row["disp"] == "PC"
    assert float(row["epoch"]) == pytest.approx(2100.25 + 2457000.0)
    assert float(row["period"]) == pytest.approx(4.5) and float(row["depth"]) == 850.0
    assert float(row["duration"]) == 2.4
    assert float(row["radius"]) == pytest.approx(0.42 * 11.2089, rel=1e-3)
    assert float(row["radius_unc"]) == pytest.approx(0.05 * 11.2089, rel=1e-3)
    assert row["prop_period"] == "0" and row["tag"] == "20260926_owner_finder"
    assert row["paper"] == "https://doi.org/10.0000/x"
    assert 0 < len(row["notes"]) <= 120 and "candidate" in row["notes"]
    assert not any(ln.startswith("\\ WARNING") for ln in lines)
    assert not honesty.BANNED.search(r.text)
    for cid in ids:
        assert storage.get_candidate(cid)["status"] == "exported"
    assert storage.get_candidate(f"{TIC_C}_1")["status"] == "new"


def test_export_rejects_unknown_and_dismissed(make_client, ingested, storage):
    client = make_client(admin_token=TOKEN)
    h = {"Authorization": f"Bearer {TOKEN}"}
    r = client.post("/finder/export/ctoi", headers=h, json={"ids": [f"{TIC_A}_1", "7_7"]})
    assert r.status_code == 404 and r.json()["detail"]["ids"] == ["7_7"]
    storage.dismiss_candidate(f"{TIC_B}_1", "matches TOI x", storage.get_candidate(
        f"{TIC_B}_1")["created_at"])  # fmt: skip
    r = client.post("/finder/export/ctoi", headers=h, json={"ids": [f"{TIC_B}_1"]})
    assert r.status_code == 409
    assert storage.get_candidate(f"{TIC_A}_1")["status"] == "new"  # nothing marked
    r = client.post("/finder/export/ctoi", headers=h, json={"ids": [f"{TIC_A}_1"]})
    assert "\\ WARNING: `paper` is empty" in r.text  # ExoFOP requires one for newctoi
    assert client.post("/finder/export/ctoi", headers=h, json={"ids": []}).status_code == 422


# honesty -------------------------------------------------------------------------------------


def test_honesty_scan(client, storage, run, cands, tmp_path, make_client):
    write(cands, TIC_A, score=0.9, checks=[{"name": "shape", "value": 1, "passed": True,
          "reason": "Looks like a new planet discovered by TESS"}])  # fmt: skip
    summary = tmp_path / "s.json"
    summary.write_text(json.dumps({"funnel": {"new planets discovered": 1}}))
    run(cands, summary=summary)
    stored = storage.get_candidate(f"{TIC_A}_1")["record"]
    assert not honesty.violations(stored)
    assert stored["checks"][0]["reason"] == "Looks like a planet candidate detected by TESS"
    # HonestClient fails on any violation in a JSON response.
    client.get(f"{C}")
    client.get(f"{C}/{TIC_A}_1")
    client.get("/finder/funnel")
    admin = make_client(admin_token=TOKEN)
    text = admin.post("/finder/export/ctoi", headers={"Authorization": f"Bearer {TOKEN}"},
                      json={"ids": [f"{TIC_A}_1"]}).text  # fmt: skip
    assert not honesty.BANNED.search(text)


def test_cli_without_pixels_installed_still_ingests(tmp_path, cands, capsys, monkeypatch):
    import api.adapters.finder_real as real

    def missing():
        raise ImportError("No module named 'skypixels'")

    monkeypatch.setattr(real, "_vet_pixels", missing)
    monkeypatch.setenv("PH_ADAPTERS", "real")
    db = str(tmp_path / "f.db")
    assert finder_ingest.main(["--dir", str(cands), "--db", db, "--no-recheck"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["candidates"]["created"] == 3 and out["pixels"]["vetted"] == 0
    assert "skypixels" in out["pixels"]["unavailable"]


# CONNECT fixes, v2 ---------------------------------------------------------------------------


def test_vote_null_withdraws(client, ingested, storage):
    cid, h = f"{TIC_A}_1", {"X-Voter-Key": KEY}
    client.post(f"{C}/{cid}/vote", json={"vote": "planet", "reason_chips": ["clean-dip"]},
                headers=h)  # fmt: skip
    r = client.post(f"{C}/{cid}/vote", json={"vote": None, "reason_chips": ["ignored"]},
                    headers=h)  # fmt: skip
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vote"] is None and body["previous_vote"] == "planet"
    assert body["reason_chips"] == [] and body["votes"]["total"] == 0
    assert body["status"] == "new"  # its last vote gone: back from "under review"
    detail = client.get(f"{C}/{cid}", headers=h).json()
    assert detail["my_vote"] is None and detail["votes"]["reasons"] == {}
    # Withdrawing again, or with no vote cast, is a no-op.
    again = client.post(f"{C}/{cid}/vote", json={"vote": None}, headers=h).json()
    assert again["previous_vote"] is None and again["votes"]["total"] == 0
    # Another voter's vote keeps it under review.
    client.post(f"{C}/{cid}/vote", json={"vote": "fake"}, headers={"X-Voter-Key": KEY2})
    client.post(f"{C}/{cid}/vote", json={"vote": "planet"}, headers=h)
    left = client.post(f"{C}/{cid}/vote", json={"vote": None}, headers=h).json()
    assert left["status"] == "under review" and left["votes"]["fake"] == 1
    # A dismissed candidate takes no new votes, but a vote can still be withdrawn.
    storage.dismiss_candidate(cid, "matches TOI x", storage.get_candidate(cid)["created_at"])
    assert client.post(f"{C}/{cid}/vote", json={"vote": "planet"}, headers=h).status_code == 409
    gone = client.post(f"{C}/{cid}/vote", json={"vote": None}, headers={"X-Voter-Key": KEY2})
    assert gone.status_code == 200 and gone.json()["status"] == "dismissed"
    # The vote key is still required to withdraw.
    assert client.post(f"{C}/{cid}/vote", json={"vote": None}).status_code == 400


def test_rows_carry_checks_score_parts_and_radius_range(client, run, tmp_path):
    folder = tmp_path / "c"
    folder.mkdir()
    write(folder, TIC_A, checks=[
        {"name": "odd_even", "value": 0.1, "passed": True, "reason": "same depth"},
        {"name": "secondary", "value": 3.0, "passed": False, "reason": "eclipse at phase 0.5"},
        {"name": "centroid", "value": None, "passed": None, "reason": "not run"},
    ])  # fmt: skip
    run(folder)
    item = client.get(C).json()["items"][0]
    assert (item["checks_passed"], item["checks_total"]) == (1, 2)  # "not run" doesn't count
    assert item["score_parts"] == {"snr": 0.3, "shape": 0.2}
    assert (item["radius_low"], item["radius_high"]) == (0.38, 0.47)
    assert "checks" not in item and "folded" not in item


def test_hunt_shaped_radius_filters(client, run, tmp_path):
    """hunt writes radius_rjup as [low, high] plus radius_rjup_best."""
    folder = tmp_path / "c"
    folder.mkdir()
    write(folder, TIC_A, radius_rjup=[0.9, 1.3], radius_low=0.9, radius_high=1.3,
          radius_rjup_best=1.1)  # fmt: skip
    write(folder, TIC_B, radius_rjup=[0.2, 0.3], radius_low=0.2, radius_high=0.3)  # midpoint 0.25
    run(folder)
    assert _ids(client.get(f"{C}?min_radius=1").json()) == [f"{TIC_A}_1"]
    assert _ids(client.get(f"{C}?max_radius=0.26").json()) == [f"{TIC_B}_1"]
    item = client.get(f"{C}?min_radius=1").json()["items"][0]
    assert item["radius_rjup"] == [0.9, 1.3] and item["radius_rjup_best"] == 1.1


def test_single_and_duo_dip_ids(client, run, storage, make_client, tmp_path, vetter):
    """DEEPHUNT names single/duo dips <tic>_s<m> / <tic>_d<m>; a single dip has no period."""
    folder = tmp_path / "c"
    folder.mkdir()
    write(folder, TIC_A, 1)
    (folder / f"{TIC_A}_s1.json").write_text(json.dumps(
        candidate(TIC_A, 1, period_d=None, kind="single", score=0.95)))  # fmt: skip
    (folder / f"{TIC_B}_d2.json").write_text(json.dumps(
        candidate(TIC_B, 1, period_d=31.2, kind="duo")))  # fmt: skip
    out = run(folder)
    assert out["invalid"] == [] and out["candidates"]["created"] == 3
    assert TIC_A in vetter.calls and vetter.calls.count(TIC_A) == 1  # s1 has no period: no vet
    ids = _ids(client.get(C).json())
    assert ids[0] == f"{TIC_A}_s1" and set(ids) == {f"{TIC_A}_1", f"{TIC_A}_s1", f"{TIC_B}_d2"}
    assert client.get(f"{C}/{TIC_A}_s1").json()["candidate"]["kind"] == "single"
    r = client.post(f"{C}/{TIC_B}_d2/vote", json={"vote": "planet"}, headers={"X-Voter-Key": KEY})
    assert r.status_code == 200
    assert client.get(f"{C}/{TIC_A}_S1").status_code == 404  # lower case only
    admin = make_client(admin_token=TOKEN)
    r = admin.post("/finder/export/ctoi", headers={"Authorization": f"Bearer {TOKEN}"},
                   json={"ids": [f"{TIC_A}_1", f"{TIC_A}_s1"]})  # fmt: skip
    assert r.status_code == 422 and r.json()["detail"]["ids"] == [f"{TIC_A}_s1"]
    assert storage.get_candidate(f"{TIC_A}_1")["status"] == "new"


def test_vetting_block_is_stored_and_returned(client, run, tmp_path, storage):
    folder = tmp_path / "c"
    folder.mkdir()
    vetting = {"verdict": "passed", "tests": [{"name": "odd_even", "passed": True,
               "reason": "Looks like a new planet"}]}  # fmt: skip
    write(folder, TIC_A, vetting=vetting)
    write(folder, TIC_B)
    (folder / f"{TIC_C}_1.json").write_text(json.dumps(candidate(TIC_C, vetting=["no"])))
    out = run(folder)
    assert [i["file"] for i in out["invalid"]] == [f"{TIC_C}_1.json"]
    got = client.get(f"{C}/{TIC_A}_1").json()["candidate"]["vetting"]
    assert (
        got["verdict"] == "passed" and got["tests"][0]["reason"] == "Looks like a planet candidate"
    )
    assert client.get(f"{C}/{TIC_B}_1").json()["candidate"]["vetting"] is None
    assert storage.get_candidate(f"{TIC_A}_1")["vetting"] == got


def test_empty_night(tmp_path, capsys, storage, run):
    """No candidates at all: the artifact may have no candidates/ folder, or an empty one."""
    root = tmp_path / "sweep"
    root.mkdir()
    (root / "summary.json").write_text(json.dumps({"funnel": {"stars searched": 4000}}))
    out = run(root / "candidates")
    assert out["candidates"] == {"created": 0, "updated": 0, "unchanged": 0}
    assert out["invalid"] == [] and out["summary_stored"] is True
    (root / "candidates").mkdir()
    db = str(tmp_path / "f.db")
    assert finder_ingest.main(["--dir", str(root / "candidates"), "--db", db]) == 0
    assert json.loads(capsys.readouterr().out)["summary_stored"] is True
    (root / "file").write_text("x")
    with pytest.raises(SystemExit):
        finder_ingest.main(["--dir", str(root / "file"), "--db", db])

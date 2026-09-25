"""Storing what traps catch: ID conventions, updates instead of duplicates, one catch per player."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from api import conventions, honesty
from api.contract import Discovery
from api.ports import Storage
from api.timeutil import iso


@dataclass
class IngestResult:
    stored: list[Discovery] = field(default_factory=list)
    new_catches: int = 0
    created: int = 0
    updated: int = 0
    rejected: list[str] = field(default_factory=list)


def _comparable(d: Discovery) -> dict:
    data = d.model_dump(mode="json")
    data["raw"] = {k: v for k, v in data["raw"].items() if k != "updated_at"}
    return data


def _merge(existing: Discovery, incoming: Discovery, now: datetime) -> Discovery | None:
    """The updated record, or None when nothing changed (so re-runs write nothing)."""
    merged = incoming.model_copy(
        update={"detected_at": min(existing.detected_at, incoming.detected_at)}
    )
    if _comparable(merged) == _comparable(existing):
        return None
    return merged.model_copy(update={"raw": {**incoming.raw, "updated_at": iso(now)}})


def ingest(
    storage: Storage,
    player_id: str,
    trap_id: str | None,
    discoveries: list[Discovery],
    now: datetime,
) -> IngestResult:
    """Upsert discoveries (IDs already final) and link them to the player."""
    result = IngestResult()
    with storage.atomic():
        for incoming in discoveries:
            incoming = honesty.clean(incoming)
            existing = storage.get_discovery(incoming.id)
            if existing is None:
                storage.put_discovery(incoming)
                stored = incoming
                result.created += 1
            else:
                merged = _merge(existing, incoming, now)
                if merged is not None:
                    storage.put_discovery(merged)
                    result.updated += 1
                stored = merged or existing
            if storage.add_catch(player_id, stored.id, trap_id, now):
                result.new_catches += 1
            result.stored.append(stored)
    return result


def ingest_rubin(
    storage: Storage, player_id: str, trap_id: str | None, found: list[Discovery], now: datetime
) -> IngestResult:
    kept, rejected = conventions.normalize_rubin(found)
    result = ingest(storage, player_id, trap_id, kept, now)
    result.rejected = rejected
    return result


def ingest_hunt(
    storage: Storage,
    player_id: str,
    trap_id: str | None,
    tic_id: int,
    found: list[Discovery],
    now: datetime,
) -> IngestResult:
    """Give TESS results their final IDs against what is stored, then ingest, in one transaction."""
    with storage.atomic():
        existing = storage.discoveries_with_prefix(f"tess:{tic_id}:sig:")
        final, rejected = conventions.assign_tess_ids(tic_id, found, existing)
        result = ingest(storage, player_id, trap_id, final, now)
    result.rejected = rejected
    return result

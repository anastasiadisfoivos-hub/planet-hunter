from __future__ import annotations

from datetime import UTC, datetime, timedelta

from api.contract import Cutouts, Discovery
from tests.conftest import SKY


def _disc(i: int) -> Discovery:
    return Discovery(
        id=f"rubin:obj:{i}",
        type="supernova",
        confidence=0.5,
        source="rubin",
        origin="test",
        ra_deg=10,
        dec_deg=10,
        detected_at=datetime(2026, 9, 1, tzinfo=UTC),
        known_status="unchecked",
        cutouts=Cutouts(),
        explanation="Best guess: supernova.",
    )


def _seed(storage, player_id: str, n: int) -> None:
    base = datetime(2026, 9, 1, tzinfo=UTC)
    for i in range(n):
        storage.put_discovery(_disc(i))
        # Two catches share each timestamp so the ID tie-break matters.
        storage.add_catch(player_id, f"rubin:obj:{i}", None, base + timedelta(minutes=i // 2))


def test_newest_first_and_paging(client, alice, services):
    pid = alice["X-Player-Id"]
    _seed(services.storage, pid, 7)
    seen, cursor = [], None
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        page = client.get("/discoveries", params=params, headers=alice).json()
        seen += [d["id"] for d in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    expected = [f"rubin:obj:{i}" for i in (6, 5, 4, 3, 2, 1, 0)]
    assert seen == expected


def test_discovery_detail(client, alice, bob):
    catches = client.post("/traps", json={"sphere": SKY}, headers=alice).json()["catches"]
    did = catches[0]["id"]
    r = client.get(f"/discoveries/{did}", headers=alice)
    assert r.status_code == 200
    d = Discovery.model_validate(r.json())
    assert d.model_dump(mode="json") == catches[0]
    assert client.get(f"/discoveries/{did}", headers=bob).status_code == 404
    assert client.get("/discoveries/rubin:obj:0", headers=alice).status_code == 404


def test_empty_and_bad_params(client, alice):
    assert client.get("/discoveries", headers=alice).json() == {"items": [], "next_cursor": None}
    assert client.get("/discoveries", params={"limit": 0}, headers=alice).status_code == 422
    assert client.get("/discoveries", params={"limit": 101}, headers=alice).status_code == 422
    assert client.get("/discoveries", params={"cursor": "!!"}, headers=alice).status_code == 422


def test_same_object_caught_by_two_players(client, alice, bob, services):
    a = client.post("/traps", json={"sphere": SKY}, headers=alice).json()["catches"]
    b = client.post("/traps", json={"sphere": SKY}, headers=bob).json()["catches"]
    assert {d["id"] for d in a} == {d["id"] for d in b}
    # One shared record per object, one catch per player.
    assert services.storage.count_catches() == 2 * len(a)
    client.post("/traps", json={"sphere": SKY}, headers=alice)
    assert services.storage.count_catches() == 2 * len(a)

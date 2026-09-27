"""Queue policy: list order, the deep queue's priority (promoted > group 0 > group 1), fast skipping what deep
finished, faint's tier filter, and the nightly split of worker-seconds."""

import csv

from scheduler import queues
from scheduler.ledger import Ledger

FIELDS = ["rank", "list", "tic", "ra", "dec", "tmag", "group", "n_sectors", "sectors_2min", "sectors_ffi"]


def write_targets(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({f: r.get(f, "") for f in FIELDS})


def rows():
    # tic, group, sectors
    spec = [(101, "2", "90"), (102, "0", "10 20 30 40 50"), (103, "1", "1 2 3 4 5 6"), (104, "0", "7 8 9 10 11"),
            (105, "2", "91"), (106, "1", "60 61 62 63 64")]
    return [{"rank": i + 1, "list": "A", "tic": t, "ra": 1, "dec": 2, "tmag": 10, "group": g, "sectors_2min": s}
            for i, (t, g, s) in enumerate(spec)]


def drain(q, run="r1"):
    out = []
    while (row := q.next(run)) is not None:
        out.append(row["tic"])
    return out


def test_fast_goes_down_the_list_and_skips_finished(tmp_path):
    t = tmp_path / "targets.csv"
    write_targets(t, rows())
    led = Ledger(tmp_path / "l.sqlite")
    led.claim("fast", 103, queues.sectors_key(rows()[2]), "r0")
    led.finish("fast", 103, {"outcome": "none"})
    led.claim("deep", 105, queues.sectors_key(rows()[4]), "r0")
    led.finish("deep", 105, {"outcome": "none"})
    qs = queues.build_queues(led, t, None, {"fast": True, "deep": False, "faint": False})
    assert drain(qs["fast"]) == [101, 102, 104, 106]  # 103 done in fast, 105 done in deep


def test_deep_order_promoted_then_group0_then_group1(tmp_path):
    t = tmp_path / "targets.csv"
    write_targets(t, rows())
    led = Ledger(tmp_path / "l.sqlite")
    for tic, score in ((105, 0.2), (101, 0.5)):  # the fast pass flagged these two
        led.claim("fast", tic, "", "r0")
        led.finish("fast", tic, {"outcome": "rejected", "promising": True, "best_score": score})
    qs = queues.build_queues(led, t, None, {"fast": True, "deep": True, "faint": False})
    assert drain(qs["deep"]) == [101, 105, 102, 104, 103, 106]


def test_deep_sees_stars_promoted_during_the_night(tmp_path):
    t = tmp_path / "targets.csv"
    write_targets(t, rows())
    led = Ledger(tmp_path / "l.sqlite")
    qs = queues.build_queues(led, t, None, {"fast": True, "deep": True, "faint": False})
    assert qs["deep"].next("r1")["tic"] == 102
    led.claim("fast", 105, "", "r1")
    led.finish("fast", 105, {"outcome": "candidate", "promising": True})
    qs["deep"].reset()
    assert qs["deep"].next("r1")["tic"] == 105


def test_new_sector_requeues(tmp_path):
    t = tmp_path / "targets.csv"
    write_targets(t, rows())
    led = Ledger(tmp_path / "l.sqlite")
    qs = queues.build_queues(led, t, None, {"fast": True, "deep": False, "faint": False})
    for tic in drain(qs["fast"]):
        led.finish("fast", tic, {"outcome": "none"})
    new = rows()
    new[0]["sectors_2min"] = "90 97"
    write_targets(t, new)
    qs = queues.build_queues(led, t, None, {"fast": True, "deep": False, "faint": False})
    assert drain(qs["fast"], "r2") == [101]


def test_faint_takes_tier_1_only_and_limit(tmp_path):
    f = tmp_path / "faint.csv"
    with open(f, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "tier", "tic", "ra", "dec", "tmag", "sectors"])
        for i, tier in enumerate(["1", "2", "1", "1", "3"]):
            w.writerow([i + 1, tier, 900 + i, 1, 2, 14, "1 2 3"])
    led = Ledger(tmp_path / "l.sqlite")
    qs = queues.build_queues(led, None, f, {"faint": True, "fast": False, "deep": False}, limit=2)
    assert drain(qs["faint"]) == [900, 902]


def test_plain_tic_list(tmp_path):
    t = tmp_path / "tics.txt"
    t.write_text("# test\n11\n12\n")
    led = Ledger(tmp_path / "l.sqlite")
    qs = queues.build_queues(led, t, None, {"fast": True, "deep": True, "faint": False})
    assert drain(qs["fast"]) == [11, 12]
    assert drain(qs["deep"]) == [11, 12]  # no group column: all taken as group 1


def test_split_follows_shares_of_worker_time():
    """Simulate a night on 4 workers with fast 60 s, deep 250 s, faint 90 s per star: the worker-seconds each queue
    gets land within a few percent of its share."""
    split = {"fast": 0.45, "deep": 0.40, "faint": 0.15}
    cost = {"fast": 60.0, "deep": 250.0, "faint": 90.0}
    qs = {n: type("Q", (), {"exhausted": False})() for n in cost}
    used = {n: 0.0 for n in cost}
    running: list[tuple[float, str]] = []  # (finish time, queue)
    now = 0.0
    while now < 20 * 3600:
        while len(running) < 4:
            counts = {n: sum(1 for _, q in running if q == n) for n in cost}
            name = queues.pick_queue(qs, split, used, counts, cost)
            running.append((now + cost[name], name))
        running.sort()
        now, name = running.pop(0)
        used[name] += cost[name]
    total = sum(used.values())
    for n, share in split.items():
        assert abs(used[n] / total - share) < 0.03, (n, used[n] / total)


def test_split_gives_an_empty_queues_time_to_the_others():
    qs = {"fast": type("Q", (), {"exhausted": True})(), "deep": type("Q", (), {"exhausted": False})()}
    assert queues.pick_queue(qs, {"fast": 0.5, "deep": 0.5}, {}, {}, {}) == "deep"
    assert queues.pick_queue({}, {"fast": 1}, {}, {}, {}) is None


def test_plan():
    p = queues.plan({"fast": 0.45, "deep": 0.40, "faint": 0.15}, 4, 21.5 * 3600,
                    {"fast": 60, "deep": 250, "faint": 90}, ["fast", "deep", "faint"])
    assert p == {"fast": 2322, "deep": 495, "faint": 516}

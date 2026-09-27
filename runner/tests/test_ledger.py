"""The ledger: a star is never started twice, failures are retried a bounded number of times, a new sector makes
a finished star eligible again, and a crash (the process dies with stars running) loses nothing."""

import os
import subprocess
import sys
import textwrap

from scheduler.ledger import MAX_ATTEMPTS, Ledger


def test_no_repeats(tmp_path):
    led = Ledger(tmp_path / "l.sqlite")
    assert led.claim("fast", 1, "10 11", "r1")
    assert not led.claim("fast", 1, "10 11", "r1"), "running: never claimed twice"
    led.finish("fast", 1, {"outcome": "none", "elapsed_s": 3})
    assert not led.claim("fast", 1, "10 11", "r2"), "done on the same sectors: not again"
    assert led.claim("deep", 1, "10 11", "r2"), "queues keep separate records"
    assert led.get("fast", 1)["status"] == "done"


def test_no_data_is_done(tmp_path):
    led = Ledger(tmp_path / "l.sqlite")
    led.claim("fast", 2, "", "r1")
    assert led.finish("fast", 2, {"outcome": "no_data", "error": "no_data: none"}) == "done"
    assert not led.claim("fast", 2, "", "r2")


def test_new_sector_makes_it_eligible_again(tmp_path):
    led = Ledger(tmp_path / "l.sqlite")
    led.claim("deep", 3, "10 11", "r1")
    led.finish("deep", 3, {"outcome": "rejected"})
    assert led.claim("deep", 3, "10 11 12", "r2")
    assert led.get("deep", 3)["attempts"] == 1


def test_failures_retried_then_given_up(tmp_path):
    led = Ledger(tmp_path / "l.sqlite")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        assert led.claim("fast", 4, "", f"r{attempt}"), attempt
        assert led.finish("fast", 4, {"outcome": "timeout", "error": "timeout"}) == "failed"
    assert not led.claim("fast", 4, "", "r9")
    assert led.blocked("fast")[4] is None


def test_recover_after_crash_does_not_charge_an_attempt(tmp_path):
    path = tmp_path / "l.sqlite"
    # A separate process claims two stars, finishes one, and dies with the other running (no close, no commit
    # of anything after the claim).
    code = textwrap.dedent(f"""
        import os
        from scheduler.ledger import Ledger
        led = Ledger({str(path)!r})
        led.claim("fast", 5, "", "r1"); led.claim("fast", 6, "", "r1")
        led.finish("fast", 5, {{"outcome": "none"}})
        os._exit(9)
    """)
    env = {**os.environ, "PYTHONPATH": os.path.dirname(os.path.dirname(__file__))}
    assert subprocess.run([sys.executable, "-c", code], env=env).returncode == 9
    led = Ledger(path)
    assert led.get("fast", 6)["status"] == "running"
    assert led.recover() == 1
    row = led.get("fast", 6)
    assert row["status"] == "failed" and row["attempts"] == 0
    assert led.claim("fast", 6, "", "r1"), "retried after the crash"
    assert not led.claim("fast", 5, "", "r1"), "the finished one is not repeated"


def test_vets_queue(tmp_path):
    led = Ledger(tmp_path / "l.sqlite")
    assert led.add_vets("r1", [("7_1", 7, "/a/7_1.json")]) == 1
    assert led.add_vets("r1", [("7_1", 7, "/a/7_1.json")]) == 0, "same file: not queued twice"
    v = led.next_vet()
    assert v["stem"] == "7_1" and led.next_vet() is None
    led.finish_vet("7_1", ok=True, verdict="pass", vetted_path="/v/7_1.json")
    assert led.vetted()["7_1"]["verdict"] == "pass"
    assert led.add_vets("r2", [("7_1", 7, "/b/7_1.json")]) == 1, "found again on a new night: vet the new file"


def test_mean_elapsed_and_counts(tmp_path):
    led = Ledger(tmp_path / "l.sqlite")
    for tic, s in ((1, 10.0), (2, 30.0)):
        led.claim("fast", tic, "", "r1")
        led.finish("fast", tic, {"outcome": "none", "elapsed_s": s})
    assert led.mean_elapsed("fast") == 20.0
    assert led.counts("r1") == {"fast": {"done": 2}}

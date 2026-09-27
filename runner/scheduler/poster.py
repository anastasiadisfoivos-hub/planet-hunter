"""Posts to the API's live monitor: POST /monitor/progress with `Authorization: Bearer PH_INGEST_TOKEN` and
{run_id, run_started_at, shard, done, total, star?} (api/src/api/routes/monitor.py).

Shards: one per queue (fast 0, deep 1, faint 2), so the run's progress is the sum of the three. A post goes out
after every finished star (with its monitor record) and as a heartbeat every PH_HEARTBEAT_S, which keeps the
monitor "live" while long deep stars run (the API calls a run live while it heard from it within 900 s).

Posting never slows or changes the search: posts go through a bounded queue to one background thread; when the
API is down they fail after a short timeout, are counted, and the star records are dropped (each record is also
on disk in monitor/<tic>.json, and the night's ingest loads those). Progress is cumulative, so the next post
after an outage brings it up to date.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

SHARDS = {"fast": 0, "deep": 1, "faint": 2}
TIMEOUT_S = 10.0
MAX_QUEUED = 500


class Poster:
    def __init__(self, api_url: str | None, token: str | None, run_id: str, run_started_at: datetime,
                 log=print):
        self.url = f"{api_url.rstrip('/')}/monitor/progress" if api_url else None
        self.token = token
        self.run_id = run_id
        self.started = run_started_at.isoformat()
        self.log = log
        self.enabled = bool(self.url and self.token)
        self.stats = {"sent": 0, "failed": 0, "dropped": 0, "stars_sent": 0, "last_ok_at": None,
                      "last_error": None}
        self._q: queue.Queue = queue.Queue(MAX_QUEUED)
        self._progress: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._down_logged = False

    # ---- called from the scheduler --------------------------------------------------------------------------

    def start(self) -> None:
        if self.enabled and self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="poster", daemon=True)
            self._thread.start()
        elif not self.enabled:
            self.log("poster: PH_API_URL or PH_INGEST_TOKEN unset; not posting to the monitor")

    def set_progress(self, queue_name: str, done: int, total: int) -> None:
        with self._lock:
            self._progress[queue_name] = (done, max(total, done))

    def star(self, queue_name: str, record: dict) -> None:
        self._put(("star", queue_name, record))

    def heartbeat(self) -> None:
        self._put(("beat", None, None))

    def close(self, timeout_s: float = 30.0) -> dict:
        """Send what is queued (up to timeout_s), then stop."""
        if self._thread is not None:
            deadline = time.time() + timeout_s
            while not self._q.empty() and time.time() < deadline:
                time.sleep(0.1)
            self._stop.set()
            self._put(("stop", None, None))
            self._thread.join(timeout=max(1.0, deadline - time.time()))
        return dict(self.stats)

    # ---- internals ------------------------------------------------------------------------------------------

    def _put(self, item) -> None:
        if not self.enabled:
            return
        try:
            self._q.put_nowait(item)
        except queue.Full:  # API far behind: drop the oldest, keep the newest
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            self.stats["dropped"] += 1
            try:
                self._q.put_nowait(item)
            except queue.Full:
                self.stats["dropped"] += 1

    def _body(self, queue_name: str, star: dict | None) -> dict:
        with self._lock:
            done, total = self._progress.get(queue_name, (0, 0))
        body = {"run_id": self.run_id, "run_started_at": self.started, "shard": SHARDS.get(queue_name, 9),
                "done": done, "total": total}
        if star is not None:
            body["star"] = star
        return body

    def _loop(self) -> None:
        while True:
            kind, qname, record = self._q.get()
            if kind == "stop":
                return
            if kind == "star":
                ok = self._send(self._body(qname, record))
                if ok:
                    self.stats["stars_sent"] += 1
                else:
                    self.stats["dropped"] += 1
            else:  # heartbeat: every queue's current progress
                with self._lock:
                    names = list(self._progress) or ["fast"]
                for name in names:
                    self._send(self._body(name, None))

    def _send(self, body: dict) -> bool:
        data = json.dumps(body, allow_nan=False, default=str).encode()
        req = urllib.request.Request(self.url, data=data, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {self.token}",
            "User-Agent": "planet-hunter-runner"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                resp.read()
            self.stats["sent"] += 1
            self.stats["last_ok_at"] = time.time()
            if self._down_logged:
                self.log("poster: API reachable again")
                self._down_logged = False
            return True
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode(errors="replace")
            self._fail(f"HTTP {exc.code}: {detail}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self._fail(f"{type(exc).__name__}: {exc}")
        return False

    def _fail(self, why: str) -> None:
        self.stats["failed"] += 1
        self.stats["last_error"] = why
        if not self._down_logged:
            self.log(f"poster: post failed ({why}); dropping and counting until it answers")
            self._down_logged = True

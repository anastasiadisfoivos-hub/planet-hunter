"""Monitor storage, shared by both backends (same hooks as FinderSql).

monitor_runs/_shards/_stars hold the sweeps (the last few, with every star's full record);
monitor_seen/_sectors/_reasons hold each star's latest search forever, for the log, coverage and
stats.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from api.ports import MonitorStar

CELL_DEG = 5  # the coverage grid: 72 x 36 cells of 5 x 5 degrees
_RUN_ORDER = "COALESCE(r.started_at, r.updated_at) DESC, r.updated_at DESC, r.run_id DESC"


def sky_cell(ra: float | None, dec: float | None) -> tuple[int | None, int | None]:
    if ra is None or dec is None or not (math.isfinite(ra) and math.isfinite(dec)):
        return None, None
    cell_ra = int(math.floor((ra % 360.0) / CELL_DEG)) % (360 // CELL_DEG)
    cell_dec = min(int(math.floor((max(-90.0, min(90.0, dec)) + 90.0) / CELL_DEG)),
                   180 // CELL_DEG - 1)  # fmt: skip
    return cell_ra, cell_dec


class MonitorSql:
    # Hooks, supplied by the backend (see FinderSql).
    PH: str
    FOR_UPDATE: str
    NO_LIGHTCURVE: str  # SQL: monitor_stars s's record without its "lightcurve" key
    LIGHTCURVE_F: str  # SQL: monitor_stars s's lightcurve.f (JSON array, or NULL)

    # Runs --------------------------------------------------------------------------------

    def put_monitor_run(
        self, run_id: str, started_at: datetime | None, state: str, at: datetime
    ) -> None:
        """Create or touch a run. A run never goes back from "done" to "running" (a shard's late
        post after the ingest), and the first known start time is kept."""
        self._exec(
            self._sql(
                "INSERT INTO monitor_runs (run_id, started_at, finished_at, state, updated_at)"
                " VALUES (?,?,?,?,?) ON CONFLICT (run_id) DO UPDATE SET"
                " started_at = COALESCE(monitor_runs.started_at, excluded.started_at),"
                " finished_at = COALESCE(monitor_runs.finished_at, excluded.finished_at),"
                " state = CASE WHEN monitor_runs.state = 'done' THEN 'done'"
                " ELSE excluded.state END,"
                " updated_at = excluded.updated_at"
            ),
            (run_id, self._t(started_at), self._t(at) if state == "done" else None, state,
             self._t(at)),
        )  # fmt: skip

    def put_monitor_progress(
        self, run_id: str, shard: int, done: int, total: int, at: datetime
    ) -> None:
        with self.atomic():
            self.put_monitor_run(run_id, None, "running", at)
            self._exec(
                self._sql(
                    "INSERT INTO monitor_shards (run_id, shard, done, total, updated_at)"
                    " VALUES (?,?,?,?,?) ON CONFLICT (run_id, shard) DO UPDATE SET"
                    " done = excluded.done, total = excluded.total,"
                    " updated_at = excluded.updated_at"
                ),
                (run_id, shard, done, total, self._t(at)),
            )

    def _run(self, r: Any) -> dict[str, Any]:
        run_id = r["run_id"]
        shards = self._one(
            self._sql(
                "SELECT COUNT(*) AS n, SUM(done) AS done, SUM(total) AS total"
                " FROM monitor_shards WHERE run_id = ?"
            ),
            (run_id,),
        )
        stars = self.monitor_star_count(run_id)
        if shards["n"]:
            done, total = int(shards["done"] or 0), int(shards["total"] or 0)
            if r["state"] == "done":  # the ingest has every star the shards finished
                done = max(done, stars)
                total = max(total, done)
        else:
            done = total = stars
        return {
            "run_id": run_id,
            "started_at": self._to(r["started_at"]),
            "finished_at": self._to(r["finished_at"]),
            "state": r["state"],
            "updated_at": self._to(r["updated_at"]),
            "done": done,
            "total": total,
            "stars": stars,
        }

    def get_monitor_run(self, run_id: str) -> dict[str, Any] | None:
        r = self._one(self._sql("SELECT * FROM monitor_runs r WHERE r.run_id = ?"), (run_id,))
        return self._run(r) if r else None

    def latest_monitor_run(
        self, state: str | None = None, *, with_stars: bool = False
    ) -> dict[str, Any] | None:
        where, params = [], []
        if state is not None:
            where.append(f"r.state = {self.PH}")
            params.append(state)
        if with_stars:
            where.append("EXISTS (SELECT 1 FROM monitor_stars s WHERE s.run_id = r.run_id)")
        sql = "SELECT * FROM monitor_runs r"
        if where:
            sql += " WHERE " + " AND ".join(where)
        r = self._one(f"{sql} ORDER BY {_RUN_ORDER} LIMIT 1", params)
        return self._run(r) if r else None

    def prune_monitor_runs(self, keep: int) -> int:
        """Delete all but the newest `keep` finished runs (their stars go with them). Running
        runs are never pruned. Returns how many runs were deleted."""
        rows = self._all(f"SELECT r.run_id, r.state FROM monitor_runs r ORDER BY {_RUN_ORDER}")
        done = [r["run_id"] for r in rows if r["state"] == "done"]
        old = done[max(keep, 0) :]
        for run_id in old:
            self._exec(self._sql("DELETE FROM monitor_runs WHERE run_id = ?"), (run_id,))
        return len(old)

    # Stars -------------------------------------------------------------------------------

    def put_monitor_star(self, run_id: str, star: MonitorStar) -> None:
        """Store a run's star, and make it the star's latest search unless a newer one exists."""
        at = self._t(star.searched_at)
        with self.atomic():
            self._exec(
                self._sql(
                    "INSERT INTO monitor_stars (run_id, tic, searched_at, outcome,"
                    " detections_count, record) VALUES (?,?,?,?,?,?)"
                    " ON CONFLICT (run_id, tic) DO UPDATE SET searched_at = excluded.searched_at,"
                    " outcome = excluded.outcome, detections_count = excluded.detections_count,"
                    " record = excluded.record"
                ),
                (run_id, star.tic, at, star.outcome, star.detections_count,
                 self._j(star.record)),
            )  # fmt: skip
            old = self._one(
                self._sql(f"SELECT searched_at FROM monitor_seen WHERE tic = ?{self.FOR_UPDATE}"),
                (star.tic,),
            )
            if old is not None and self._to(old["searched_at"]) > star.searched_at:
                return
            cell_ra, cell_dec = sky_cell(star.ra, star.dec)
            values = (
                run_id, at, star.outcome, star.ra, star.dec, cell_ra, cell_dec,
                star.detections_count, star.candidates_count, star.known_count,
                star.rejected_count, star.tic,
            )  # fmt: skip
            if old is None:
                self._exec(
                    self._sql(
                        "INSERT INTO monitor_seen (run_id, searched_at, outcome, ra_deg, dec_deg,"
                        " cell_ra, cell_dec, detections_count, candidates_count, known_count,"
                        " rejected_count, tic) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                    ),
                    values,
                )
            else:
                self._exec(
                    self._sql(
                        "UPDATE monitor_seen SET run_id = ?, searched_at = ?, outcome = ?,"
                        " ra_deg = ?, dec_deg = ?, cell_ra = ?, cell_dec = ?,"
                        " detections_count = ?, candidates_count = ?, known_count = ?,"
                        " rejected_count = ? WHERE tic = ?"
                    ),
                    values,
                )
            self._exec(self._sql("DELETE FROM monitor_sectors WHERE tic = ?"), (star.tic,))
            for sector in sorted(set(star.sectors)):
                self._exec(
                    self._sql("INSERT INTO monitor_sectors (tic, sector) VALUES (?,?)"),
                    (star.tic, sector),
                )
            self._exec(self._sql("DELETE FROM monitor_reasons WHERE tic = ?"), (star.tic,))
            for reason, n in sorted(star.rejected.items()):
                self._exec(
                    self._sql("INSERT INTO monitor_reasons (tic, reason, n) VALUES (?,?,?)"),
                    (star.tic, reason, n),
                )

    def _star(self, r: Any) -> dict[str, Any] | None:
        return self._jo(r["record"]) if r else None

    def get_monitor_star(self, run_id: str, tic: int) -> dict[str, Any] | None:
        return self._star(self._one(
            self._sql("SELECT record FROM monitor_stars WHERE run_id = ? AND tic = ?"),
            (run_id, tic),
        ))  # fmt: skip

    def latest_monitor_star(self, run_id: str) -> dict[str, Any] | None:
        """The run's most recently searched star (live mode)."""
        return self._star(self._one(
            self._sql(
                "SELECT record FROM monitor_stars WHERE run_id = ?"
                " ORDER BY searched_at DESC, tic DESC LIMIT 1"
            ),
            (run_id,),
        ))  # fmt: skip

    def monitor_star_count(self, run_id: str) -> int:
        r = self._one(
            self._sql("SELECT COUNT(*) AS n FROM monitor_stars WHERE run_id = ?"), (run_id,)
        )
        return int(r["n"])

    def monitor_star_at(self, run_id: str, index: int) -> dict[str, Any] | None:
        """The run's index-th star in search order (replay mode)."""
        return self._star(self._one(
            self._sql(
                "SELECT record FROM monitor_stars WHERE run_id = ?"
                " ORDER BY searched_at, tic LIMIT 1 OFFSET ?"
            ),
            (run_id, index),
        ))  # fmt: skip

    def monitor_next_tic(self, run_id: str, tic: int) -> int | None:
        """The tic after `tic` in the run's search order, wrapping around (the first tic when
        `tic` is the last or not in the run). None when the run has no stars."""
        r = self._one(
            self._sql(
                "SELECT s.tic FROM monitor_stars s"
                " JOIN monitor_stars me ON me.run_id = s.run_id AND me.tic = ?"
                " WHERE s.run_id = ? AND (s.searched_at > me.searched_at"
                " OR (s.searched_at = me.searched_at AND s.tic > me.tic))"
                " ORDER BY s.searched_at, s.tic LIMIT 1"
            ),
            (tic, run_id),
        )
        if r is None:
            r = self._one(
                self._sql(
                    "SELECT tic FROM monitor_stars WHERE run_id = ?"
                    " ORDER BY searched_at, tic LIMIT 1"
                ),
                (run_id,),
            )
        return int(r["tic"]) if r else None

    def monitor_star_latest(self, tic: int) -> dict[str, Any] | None:
        """The star's latest full record still kept (any run), or None."""
        return self._star(self._one(
            self._sql(
                "SELECT record FROM monitor_stars WHERE tic = ?"
                " ORDER BY searched_at DESC, run_id DESC LIMIT 1"
            ),
            (tic,),
        ))  # fmt: skip

    # Log, coverage, stats ----------------------------------------------------------------

    def monitor_log(self, limit: int, *, detail: bool = False) -> list[dict[str, Any]]:
        """Newest searches first. With `detail`, each item's `record` is that search's full
        record without the light curve (None once its run is pruned)."""
        record = f", {self.NO_LIGHTCURVE} AS record" if detail else ""
        join = ""
        if detail:
            join = " LEFT JOIN monitor_stars s ON s.run_id = m.run_id AND s.tic = m.tic"
        rows = self._all(
            self._sql(
                f"SELECT m.tic, m.outcome, m.detections_count, m.searched_at{record}"
                f" FROM monitor_seen m{join} ORDER BY m.searched_at DESC, m.tic DESC LIMIT ?"
            ),
            (limit,),
        )
        items = []
        for r in rows:
            item = {
                "tic": int(r["tic"]),
                "outcome": r["outcome"],
                "detections_count": int(r["detections_count"]),
                "searched_at": self._to(r["searched_at"]),
            }
            if detail:
                item["record"] = self._jo(r["record"])
            items.append(item)
        return items

    def monitor_curves(self) -> list[tuple[int, list[Any]]]:
        """(tic, lightcurve.f) of every star whose latest search's record is still kept."""
        rows = self._all(
            f"SELECT m.tic, {self.LIGHTCURVE_F} AS f FROM monitor_seen m"
            " JOIN monitor_stars s ON s.run_id = m.run_id AND s.tic = m.tic ORDER BY m.tic"
        )
        out = []
        for r in rows:
            f = self._jo(r["f"])
            if isinstance(f, list):
                out.append((int(r["tic"]), f))
        return out

    def monitor_coverage(self) -> dict[str, Any]:
        total = self._one("SELECT COUNT(*) AS n FROM monitor_seen")["n"]
        sectors = self._all(
            "SELECT sector, COUNT(*) AS n FROM monitor_sectors GROUP BY sector ORDER BY sector"
        )
        cells = self._all(
            "SELECT cell_ra, cell_dec, COUNT(*) AS n FROM monitor_seen"
            " WHERE cell_ra IS NOT NULL AND cell_dec IS NOT NULL"
            " GROUP BY cell_ra, cell_dec ORDER BY cell_dec, cell_ra"
        )
        half = CELL_DEG / 2
        # Every star's latest search, one row per (star, sector): grouped here into one list.
        rows = self._all(
            "SELECT m.tic, m.ra_deg, m.dec_deg, m.outcome, x.sector FROM monitor_seen m"
            " LEFT JOIN monitor_sectors x ON x.tic = m.tic ORDER BY m.tic, x.sector"
        )
        stars: list[dict[str, Any]] = []
        for r in rows:
            tic = int(r["tic"])
            if not stars or stars[-1]["tic"] != tic:
                stars.append({"tic": tic, "ra": r["ra_deg"], "dec": r["dec_deg"],
                              "outcome": r["outcome"], "sectors": []})  # fmt: skip
            if r["sector"] is not None:
                stars[-1]["sectors"].append(int(r["sector"]))
        return {
            "stars_searched_total": int(total),
            "by_sector": [{"sector": int(r["sector"]), "stars": int(r["n"])} for r in sectors],
            "cell_deg": CELL_DEG,
            "sky_cells": [
                {
                    "ra": r["cell_ra"] * CELL_DEG + half,
                    "dec": r["cell_dec"] * CELL_DEG - 90 + half,
                    "stars": int(r["n"]),
                }
                for r in cells
            ],
            "stars": stars,
        }

    def monitor_stats(self) -> dict[str, Any]:
        r = self._one(
            "SELECT COUNT(*) AS n, SUM(detections_count) AS signals,"
            " SUM(candidates_count) AS candidates, SUM(known_count) AS known,"
            " SUM(rejected_count) AS rejected FROM monitor_seen"
        )
        reasons = self._all(
            "SELECT reason, SUM(n) AS n FROM monitor_reasons GROUP BY reason ORDER BY reason"
        )
        last = self.latest_monitor_run()
        return {
            "stars_searched": int(r["n"]),
            "signals": int(r["signals"] or 0),
            "candidates": int(r["candidates"] or 0),
            "known": int(r["known"] or 0),
            "rejected": int(r["rejected"] or 0),
            "rejected_by_reason": {x["reason"]: int(x["n"]) for x in reasons},
            "last_run_at": (last["started_at"] or last["updated_at"]) if last else None,
        }

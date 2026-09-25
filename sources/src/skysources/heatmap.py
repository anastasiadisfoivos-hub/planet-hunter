"""build_heatmap(nights=N) -> heatmap.json {generated_at, grid, window, cells[{pix, counts}]}.

Counts are *objects* with Rubin alerts in the window, binned by HEALPix (RING ordering) at their
position, per CatchType. Two no-login sources, because no single broker lists the whole sky fast:

  - static-sky objects: ALeRCE LSST object list (https://api-lsst.alerce.online/object_api),
    top class of its Rubin stamp classifier (SN / AGN / VS). "bogus" is dropped. ALeRCE's own
    "asteroid" class is skipped: it is ~90% of rows (hours of paging) and would double-count
    the known solar-system objects below.
  - known solar-system objects: Fink's SSO bulk file (one download), typed by sso.heuristic_type.

By default the window is the most recent `nights` nights that actually have alerts
(status.latest_observed_window), so a paused survey still gives its last real map. The window
used is written into the JSON as {"window": {"start", "end"}}.

CLI (for the daily GitHub Action):
    uv run skysources-heatmap --nights 3 --out heatmap.json      # latest nights with alerts
    uv run skysources-heatmap --nights 3 --until now             # strictly the last 3 x 24 h
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import astropy.units as u
import numpy as np
from astropy.time import Time
from astropy_healpix import HEALPix

from . import classes, sso
from .http import HOST_MIN_INTERVAL, get_client
from .status import latest_observed_window
from .util import as_utc

log = logging.getLogger("skysources.heatmap")

ALERCE_OBJECTS = "https://api-lsst.alerce.online/object_api/list_objects"
ALERCE_CLASSIFIER = "stamp_classifier_rubin_beta_20260421"
ALERCE_CLASSES = ["SN", "AGN", "VS"]
PAGE_SIZE = 5000
MAX_PAGES_PER_CLASS = 200  # 1M objects: a guard, not an expected size
HOST_MIN_INTERVAL.setdefault("api-lsst.alerce.online", 0.5)

DEFAULT_NSIDE = 32  # 12,288 cells of ~3.4 deg^2 (about half an LSSTCam field)


def build_heatmap(
    nights: int = 3,
    *,
    until: datetime | str = "latest",
    nside: int = DEFAULT_NSIDE,
) -> dict[str, Any]:
    """Heatmap of the latest `nights` nights that have alerts (until="latest"), or of the
    `nights` x 24 h ending at `until` ("now" or a time)."""
    if nights < 1:
        raise ValueError("nights must be >= 1")
    if until == "latest":
        start, end = latest_observed_window(nights)
    else:
        end = datetime.now(UTC) if until == "now" else as_utc(until)
        start = end - timedelta(days=nights)
    m0, m1 = float(Time(start).tai.mjd), float(Time(end).tai.mjd)
    log.info("window %s -> %s (MJD TAI %.4f-%.4f), nside=%d", start, end, m0, m1, nside)

    hp = HEALPix(nside=nside, order="ring")
    counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def add(ra: np.ndarray, dec: np.ndarray, catch: list[str]) -> None:
        if len(ra) == 0:
            return
        pix = hp.lonlat_to_healpix(np.asarray(ra) * u.deg, np.asarray(dec) * u.deg)
        for p, c in zip(pix.tolist(), catch):
            counts[p][c] += 1

    for cls in ALERCE_CLASSES:
        catch = classes.ALERCE_STAMP[cls]
        ra, dec = _alerce_positions(cls, m0, m1)
        add(ra, dec, [catch] * len(ra))
        log.info("ALeRCE %s: %d objects", cls, len(ra))

    seen = sso.sightings(m0, m1)
    add(
        np.array([s.ra_deg for s in seen]),
        np.array([s.dec_deg for s in seen]),
        [sso.heuristic_type(s.designation, s.helio_au) for s in seen],
    )
    log.info("Fink SSO bulk: %d objects", len(seen))

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "grid": f"healpix nside={nside}",
        "window": {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds")},
        "cells": [
            {"pix": p, "counts": dict(sorted(c.items()))} for p, c in sorted(counts.items())
        ],
    }


def _alerce_positions(class_name: str, m0: float, m1: float) -> tuple[np.ndarray, np.ndarray]:
    """Positions of objects whose top stamp class is `class_name`, last seen on/after m0 and
    first seen on/before m1 (i.e. active in the window when m1 is 'now')."""
    ra: list[float] = []
    dec: list[float] = []
    client = get_client()
    for page in range(1, MAX_PAGES_PER_CLASS + 1):
        params = [
            ("survey", "lsst"),
            ("classifier", ALERCE_CLASSIFIER),
            ("class_name", class_name),
            ("ranking", 1),
            ("lastmjd", round(m0, 5)),
            ("firstmjd", 0),
            ("firstmjd", round(m1, 5)),
            ("page_size", PAGE_SIZE),
            ("page", page),
            ("order_by", "oid"),
            ("order_mode", "ASC"),
        ]
        data = client.get_json(ALERCE_OBJECTS, params=params, ttl=6 * 3600)
        for item in data["items"]:
            ra.append(item["meanra"])
            dec.append(item["meandec"])
        if not data.get("has_next"):
            break
    return np.array(ra), np.array(dec)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skysources-heatmap", description=__doc__.split("\n\n")[0])
    ap.add_argument("--nights", type=int, default=3, help="window length in nights (24 h each)")
    ap.add_argument(
        "--until",
        default="latest",
        help="'latest' (default: the latest nights that have alerts), 'now', or an ISO time",
    )
    ap.add_argument("--nside", type=int, default=DEFAULT_NSIDE)
    ap.add_argument("--out", default="heatmap.json", help="output path, or - for stdout")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", stream=sys.stderr)

    t = time.time()
    heat = build_heatmap(args.nights, until=args.until, nside=args.nside)
    text = json.dumps(heat, separators=(",", ":"))
    if args.out == "-":
        sys.stdout.write(text + "\n")
    else:
        Path(args.out).write_text(text + "\n")
    total = sum(sum(c["counts"].values()) for c in heat["cells"])
    log.info("%d cells, %d objects, %d bytes, %.0f s", len(heat["cells"]), total, len(text), time.time() - t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

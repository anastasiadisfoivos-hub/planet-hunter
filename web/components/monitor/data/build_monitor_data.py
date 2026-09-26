"""Build the monitor's mock data (web/public/data/monitor/) from REAL TESS light curves and the real hunt search.

Run with the hunt session's environment (it needs the `hunt` and `hunter` packages and the network):

    cd ~/ph-hunt/hunt && uv run python ~/ph-monitorui/web/components/monitor/data/build_monitor_data.py

What goes in, all real:
  * The five light curves recorded as hunt's offline test fixtures (hunt/tests/data/*.npz).
  * The 2026-09-26 sweep of 200 stars (hunt/out/sweep_final/results/*.json): every star's position, sectors
    and signals, and the time each star's search finished (the result file's modification time).
  * Light curves for a selection of those sweep stars, downloaded again from MAST (the same SPOC products).
  * Four TESS Objects of Interest used as stand-in candidates, since the sweep found no new candidate.
    They are listed as such everywhere they appear.
  * Gaia DR3 (RUWE, neighbours, variability flag) and the AAVSO VSX catalogue for the candidates' vetting block.

Every star is searched again here with hunt.analyse so each detection carries hunt's own reason in words.
Light curves are normalised per sector (divided by the sector median) and binned to 10 minutes: the shape is
the star's, only the resolution is reduced to keep the files small. Nothing is simulated.
"""

from __future__ import annotations

import json
import math
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

HUNT = Path.home() / "ph-hunt" / "hunt"
sys.path.insert(0, str(HUNT / "tests"))

from hunt import analyse, catalogs, lightcurve  # noqa: E402
from hunt import checks as chk  # noqa: E402
from hunt.catalogs import Catalogue  # noqa: E402
from hunt.lightcurve import StarLC  # noqa: E402
from hunt.stars import Star  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / "public" / "data" / "monitor"
SWEEP = HUNT / "out" / "sweep_final" / "results"
SWEEP_SUMMARY = HUNT / "results" / "sweep_2026-09-26_top200_summary.json"
FIXTURES = HUNT / "tests" / "data"
PIXELS = Path(__file__).resolve().parents[2] / "finder" / "data" / "pixels-toi4257-s0062.json"
BIN_MIN = 10

# Sweep stars whose light curves the monitor replays: the strongest signals the checks rejected, plus WASP-18
# (its known planet masked) and two with nothing above the noise.
SWEEP_REPLAY = [113233475, 1353822, 140478472, 201604954, 209366972, 7723060, 166348393, 12931952,
                88365885, 214517415, 100100827]
# Stand-in candidates: real TOI signals, found again by hunt when the known-object lists are switched off.
# The replay's order: outcomes interleaved, so a viewer sees known, rejected and quiet stars early.
REPLAY_ORDER = [415739607, 113233475, 100100827, 408512382, 1353822, 254113311, 175516858, 140478472, 20318757, 201604954,
                76923707, 209366972, 75208638, 7723060, 12931952, 26880783, 166348393, 88365885, 214517415]
STAND_INS = {415739607: "TOI-7303.01", 75208638: "TOI-4257.01", 20318757: "TOI-1027.01", 88863718: "TOI-1001.01",
             26880783: "TOI-1364.01", 146172354: "TOI-1036.01"}


# ---------- helpers ----------

def iso_from_btjd(t: float) -> str:
    unix = (t + 2457000 - 2440587.5) * 86400
    return datetime.fromtimestamp(unix, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def binned_curve(lc: StarLC) -> dict:
    ts, fs = [], []
    for s in sorted(set(lc.sector.tolist())):
        m = (lc.sector == s) & np.isfinite(lc.flux)
        t, f = lc.time[m], lc.flux[m].astype(float)
        if len(t) < 10:
            continue
        f = f / np.nanmedian(f)
        w = BIN_MIN / 1440
        k = np.floor((t - t[0]) / w).astype(int)
        cnt = np.bincount(k)
        ok = cnt >= 2
        bt = (np.bincount(k, weights=t) / np.maximum(cnt, 1))[ok]
        bf = (np.bincount(k, weights=f) / np.maximum(cnt, 1))[ok]
        ts.append(bt)
        fs.append(bf)
    t, f = np.concatenate(ts), np.concatenate(fs)
    return {"t": [round(float(x), 4) for x in t], "f": [round(float(x), 5) for x in f]}


def measured_depth_ppm(lc: StarLC, period: float, t0: float, dur_d: float) -> float | None:
    ph = ((lc.time - t0) / period + 0.5) % 1 - 0.5
    inn = np.abs(ph * period) < dur_d / 4
    out = (np.abs(ph * period) > dur_d) & (np.abs(ph * period) < 3 * dur_d)
    if inn.sum() < 5 or out.sum() < 5:
        return None
    d = 1 - np.nanmedian(lc.flux[inn]) / np.nanmedian(lc.flux[out])
    return round(float(d) * 1e6, 1)


def kind_of(n_transits: int) -> str:
    return "periodic" if n_transits >= 3 else "duo" if n_transits == 2 else "single"


def reason_for(rec: dict, checks: list[chk.Check]) -> str:
    stage = rec["failed_stage"]
    if stage is None:
        return "Passed every check and is on none of the lists of known planets, candidates and binaries we checked."
    if stage == "snr":
        return f"Too faint: the dip stands {rec['snr']:.1f} times above the noise; the search needs 10."
    if stage == "sde":
        return f"Does not stand out from other periods in the search (SDE {rec['sde']:.1f}; the search needs 9)."
    if stage == "transits":
        return f"Only {rec['n_transits']} dips; the search needs at least 3 on one period."
    if stage in ("known", "neighbour"):
        names = ", ".join(rec["known_names"][:2]) or "a listed object"
        where = "on this star" if stage == "known" else "on a neighbouring star"
        return f"Already known {where}: {names}."
    failed = [c for c in checks if c.passed is False]
    return failed[0].reason if failed else "Failed the checks."


def run(star: Star, lc: StarLC, cat: Catalogue | None, list_kind: str):
    captured: list[list[chk.Check]] = []
    orig = chk.run_all

    def spy(*a, **k):
        out = orig(*a, **k)
        captured.append(out[0])
        return out

    analyse.chk.run_all = spy
    try:
        res = analyse.analyse(star, lc, cat, list_kind)
    finally:
        analyse.chk.run_all = orig
    return res, captured


def detections(res, captured, lc: StarLC, cat: Catalogue) -> list[dict]:
    from hunter.known import match_period

    out = []
    # One known object can sit on several lists (WASP-18 b, TOI-185.01, the EB catalogue): one detection each,
    # named by every list. Where hunt re-located the dips in the data (TTVs), use that ephemeris.
    groups: list[list[dict]] = []
    for m in res.masked_known:
        g = next((g for g in groups if match_period(m["period_d"], g[0]["period_d"]) == "same period"), None)
        if g is None:
            groups.append([m])
        else:
            g.append(m)
    for g in groups:
        listed_entries = [m for m in g if "(as found in the data)" not in m["name"]]
        if not listed_entries:
            continue
        names = [m["name"] for m in listed_entries]
        listed = next((e for e in cat.on_star(res.tic) if e.name == names[0]), None)
        dur_h = (listed.duration_h if listed and listed.duration_h else listed_entries[0]["mask_half_width_h"])
        # the ephemeris that puts the deepest dip in the data: the list's, or where hunt re-found it (TTVs)
        tries = [(measured_depth_ppm(lc, m["period_d"], m["t0_btjd"], dur_h / 24) or -1e9, m) for m in g]
        depth, eph = max(tries, key=lambda x: x[0])
        also = f" (also listed as {', '.join(names[1:])})" if len(names) > 1 else ""
        out.append({"t0": eph["t0_btjd"], "duration_h": round(dur_h, 3),
                    "depth_ppm": depth if depth and depth > 0 else None,
                    "period_d": eph["period_d"], "kind": "periodic", "outcome": "known",
                    "reason": f"Already known: {names[0]}{also}. Its dips were masked before the search."})
    for rec, checks in zip(res.signals, captured):
        stage = rec["failed_stage"]
        outcome = "candidate" if stage is None else "known" if stage in ("known", "neighbour") else "rejected"
        kind = kind_of(rec["n_transits"])
        out.append({"t0": rec["t0_btjd"], "duration_h": rec["duration_h"], "depth_ppm": rec["depth_ppm"],
                    "period_d": rec["period_d"] if kind != "single" else None, "kind": kind,
                    "outcome": outcome, "reason": reason_for(rec, checks),
                    # extra numbers the dossier and log may show; not part of the monitor contract
                    "snr": rec["snr"], "sde": rec["sde"], "n_transits": rec["n_transits"],
                    "failed_checks": rec["failed_checks"]})
    return out


def star_outcome(dets: list[dict]) -> str:
    kinds = {d["outcome"] for d in dets}
    for o in ("candidate", "known", "rejected"):
        if o in kinds:
            return o
    return "none"


def star_record(star: Star, lc: StarLC | None, sectors: list[int], dets: list[dict], searched_at: str,
                observed: tuple[str, str] | None) -> dict:
    return {"tic": star.tic, "tmag": star.tmag, "teff": star.teff, "radius_rsun": star.rad,
            "ra": round(star.ra, 5), "dec": round(star.dec, 5), "sectors": sectors,
            "observed_from": observed[0] if observed else None, "observed_to": observed[1] if observed else None,
            "lightcurve": binned_curve(lc) if lc is not None else None,
            "detections": dets, "outcome": star_outcome(dets), "searched_at": searched_at}


def observed_of(lc: StarLC) -> tuple[str, str]:
    return iso_from_btjd(float(lc.time.min())), iso_from_btjd(float(lc.time.max()))


# ---------- Gaia and VSX for the vetting block ----------

def gaia_block(ra: float, dec: float, depth_ppm: float) -> dict:
    from astroquery.gaia import Gaia

    q = f"""SELECT source_id, ra, dec, phot_g_mean_mag, ruwe, non_single_star, phot_variable_flag,
              DISTANCE(POINT({ra}, {dec}), POINT(ra, dec)) * 3600 AS sep
            FROM gaiadr3.gaia_source
            WHERE 1 = CONTAINS(POINT({ra}, {dec}), CIRCLE(ra, dec, {42 / 3600}))
            ORDER BY sep"""
    rows = Gaia.launch_job(q).get_results()
    rows = [dict(zip(rows.colnames, r)) for r in rows]
    tgt, rest = rows[0], rows[1:]
    g0 = float(tgt["phot_g_mean_mag"])
    neigh = []
    for r in rest:
        g = float(r["phot_g_mean_mag"]) if r["phot_g_mean_mag"] is not None and not np.ma.is_masked(r["phot_g_mean_mag"]) else None
        if g is None:
            continue
        need = depth_ppm * 1e-6 * (1 + 10 ** (0.4 * (g - g0)))  # eclipse depth the neighbour would need
        neigh.append({"gaia_id": str(r["source_id"]), "sep_arcsec": round(float(r["sep"]), 1), "gmag": round(g, 2),
                      "can_mimic": bool(need < 1.0), "needed_depth": round(float(min(need, 9.99)), 4)})
    ruwe = None if np.ma.is_masked(tgt["ruwe"]) else round(float(tgt["ruwe"]), 3)
    nss = 0 if np.ma.is_masked(tgt["non_single_star"]) else int(tgt["non_single_star"])
    return {"ruwe": ruwe, "neighbours": neigh[:8], "binary_hint": bool((ruwe or 0) > 1.4 or nss > 0),
            "gaia_id": str(tgt["source_id"]), "gaia_variable": str(tgt["phot_variable_flag"]) == "VARIABLE"}


def vsx_match(ra: float, dec: float) -> dict | None:
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astroquery.vizier import Vizier

    t = Vizier(columns=["Name", "Type", "Period", "_r"]).query_region(
        SkyCoord(ra * u.deg, dec * u.deg), radius=30 * u.arcsec, catalog="B/vsx/vsx")
    if not t:
        return None
    r = t[0][0]
    return {"name": str(r["Name"]), "type": str(r["Type"]), "sep_arcsec": round(float(r["_r"]) * 60, 1)
            if float(r["_r"]) < 1 else round(float(r["_r"]), 1),
            "period_d": None if np.ma.is_masked(r["Period"]) else float(r["Period"])}


def pixel_vet_toi4257() -> dict:
    """The real PIXELS run on TOI-4257 (sector 62), turned into the PixelVet shape the dossier reads."""
    p = json.loads(PIXELS.read_text())
    tgt = next(m for m in p["markers"] if m["kind"] == "target")
    c = p["centroid"]
    dx, dy = c["x"] - tgt["x"], c["y"] - tgt["y"]
    off_px = math.hypot(dx, dy)
    sig_px = math.sqrt((c["cov_px"][0][0] + c["cov_px"][1][1]) / 2)
    off = round(off_px * p["pixel_scale_arcsec"], 1)
    nearest = min((m for m in p["markers"] if m["kind"] != "target"),
                  key=lambda m: math.hypot(m["x"] - c["x"], m["y"] - c["y"]))
    return {
        "verdict": "off target",
        "reason": (f"the light lost during the dip comes from {off}″ away from the target ({off_px / sig_px:.0f}σ), "
                   f"closest to Gaia DR3 {nearest['gaia_id']} (G={nearest['gmag']:.1f})"),
        "on_target_probability": None,
        "centroid_offset_arcsec": off,
        "offset_sigma": round(off_px / sig_px, 1),
        "suspect_neighbours": [{"gaia_id": nearest["gaia_id"], "sep_arcsec": round(math.hypot(nearest["x"] - tgt["x"], nearest["y"] - tgt["y"]) * p["pixel_scale_arcsec"], 1),
                                "gmag": nearest["gmag"], "needed_depth": nearest.get("needed_depth")}],
        "images": {"out_of_transit": p["out_of_transit"], "difference": p["difference"],
                   "markers": p["markers"], "centroid": {"x": c["x"], "y": c["y"]}, "sector": p["sector"],
                   "pixel_scale_arcsec": p["pixel_scale_arcsec"], "compass": p["compass"]},
    }


# ---------- main ----------

def main() -> None:
    for sub in ("stars", "candidates"):
        for old in (OUT / sub).glob("*.json"):
            old.unlink()
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    cat = catalogs.load()
    built_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    # 1. the sweep: every star in the log, light curves fetched for dates (and kept for the replay set)
    sweep = {}
    for f in sorted(SWEEP.glob("*.json")):
        d = json.loads(f.read_text())
        d["_searched_at"] = datetime.fromtimestamp(f.stat().st_mtime, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        sweep[d["tic"]] = d

    def fetch(tic):
        try:
            return tic, lightcurve.fetch(tic, max_sectors=3)
        except Exception as e:  # noqa: BLE001
            print("fetch failed", tic, e)
            return tic, None

    with ThreadPoolExecutor(4) as ex:
        lcs = dict(ex.map(fetch, list(sweep)))
    print("fetched", sum(v is not None for v in lcs.values()), "of", len(sweep))

    log, replay = [], []
    for tic, d in sweep.items():
        star = Star.from_row(d["star"])
        lc = lcs.get(tic)
        if tic in SWEEP_REPLAY and lc is not None:
            res, captured = run(star, lc, cat, d["list"])
            dets = detections(res, captured, lc, cat)
            rec = star_record(star, lc, lc.sectors, dets, d["_searched_at"], observed_of(lc))
            rec["source"] = "sweep-2026-09-26"
            (OUT / "stars" / f"{tic}.json").write_text(json.dumps(rec, separators=(",", ":")))
            replay.append(tic)
        else:
            dets = []
            for s in d["signals"]:
                kind = kind_of(s["n_transits"])
                stage = s["failed_stage"]
                dets.append({"t0": s["t0_btjd"], "duration_h": s["duration_h"], "depth_ppm": s["depth_ppm"],
                             "period_d": s["period_d"] if kind != "single" else None, "kind": kind,
                             "outcome": "candidate" if stage is None else "known" if stage in ("known", "neighbour") else "rejected",
                             "reason": reason_for(s, []) if stage != "checks" else
                             "Failed the checks: " + ", ".join(c.replace("_", " ") for c in s["failed_checks"]) + ".",
                             "snr": s["snr"], "sde": s["sde"], "n_transits": s["n_transits"], "failed_checks": s["failed_checks"]})
            rec = star_record(star, None, d["sectors"], dets, d["_searched_at"], observed_of(lc) if lc is not None else None)
            rec["source"] = "sweep-2026-09-26"
        rec_log = {k: v for k, v in rec.items() if k != "lightcurve"}
        log.append(rec_log)

    # 2. the hunt test fixtures (searched here, at build time)
    fixtures = [(415739607, "A"), (408512382, "A"), (175516858, "A"), (254113311, "B"), (76923707, "B")]
    for tic, lk in fixtures:
        lc, meta = StarLC.load(FIXTURES / f"{tic}.npz")
        star = Star.from_row(meta["star"])
        res, captured = run(star, lc, cat, lk)
        dets = detections(res, captured, lc, cat)
        rec = star_record(star, lc, lc.sectors, dets, built_at, observed_of(lc))
        rec["source"] = "hunt-test-fixture"
        (OUT / "stars" / f"{tic}.json").write_text(json.dumps(rec, separators=(",", ":")))
        if tic not in sweep:  # a fixture star the sweep also searched keeps the sweep's record in the log
            log.append({k: v for k, v in rec.items() if k != "lightcurve"})
        replay.append(tic)

    # 3. stand-in candidates: real TOIs, searched with the known-object lists switched off
    cands = []
    for tic, toi in STAND_INS.items():
        if (FIXTURES / f"{tic}.npz").exists():
            lc, meta = StarLC.load(FIXTURES / f"{tic}.npz")
            star = Star.from_row(meta["star"])
        else:
            from hunt import stars
            star = stars.star(tic)
            lc = lightcurve.fetch(tic, max_sectors=3)
        res, captured = run(star, lc, Catalogue([]), "A")
        if not res.candidates:
            print("no candidate for", tic, toi, [s["failed_stage"] for s in res.signals])
            continue
        c = res.candidates[0]
        listed = next((e for e in cat.on_star(tic) if e.name == toi), None)
        c["id"] = f"tic{tic}-01"
        c["name"] = None
        # FINDER's Candidate shape: the best radius as a number, the range as radius_low/high
        c["radius_rjup"] = c.pop("radius_rjup_best")
        # known lists as they really stand for this signal (the search ran with them off)
        from hunter.known import match_period
        hits = [e for e in cat.on_star(tic) if e.period and match_period(c["period_d"], e.period)]
        on = {k: next((e.name for e in hits if e.kind == k), None) for k in ("confirmed", "toi", "ctoi", "eb")}
        c["known_lists"] = {k: {"matched": v is not None, "id": v} for k, v in on.items()}
        c["stand_in"] = {"name": toi, "disposition": listed.disposition if listed else None,
                         "note": f"This is {toi}, already a TESS Object of Interest"
                                 + (f" (ExoFOP disposition {listed.disposition})" if listed else "")
                                 + ". The live search would file it as already known; it is shown here as a stand-in "
                                   "because the 2026-09-26 search found no new candidate."}
        try:
            gaia = gaia_block(star.ra, star.dec, c["depth_ppm"])
        except Exception as e:  # noqa: BLE001
            print("gaia failed", tic, e)
            gaia = {"ruwe": None, "neighbours": [], "binary_hint": False, "gaia_id": None, "gaia_variable": False}
        try:
            vsx = vsx_match(star.ra, star.dec)
        except Exception as e:  # noqa: BLE001
            print("vsx failed", tic, e)
            vsx = None
        mimic = [n for n in gaia["neighbours"] if n["can_mimic"]]
        failed = [ch for ch in c["checks"] if ch["passed"] is False]
        reasons = []
        if failed:
            reasons.append(f"{len(failed)} of hunt's checks failed: " + ", ".join(ch["name"].replace("_", " ") for ch in failed) + ".")
        else:
            reasons.append("Passed all of hunt's checks.")
        if gaia["binary_hint"]:
            reasons.append(f"Gaia hints the star may be a binary (RUWE {gaia['ruwe']}).")
        elif gaia["ruwe"] is not None:
            reasons.append(f"Gaia sees a single, well-behaved star (RUWE {gaia['ruwe']}).")
        if mimic:
            reasons.append(f"{len(mimic)} Gaia neighbour{'s' if len(mimic) > 1 else ''} within 42″ could be bright enough to fake the dip.")
        if vsx:
            reasons.append(f"Listed in VSX as {vsx['name']} ({vsx['type']}).")
        pixels = pixel_vet_toi4257() if tic == 75208638 else None
        if pixels:
            reasons.append("The pixel check puts the dip on a neighbouring star.")
        reasons.append("LEO and TRICERATOPS have not been run on it yet.")
        verdict = ("likely false positive" if (pixels and pixels["verdict"] == "off target") or failed or gaia["binary_hint"]
                   else "needs follow-up")
        c["vetting"] = {
            "leo": {"ran": False, "passed": None, "flags": []},
            "triceratops": {"ran": False, "fpp": None, "nfpp": None},
            "gaia": {"ruwe": gaia["ruwe"], "neighbours": gaia["neighbours"], "binary_hint": gaia["binary_hint"],
                     "gaia_id": gaia["gaia_id"]},
            "variability": {"vsx_match": vsx, "gaia_variable": gaia["gaia_variable"]},
            "summary": {"verdict": verdict, "reasons": reasons},
        }
        c["created_at"] = built_at
        cands.append((c, pixels, star))
        # the stand-in's star also goes in the replay, searched the way the live search would: with the lists on,
        # so the monitor shows it as already known, never as a new candidate
        rec_path = OUT / "stars" / f"{tic}.json"
        if tic not in replay:
            res_k, captured_k = run(star, lc, cat, "A")
            dets = detections(res_k, captured_k, lc, cat)
            rec = star_record(star, lc, lc.sectors, dets, built_at, observed_of(lc))
            rec["source"] = "stand-in-toi"
            rec_path.write_text(json.dumps(rec, separators=(",", ":")))
            log.append({k: v for k, v in rec.items() if k != "lightcurve"})
            replay.append(tic)

    # 4. candidate list and reports (FINDER shapes + vetting); votes start at zero: there are no real votes yet
    rows = []
    for c, pixels, star in cands:
        votes = {"planet": 0, "fake": 0, "unsure": 0, "my_vote": None}
        report = {"candidate": c, "pixels": pixels, "votes": votes}
        (OUT / "candidates" / f"{c['id']}.json").write_text(json.dumps(report, separators=(",", ":")))
        row = {k: v for k, v in c.items() if k not in ("folded", "folded_zoom", "unfolded", "checks")}
        row.update({"checks_passed": sum(ch["passed"] is True for ch in c["checks"]),
                    "checks_total": sum(ch["passed"] is not None for ch in c["checks"]),
                    "pixel_verdict": pixels["verdict"] if pixels else None, "votes": votes,
                    "verdict": c["vetting"]["summary"]["verdict"]})
        rows.append(row)
    (OUT / "candidates" / "index.json").write_text(json.dumps({"run_at": built_at, "candidates": rows}, separators=(",", ":")))

    # 5. log, coverage, stats
    log.sort(key=lambda r: r["searched_at"], reverse=True)
    (OUT / "log.json").write_text(json.dumps({"stars": log}, separators=(",", ":")))
    cov = [{"tic": r["tic"], "ra": r["ra"], "dec": r["dec"], "outcome": r["outcome"], "sectors": r["sectors"]} for r in log]
    (OUT / "coverage.json").write_text(json.dumps({"stars": cov}, separators=(",", ":")))
    summ = json.loads(SWEEP_SUMMARY.read_text())["funnel"]
    stats = {"since": min(r["searched_at"] for r in log), "updated_at": max(r["searched_at"] for r in log),
             "stars_searched": len(log), "signals": sum(len(r["detections"]) for r in log),
             "candidates": 0, "rejected": sum(d["outcome"] == "rejected" for r in log for d in r["detections"]),
             "known": sum(d["outcome"] == "known" for r in log for d in r["detections"]),
             "sweep_2026_09_26": summ}
    (OUT / "stats.json").write_text(json.dumps(stats, indent=1))
    sens = json.loads((HUNT / "results" / "sensitivity.json").read_text())
    re_, pe = sens["grid"]["radius_edges_rearth"], sens["grid"]["period_edges_d"]
    cell = {(tuple(b["radius_rearth"]), tuple(b["period_d"])): b for b in sens["bins"]}
    grid = [[cell.get((tuple(re_[i:i + 2]), tuple(pe[j:j + 2]))) for j in range(len(pe) - 1)] for i in range(len(re_) - 1)]
    (OUT / "sensitivity.json").write_text(json.dumps({
        "run_at": sens["created_at"].replace("+00:00", "Z"), "stars_used": sens["n_stars"],
        "radius_edges_rearth": re_, "period_edges_d": pe,
        "recovery_pct": [[None if c is None else round(c["recovery_fraction"] * 100, 1) for c in row] for row in grid],
        "n_injected": [[0 if c is None else c["n_injected"] for c in row] for row in grid],
        "definition": sens["definition"], "overall_recovery_pct": round(sens["overall_recovery_fraction"] * 100, 1),
    }, indent=1))
    replay.sort(key=lambda t: REPLAY_ORDER.index(t) if t in REPLAY_ORDER else len(REPLAY_ORDER))
    (OUT / "replay.json").write_text(json.dumps({"built_at": built_at, "order": replay}))
    print("replay", len(replay), "log", len(log), "candidates", len(cands))


if __name__ == "__main__":
    main()

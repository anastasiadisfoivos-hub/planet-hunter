"""Build one REAL event per EventType from public sources, find its pictures live, and record
every answer so the tests can replay them offline.

    uv run --group examples python scripts/examples.py            # network, ~5 min
    uv run --group examples python scripts/examples.py --reuse-events  # same events, re-find pictures
    uv run --group examples python scripts/examples.py --report   # just rewrite EXAMPLES.md

Writes tests/fixtures/example_events.json (input, contract shape),
tests/fixtures/example_pictures.json (what pictures_for returned), tests/fixtures/http/examples.json
(recorded answers) and EXAMPLES.md (the table in the report).

The event builders here stand in for the EVENTS package only to get real inputs; they fill the
contract fields loosely (confidence etc.). What matters to this package is type, location,
observed_at and raw.
"""

from __future__ import annotations

import io
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from recording import FIXTURES, recording

from skypictures import Stats, pictures_for
from skypictures.cutouts import LSST_API, ZTF_API

UA = {"User-Agent": "planet-hunter-skypictures/0.1 (examples)"}
http = httpx.Client(timeout=180, headers=UA, follow_redirects=True)
NOW = datetime.now(UTC)
EVENTS_OUT = FIXTURES / "example_events.json"
PICTURES_OUT = FIXTURES / "example_pictures.json"


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def jd_to_iso(jd: float) -> str:
    return iso(datetime(1970, 1, 1, tzinfo=UTC) + timedelta(days=jd - 2440587.5))


def mjd_to_iso(mjd: float) -> str:
    return jd_to_iso(mjd + 2400000.5)


def event(id, type, title, summary, source, source_url, observed_at, location, raw, mag=None, conf=1.0,
          basis="reported by the source") -> dict:
    return {"id": id, "type": type, "title": title, "summary": summary, "source": source,
            "source_url": source_url, "observed_at": observed_at, "reported_at": iso(NOW),
            "location": location, "confidence": conf, "confidence_basis": basis, "brightness_mag": mag,
            "images": [], "raw": raw}


def sky(ra, dec, err_deg=0.0):
    return {"frame": "sky", "ra_deg": ra, "dec_deg": dec, "error_deg": err_deg}


# -- Rubin via Fink LSST ------------------------------------------------------------------------

def rubin_tns() -> list[dict]:
    cols = "r:diaObjectId,r:diaSourceId,r:ra,r:dec,r:midpointMjdTai,r:band,r:psfFlux,f:xm_tns_fullname,f:xm_tns_type"
    r = http.get(f"{LSST_API}/tags", params={"tag": "in_tns", "n": 200, "columns": cols})
    return r.json()


def rubin_event(row: dict, type_: str, label: str) -> dict:
    name = row["f:xm_tns_fullname"]
    return event(
        f"rubin:obj:{row['r:diaObjectId']}", type_, f"{name} ({label})",
        f"Rubin/LSST alert matched to TNS {name}.", "Rubin/LSST via Fink",
        f"https://lsst.fink-portal.org/{row['r:diaObjectId']}", mjd_to_iso(row["r:midpointMjdTai"]),
        sky(row["r:ra"], row["r:dec"], 0.1 / 3600), {**row, "latest_diaSourceId": str(row["r:diaSourceId"])})


# -- ZTF via Fink ZTF ---------------------------------------------------------------------------

def ztf_latest(cls: str) -> dict:
    cols = "i:objectId,i:candid,i:ra,i:dec,i:jd,i:magpsf,i:fid,d:tns,i:ssnamenr"
    rows = http.get(f"{ZTF_API}/latests", params={"class": cls, "n": 1, "columns": cols}).json()
    return rows[0]


def ztf_event(cls: str, type_: str, label: str, conf=1.0) -> dict:
    row = ztf_latest(cls)
    oid = row["i:objectId"]
    return event(f"ztf:{oid}", type_, f"{oid} ({label})", f"ZTF alert classified by Fink as {cls}.",
                 "ZTF via Fink", f"https://fink-portal.org/{oid}", jd_to_iso(row["i:jd"]),
                 sky(row["i:ra"], row["i:dec"], 0.3 / 3600), row, mag=row["i:magpsf"], conf=conf,
                 basis=f"Fink class '{cls}'")


# -- JPL ----------------------------------------------------------------------------------------

def horizons_radec(command: str, t: datetime) -> tuple[float, float]:
    q = {"format": "json", "COMMAND": f"'{command}'", "EPHEM_TYPE": "OBSERVER", "CENTER": "'500@399'",
         "START_TIME": f"'{t:%Y-%m-%d %H:%M}'", "STOP_TIME": f"'{t + timedelta(minutes=1):%Y-%m-%d %H:%M}'",
         "STEP_SIZE": "'1m'", "QUANTITIES": "'1'", "ANG_FORMAT": "DEG", "OBJ_DATA": "NO"}
    res = http.get("https://ssd.jpl.nasa.gov/api/horizons.api", params=q).json()["result"]
    line = res.split("$$SOE")[1].strip().splitlines()[0]
    nums = re.findall(r"-?\d+\.\d+", line.split(None, 2)[2])
    return float(nums[0]), float(nums[1])


def jpl_object(type_: str, command: str, name: str, summary: str, url: str) -> dict:
    t = NOW.replace(minute=0, second=0, microsecond=0)
    ra, dec = horizons_radec(command, t)
    return event(f"jpl:{name}", type_, name, summary, "JPL Horizons", url, iso(t), sky(ra, dec, 1 / 3600),
                 {"horizons_command": command, "ra": ra, "dec": dec})


def neo() -> dict:
    d = http.get("https://ssd-api.jpl.nasa.gov/cad.api",
                 params={"date-min": f"{NOW:%Y-%m-%d}", "date-max": f"{NOW + timedelta(days=10):%Y-%m-%d}",
                         "dist-max": "0.02", "sort": "dist"}).json()
    row = dict(zip(d["fields"], d["data"][0]))
    return jpl_object("near_earth_object", f"DES={row['des']};", row["des"],
                      f"Passes Earth at {float(row['dist']) * 389.2:.1f} lunar distances on {row['cd']} TDB.",
                      f"https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr={row['des']}")


# -- high-energy / multi-messenger --------------------------------------------------------------

def grb() -> dict:
    c = http.get("https://gcn.nasa.gov/circulars/45715.json").json()
    m = re.search(r"RA, Dec = ([\d.]+), ([+-][\d.]+)", c["body"])
    err = float(re.search(r"uncertainty of ([\d.]+) arcsec", c["body"]).group(1))
    return event("gcn:GRB260924A", "gamma_ray_burst", "GRB 260924A", c["subject"], "GCN Circular 45715",
                 "https://gcn.nasa.gov/circulars/45715", "2026-09-24T01:13:28Z",
                 sky(float(m.group(1)), float(m.group(2)), err / 3600), {"circular": 45715, "subject": c["subject"]})


def neutrino() -> dict:
    html = http.get("https://gcn.gsfc.nasa.gov/amon_icecube_gold_bronze_events.html").text
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)]
        if len(cells) >= 9 and cells[4] in ("GOLD", "BRONZE"):
            run, rev, date, time_, kind, ra, dec, err90 = cells[:8]
            t = datetime.strptime(f"{date} {time_[:8]}", "%y/%m/%d %H:%M:%S").replace(tzinfo=UTC)
            return event(f"icecube:{run}", "neutrino", f"IceCube {kind.title()} neutrino {run}",
                         f"IceCube {kind} track alert, 90% error radius {err90} arcmin (statistical).",
                         "IceCube via GCN", "https://gcn.gsfc.nasa.gov/amon_icecube_gold_bronze_events.html",
                         iso(t), sky(float(ra), float(dec), float(err90) / 60),
                         {"run_event": run, "rev": rev, "notice": kind})
    raise RuntimeError("no IceCube row")


def gravitational_wave() -> dict:
    import numpy as np
    from astropy.table import Table
    from astropy_healpix import HEALPix

    sid = "S251117dq"
    se = http.get(f"https://gracedb.ligo.org/api/superevents/{sid}/", params={"format": "json"}).json()
    files = http.get(f"https://gracedb.ligo.org/api/superevents/{sid}/files/").json()
    name = next(n for n in ("Bilby.multiorder.fits", "bayestar.multiorder.fits") if n in files)
    t = Table.read(io.BytesIO(http.get(files[name]).content), format="fits")
    uniq = np.asarray(t["UNIQ"])
    order = (np.log2(uniq // 4) // 2).astype(int)
    ipix = uniq - 4 * 4**order
    area = 4 * np.pi / (12 * 4.0**order)  # sr per pixel
    prob = np.asarray(t["PROBDENSITY"]) * area
    best = int(np.argmax(np.asarray(t["PROBDENSITY"])))
    lon, lat = HEALPix(nside=2 ** int(order[best]), order="nested").healpix_to_lonlat([ipix[best]])
    idx = np.argsort(np.asarray(t["PROBDENSITY"]))[::-1]
    area90_deg2 = float(area[idx][np.cumsum(prob[idx]) <= 0.9].sum() * (180 / np.pi) ** 2)
    radius = float(np.sqrt(area90_deg2 / np.pi))
    t0 = datetime(1980, 1, 6, tzinfo=UTC) + timedelta(seconds=float(se["t_0"]) - 18)  # GPS -> UTC (18 leap s)
    return event(f"gracedb:{sid}", "gravitational_wave", sid,
                 f"LIGO/Virgo/KAGRA candidate, 90% area {area90_deg2:.0f} deg²; position = most probable point.",
                 "GraceDB", f"https://gracedb.ligo.org/superevents/{sid}/", iso(t0),
                 sky(float(lon.deg[0]), float(lat.deg[0]), radius),
                 {"far_hz": se["far"], "skymap": name, "area90_deg2": area90_deg2})


# -- Earth and Sun ------------------------------------------------------------------------------

def fireball() -> dict:
    d = http.get("https://ssd-api.jpl.nasa.gov/fireball.api", params={"limit": 1}).json()
    row = dict(zip(d["fields"], d["data"][0]))
    lat = float(row["lat"]) * (1 if row["lat-dir"] == "N" else -1)
    lon = float(row["lon"]) * (1 if row["lon-dir"] == "E" else -1)
    t = datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return event(f"cneos:{row['date']}", "fireball", f"Fireball {row['date']} UTC",
                 f"Radiated energy {row['energy']}e10 J.", "CNEOS", "https://cneos.jpl.nasa.gov/fireballs/",
                 iso(t), {"frame": "earth", "lat_deg": lat, "lon_deg": lon,
                          "alt_km": float(row["alt"]) if row["alt"] else None}, row)


DONKI = "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get"


def donki(kind: str, days: int) -> list[dict]:
    q = {"startDate": f"{NOW - timedelta(days=days):%Y-%m-%d}", "endDate": f"{NOW:%Y-%m-%d}"}
    return http.get(f"{DONKI}/{kind}", params=q).json() or []


def solar_flare() -> dict:
    f = donki("FLR", 30)[-1]
    return event(f"donki:{f['flrID']}", "solar_flare", f"{f['classType']} solar flare",
                 f"Class {f['classType']} flare from {f['sourceLocation']}.", "NASA DONKI", f["link"],
                 f["beginTime"].replace("Z", ":00Z"), {"frame": "sun"}, f)


def cme() -> dict:
    # One LASCO saw, old enough for Helioviewer to have ingested the frames.
    seen = [x for x in donki("CME", 10)
            if any("LASCO" in i["displayName"] for i in x.get("instruments") or [])
            and datetime.strptime(x["startTime"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC) < NOW - timedelta(hours=12)]
    c = seen[-1]
    return event(f"donki:{c['activityID']}", "coronal_mass_ejection", f"CME {c['startTime']}",
                 f"Coronal mass ejection{' from ' + c['sourceLocation'] if c.get('sourceLocation') else ''}.",
                 "NASA DONKI", c["link"],
                 c["startTime"].replace("Z", ":00Z"), {"frame": "sun"}, c)


def storm() -> dict:
    g = donki("GST", 90)[-1]
    kp = max(k["kpIndex"] for k in g["allKpIndex"])
    return event(f"donki:{g['gstID']}", "geomagnetic_storm", f"Geomagnetic storm, Kp {kp:g}",
                 f"Kp reached {kp:g}.", "NASA DONKI", g["link"], g["startTime"].replace("Z", ":00Z"),
                 {"frame": "earth", "lat_deg": None, "lon_deg": None, "alt_km": None}, g)


def build_events() -> list[dict]:
    tns = rubin_tns()
    sn = next(r for r in tns if str(r["f:xm_tns_type"]).startswith("SN"))
    at = next(r for r in tns if r["f:xm_tns_fullname"].startswith("AT") and r["f:xm_tns_type"] in (None, "nan"))
    out = [
        rubin_event(sn, "supernova", f"TNS {sn['f:xm_tns_type']}"),
        ztf_event("(TNS) TDE", "tidal_disruption_event", "TNS TDE"),
        event("tns:AT2017gfo", "kilonova", "AT 2017gfo (GW170817 kilonova)",
              "The only kilonova seen with certainty, in NGC 4993.", "TNS",
              "https://www.wis-tns.org/object/2017gfo", "2017-08-17T12:41:04Z",
              sky(197.450374, -23.381495, 0.1 / 3600), {"tns_name": "AT 2017gfo"}),
        ztf_event("(TNS) Nova", "nova", "TNS nova"),
        ztf_event("(CTA) Blazar high state", "active_galaxy_flare", "blazar in high state", conf=0.8),
        ztf_event("(SIMBAD) RRLyr", "variable_star", "RR Lyrae star"),
        ztf_event("(TNS) M dwarf", "stellar_flare", "flaring M dwarf"),
        ztf_event("Microlensing candidate", "microlensing", "microlensing candidate", conf=0.5),
        ztf_event("Solar System MPC", "asteroid", "known asteroid"),
        neo(),
        jpl_object("comet", "DES=29P;CAP;NOFRAG", "29P/Schwassmann-Wachmann",
                   "Centaur comet famous for frequent outbursts.", "https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr=29P"),
        jpl_object("interstellar_object", "C/2025 N1", "3I/ATLAS", "Third interstellar object, found 2025-07-01.",
                   "https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr=3I"),
        grb(),
        neutrino(),
        gravitational_wave(),
        fireball(),
        solar_flare(),
        cme(),
        storm(),
        rubin_event(at, "unknown", "unclassified TNS transient"),
    ]
    return out


def write_report(events: list[dict], pictures: dict[str, list[dict]], stats: dict) -> None:
    lines = ["# Real examples, one per event type", "",
             (f"Recorded {stats['recorded_at']}. Candidates checked: {stats['candidates']}, "
              f"dropped as dead or blank: {stats['dropped']} ({stats['rate']:.1%})."), ""]
    for ev in events:
        imgs = pictures[ev["id"]]
        lines.append(f"## {ev['type']}: {ev['title']}")
        lines.append(f"`{ev['id']}`, observed {ev['observed_at']}, source [{ev['source']}]({ev['source_url']})")
        lines.append("")
        if not imgs:
            lines.append("_No pictures (see README: what each type gets)._")
        for img in imgs:
            size = f"{img['width']}×{img['height']}" if img["width"] else "?"
            thumb = img["thumb_url"]
            t = f" · [thumb]({thumb})" if thumb and thumb != img["url"] else " · thumb: same image"
            lines.append(f"- **{img['kind']}** {size} [image]({img['url']}){t}  ")
            lines.append(f"  {img['caption']}  ")
            lines.append(f"  _Credit:_ {img['credit']} · _Licence:_ {img['license']}")
        for url, reason in stats["dropped_by_event"].get(ev["id"], []):
            lines.append(f"- dropped ({reason}): {url}")
        lines.append("")
    (ROOT / "EXAMPLES.md").write_text("\n".join(lines))


def main() -> None:
    if "--report" not in sys.argv and "--reuse-events" not in sys.argv:
        events = build_events()
        EVENTS_OUT.write_text(json.dumps(events, indent=1, default=str) + "\n")
    events = json.loads(EVENTS_OUT.read_text())
    pictures: dict[str, list[dict]] = {}
    dropped_by_event: dict[str, list] = {}
    thumb_failures: list[str] = []
    total = Stats()
    if "--report" in sys.argv:
        pictures = json.loads(PICTURES_OUT.read_text())["pictures"]
        meta = json.loads(PICTURES_OUT.read_text())["stats"]
    else:
        with recording("examples"):
            for ev in events:
                s = Stats()
                pictures[ev["id"]] = pictures_for(ev, stats=s)
                # validate() falls back to the full URL when a separate thumbnail fails its check
                thumb_failures += [i["url"] for i in pictures[ev["id"]] if i["thumb_url"] == i["url"]
                                   and "fink-portal" not in i["url"]]
                dropped_by_event[ev["id"]] = s.dropped
                total.candidates += s.candidates
                total.dropped += s.dropped
                total.provider_errors += s.provider_errors
                print(f"{ev['type']:24} {len(pictures[ev['id']])} images, dropped {len(s.dropped)}"
                      + (f"  ERR {s.provider_errors}" if s.provider_errors else ""), file=sys.stderr)
        meta = {"recorded_at": iso(datetime.now(UTC)), "candidates": total.candidates,
                "dropped": len(total.dropped), "rate": len(total.dropped) / max(1, total.candidates),
                "dropped_by_event": dropped_by_event, "provider_errors": total.provider_errors,
                "thumb_failures": thumb_failures}
        PICTURES_OUT.write_text(json.dumps({"stats": meta, "pictures": pictures}, indent=1) + "\n")
    write_report(events, pictures, meta)
    print(f"dead-link rate {meta['rate']:.1%} ({meta['dropped']}/{meta['candidates']})", file=sys.stderr)


if __name__ == "__main__":
    main()

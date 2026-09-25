"""Write the LAB data set into one directory; index.json describes whatever is on disk."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from . import sources
from .atmospheres import build_atmospheres, curated
from .gaia_xp import build_xp
from .hosts import select_hosts
from .hypatia import build_abundances
from .net import Net
from .nist import build_elements
from .sun import build_sun

log = logging.getLogger("skyspectra")
PARTS = ("elements", "sun", "stars", "planets")
STAR_FILE = re.compile(r"^(\d+)\.(abundances|gaia_xp)\.json$")
PLANET_FILE = re.compile(r"^(.+)\.atmosphere\.json$")


SIG_FIGS = 4
# Wavelengths keep their native precision: at 4 significant figures neighbouring solar bins
# (0.08 nm), NIST lines (Na D2 588.995 / D1 589.592) and JWST points (2.72575 / 2.72711 um) merge.
EXACT_KEYS = {"nm", "wavelength_nm", "wavelength_um", "atlas_min_nm", "min_um", "max_um", "window_nm",
              "bandwidth_um"}


def sig(x: float, n: int = SIG_FIGS) -> float:
    return float(f"{x:.{n}g}")


def rounded(doc, exact: bool = False):
    """Round every float to SIG_FIGS significant figures, except under EXACT_KEYS."""
    if isinstance(doc, float):
        return doc if exact else sig(doc)
    if isinstance(doc, list):
        return [rounded(v, exact) for v in doc]
    if isinstance(doc, dict):
        return {k: rounded(v, exact or k in EXACT_KEYS) for k, v in doc.items()}
    return doc


def dump(path: Path, doc) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(rounded(doc), ensure_ascii=False, separators=(",", ":"))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text)
    tmp.replace(path)
    return len(text.encode())


def _replace_all(folder: Path, pattern: re.Pattern, docs: dict[str, dict]) -> None:
    """Write docs (file name -> doc) and delete older files of the same kind that are gone."""
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.iterdir():
        if pattern.match(f.name) and f.name not in docs:
            f.unlink()
    for name, doc in docs.items():
        dump(folder / name, doc)


def build(out: Path, net: Net, tics: list[int] | None = None, parts: tuple[str, ...] = PARTS,
          element_symbols: list[str] | None = None, sun_range: tuple[float, float] | None = None,
          planets: list[str] | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    if "elements" in parts:
        log.info("elements: NIST ASD")
        dump(out / "elements.json", build_elements(net, element_symbols))
    if "sun" in parts:
        log.info("sun: Kurucz 2005 flux atlas")
        dump(out / "sun_spectrum.json", build_sun(net, *(sun_range or ())))
    missing: list[int] = []
    if "stars" in parts or "planets" in parts:
        hosts, missing = select_hosts(net, tics)
        log.info("hosts: %d (%d requested TICs are not archive hosts)", len(hosts), len(missing))
        if "stars" in parts:
            log.info("stars: Hypatia abundances")
            ab = build_abundances(net, hosts)
            log.info("stars: Gaia DR3 XP spectra (~1 s per star on first run)")
            xp = build_xp(net, hosts)
            docs = {f"{t}.abundances.json": d for t, d in ab.items()}
            docs |= {f"{t}.gaia_xp.json": d for t, d in xp.items()}
            _replace_all(out / "stars", STAR_FILE, docs)
        if "planets" in parts:
            log.info("planets: NASA Exoplanet Archive transmission spectra")
            atm = build_atmospheres(net, hosts, planets)
            _replace_all(out / "planets", PLANET_FILE, {f"{s}.atmosphere.json": d for s, d in atm.items()})
            dump(out / "planets" / "detections_curated.json", curated())
    index = make_index(out, requested_not_hosts=missing if tics is not None else None)
    dump(out / "index.json", index)
    return index


def make_index(out: Path, requested_not_hosts: list[int] | None = None) -> dict:
    def entry(p: Path) -> dict:
        return {"path": p.relative_to(out).as_posix(), "bytes": p.stat().st_size}

    files = {}
    for name, key in (("elements.json", "elements"), ("sun_spectrum.json", "sun_spectrum"),
                      ("planets/detections_curated.json", "detections_curated")):
        if (out / name).exists():
            files[key] = entry(out / name)
    stars: dict[str, dict] = {}
    for p in sorted((out / "stars").glob("*.json")) if (out / "stars").exists() else []:
        m = STAR_FILE.match(p.name)
        if m:
            doc = json.loads(p.read_text())
            s = stars.setdefault(m.group(1), {"tic": int(m.group(1)), "name": doc.get("name")})
            s[m.group(2)] = entry(p)
    planets: dict[str, dict] = {}
    for p in sorted((out / "planets").glob("*.json")) if (out / "planets").exists() else []:
        m = PLANET_FILE.match(p.name)
        if m:
            doc = json.loads(p.read_text())
            planets[m.group(1)] = {"planet": doc["planet"], "host": doc.get("host"), "tic": doc.get("tic"),
                                   "has_spectrum": doc.get("spectrum") is not None,
                                   "n_detections": len(doc.get("detections") or []), **entry(p)}
    all_files = [f["bytes"] for f in files.values()]  # (index.json itself excluded)
    all_files += [v["bytes"] for s in stars.values() for k, v in s.items() if isinstance(v, dict)]
    all_files += [p["bytes"] for p in planets.values()]
    index = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "skyspectra (planet-hunter): NIST ASD, Kurucz 2005 solar flux atlas, Hypatia Catalog, "
                  "Gaia DR3 XP, NASA Exoplanet Archive",
        "credit": "See each file's credit; licences per source below.",
        "licence": "Mixed; each file carries its source's licence (see 'sources').",
        "sources": sources.SOURCES,
        "counts": {
            "stars_with_abundances": sum("abundances" in s for s in stars.values()),
            "stars_with_gaia_xp": sum("gaia_xp" in s for s in stars.values()),
            "planets": len(planets),
            "planets_with_spectrum": sum(p["has_spectrum"] for p in planets.values()),
            "planets_with_detections": sum(p["n_detections"] > 0 for p in planets.values()),
        },
        "total_bytes": sum(all_files),
        "files": files,
        "stars": stars,
        "planets": planets,
    }
    if requested_not_hosts is not None:
        index["requested_tics_not_in_archive"] = requested_not_hosts
    return index

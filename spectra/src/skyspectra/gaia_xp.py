"""stars/<tic>.gaia_xp.json: the host star's own low-resolution spectrum from Gaia DR3.

Gaia's BP/RP (XP) spectrophotometers give ~220 million stars a calibrated spectrum. The DR3
"sampled mean spectrum" is that spectrum on a fixed grid of 343 wavelengths, 336 to 1020 nm in
2 nm steps (Montegriffo et al. 2023), flux in W m^-2 nm^-1 at the telescope. We fetch it in
batches from the ESA Gaia Archive DataLink service (public, no login).
"""

from __future__ import annotations

import csv
import io
import logging

from . import sources
from .hosts import Host
from .net import DAY, Net

log = logging.getLogger("skyspectra")
DATALINK = "https://gea.esac.esa.int/data-server/data"
BATCH = 50  # ~1 s per source on the server side
WAVELENGTH_NM = [336.0 + 2.0 * i for i in range(343)]
TTL = 180 * DAY


def _floats(cell: str) -> list[float]:
    return [float(x) for x in cell.strip("()[] ").split(",") if x.strip()]


def parse_xp(text: str) -> dict[int, tuple[list[float], list[float]]]:
    """DataLink CSV (source_id, ..., flux, flux_error) -> source_id -> (flux, flux_error)."""
    if text.lstrip().startswith("<"):
        raise ValueError(f"Gaia DataLink error: {text[:300]}")
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        flux, err = _floats(row["flux"]), _floats(row["flux_error"])
        if len(flux) != len(WAVELENGTH_NM) or len(err) != len(flux):
            raise ValueError(f"source {row['source_id']}: {len(flux)} flux samples, expected 343")
        out[int(row["source_id"])] = (flux, err)
    return out


def fetch_xp(net: Net, source_ids: list[int]) -> dict[int, tuple[list[float], list[float]]]:
    out = {}
    ids = sorted(set(source_ids))
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        log.info("  Gaia XP %d/%d", i, len(ids))
        text = net.text(DATALINK, data={
            "RETRIEVAL_TYPE": "XP_SAMPLED", "ID": ",".join(map(str, chunk)), "FORMAT": "CSV",
            "DATA_STRUCTURE": "RAW", "RELEASE": "Gaia DR3",
        }, ttl=TTL)
        out.update(parse_xp(text))
    return out


def _sig(x: float) -> float:
    return float(f"{x:.5g}")


def build_xp(net: Net, hosts: list[Host]) -> dict[int, dict]:
    """TIC -> XP document, for hosts with a Gaia DR3 id that have a sampled XP spectrum."""
    with_gaia = [h for h in hosts if h.gaia_dr3]
    spectra = fetch_xp(net, [h.gaia_dr3 for h in with_gaia])
    docs = {}
    for h in with_gaia:
        if h.gaia_dr3 not in spectra:
            continue
        flux, err = spectra[h.gaia_dr3]
        docs[h.tic] = {
            "tic": h.tic,
            "name": h.name,
            "gaia_dr3_source_id": str(h.gaia_dr3),
            "wavelength_nm": WAVELENGTH_NM,
            "flux": [_sig(f) for f in flux],
            "flux_error": [_sig(e) for e in err],
            "flux_unit": "W m^-2 nm^-1",
            **sources.meta("gaia"),
        }
    return docs

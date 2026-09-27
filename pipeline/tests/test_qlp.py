"""QLP sectors are read as QLP recommends (hunter.fetch._read_qlp): QUALITY == 0 only, SYS_RM_FLUX when the file
has it, else SAP_FLUX. lightkurve's default read kept QLP's own bad-data bits (29-30), and on sectors 101-104 those
scattered-light cadences folded into fake periodic signals."""

import numpy as np
from astropy.io import fits

from hunter import fetch as fetch_mod

BAD_BITS = (1 << 29) | (1 << 30)  # QLP: scattered light / bad data; not in the SPOC default bitmask (17087)


def qlp_file(path, n=400, sys_rm=True):
    t = 3000.0 + np.arange(n) / 144
    sap = np.full(n, 1000.0)
    q = np.zeros(n, np.int64)
    q[50:70] = 1 << 29  # 20 scattered-light cadences, 5% low
    q[200:205] = 1 << 30
    sap[50:70] *= 0.95
    cols = [fits.Column("TIME", "D", array=t), fits.Column("SAP_FLUX", "D", array=sap),
            fits.Column("QUALITY", "J", array=q), fits.Column("DET_FLUX_ERR", "D", array=np.full(n, 0.5))]
    if sys_rm:
        cols.append(fits.Column("SYS_RM_FLUX", "D", array=np.where(q == 0, 2000.0, 1500.0)))
    fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(cols)]).writeto(path)
    return path


def test_qlp_keeps_only_quality_zero_and_prefers_sys_rm_flux(tmp_path):
    t, f, e, col = fetch_mod._read_qlp(qlp_file(tmp_path / "a.fits"))
    assert col == "sys_rm_flux"
    assert len(t) == 400 - 25, "cadences with bits 29-30 are dropped"
    assert np.all(f == 2000.0) and np.all(e == 0.5)


def test_qlp_without_sys_rm_flux_uses_sap_flux(tmp_path):
    t, f, _, col = fetch_mod._read_qlp(qlp_file(tmp_path / "b.fits", sys_rm=False))
    assert col == "sap_flux"
    assert len(t) == 375 and f.min() == 1000.0, "the 5%-low flagged cadences are gone"


def test_fetch_normalises_clean_qlp_and_names_the_column(tmp_path, monkeypatch):
    path = qlp_file(tmp_path / "c.fits")
    row = {"sector": 101, "author": "QLP", "exptime": 200.0, "uri": "x", "filename": "c.fits"}
    monkeypatch.setattr(fetch_mod, "search_products", lambda tic, refresh=False: [row])
    monkeypatch.setattr(fetch_mod, "_download", lambda r: path)
    lc = fetch_mod.fetch(1, max_sectors=1)
    assert len(lc.time) == 375 and np.allclose(lc.flux, 1.0)
    assert lc.products[0]["flux_column"] == "sys_rm_flux (QUALITY == 0)"

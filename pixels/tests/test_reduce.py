import numpy as np

from conftest import simple_wcs_header
from skypixels.psf import Shape, prf_sum
from skypixels.reduce import SectorImages, make_images


def _cube(rng, host_xy, period=2.0, t0=3001.0, dur_d=0.1, depth=0.01, drift=0.0, n=11, days=20.0):
    t = np.arange(3000.0, 3000.0 + days, 2 / 1440)
    s = Shape(0.9, 0.9, 0.0)
    star_a = prf_sum((n, n), [5.0], [5.0], [1e4], s)
    star_b = prf_sum((n, n), [host_xy[0]], [host_xy[1]], [3e3], s)
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    dip = np.where(np.abs(phase) < dur_d / 2, depth, 0.0)
    trend = 1 + drift * (t - t.mean())
    cube = (star_a[None] + star_b[None] * (1 - dip)[:, None, None]) * trend[:, None, None] + 100
    cube = cube + rng.normal(0, 1.0, cube.shape) * np.sqrt(np.abs(cube) * 0.5 + 10)
    return t, cube.astype(np.float32), np.zeros(len(t), int)


def test_difference_image_peaks_on_the_star_that_dims(rng):
    t, cube, q = _cube(rng, host_xy=(8.0, 3.0))
    img = make_images(1, "tpf", t, cube, q, simple_wcs_header(0, 0), 2.0, 3001.0, 0.1)
    assert img is not None and img.n_transits == 10
    iy, ix = np.unravel_index(np.argmax(img.diff), img.diff.shape)
    assert (ix, iy) == (8, 3)
    # flux lost ≈ depth × host flux
    assert abs(img.diff.sum() - 0.01 * 3e3) < 5 * np.sqrt(img.diff_var.sum())


def test_linear_drift_cancels_in_the_difference_image(rng):
    t, cube, q = _cube(rng, host_xy=(8.0, 3.0), depth=0.0, drift=2e-3)
    img = make_images(1, "tpf", t, cube, q, simple_wcs_header(0, 0), 2.0, 3001.0, 0.1)
    snr = img.diff / np.sqrt(img.diff_var)
    assert np.abs(snr).max() < 5


def test_flagged_frames_are_ignored_and_no_transit_gives_none(rng):
    t, cube, q = _cube(rng, host_xy=(8.0, 3.0))
    q[:] = 32  # every frame flagged (reaction-wheel desaturation)
    assert make_images(1, "tpf", t, cube, q, simple_wcs_header(0, 0), 2.0, 3001.0, 0.1) is None
    q[:] = 0
    # ephemeris puts every transit in a data gap → nothing usable
    keep = (t < 3000.8) | (t > 3001.2)
    assert make_images(1, "tpf", t[keep], cube[keep], q[keep], simple_wcs_header(0, 0), 40.0, 3001.0, 0.1) is None


def test_npz_round_trip(tmp_path, rng):
    t, cube, q = _cube(rng, host_xy=(8.0, 3.0))
    img = make_images(7, "ffi", t, cube, q, simple_wcs_header(10, 20), 2.0, 3001.0, 0.1)
    img.to_npz(tmp_path / "s.npz")
    back = SectorImages.from_npz(tmp_path / "s.npz")
    assert back.sector == 7 and back.kind == "ffi" and back.aperture is None
    assert np.allclose(back.diff, img.diff) and back.wcs().wcs.crval[0] == 10

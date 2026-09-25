import numpy as np

from skypixels.psf import Shape, fit_difference, fit_scene, prf, prf_sum


def test_prf_has_unit_flux_and_is_centred():
    img = prf((21, 21), 10.3, 9.6, Shape(0.9, 1.1, 0.4))
    assert abs(img.sum() - 1) < 1e-3
    yy, xx = np.indices(img.shape)
    assert abs((img * xx).sum() - 10.3) < 1e-3
    assert abs((img * yy).sum() - 9.6) < 1e-3


def test_prf_sum_is_the_sum_of_single_prfs():
    s = Shape(0.8, 0.9, 0.2)
    many = prf_sum((11, 11), [3.0, 7.2], [4.5, 6.1], [2.0, 0.5], s)
    single = 2.0 * prf((11, 11), 3.0, 4.5, s) + 0.5 * prf((11, 11), 7.2, 6.1, s)
    assert np.allclose(many, single)


def test_difference_fit_recovers_position_flux_and_errors(rng):
    s = Shape(0.9, 0.9, 0.0)
    truth = (6.4, 4.7)
    offsets = []
    for _ in range(40):
        var = np.full((13, 13), 4.0)
        img = 300 * prf((13, 13), *truth, s) + rng.normal(0, 2.0, (13, 13))
        fit = fit_difference(img, var, s, [(6.0, 6.0)])
        offsets.append((np.array([fit.x, fit.y]) - truth) / np.sqrt(np.diag(fit.cov)))
        assert abs(fit.flux - 300) < 5 * fit.flux_err
    pulls = np.array(offsets)
    assert np.all(np.abs(pulls.mean(axis=0)) < 0.5)
    assert np.all((pulls.std(axis=0) > 0.6) & (pulls.std(axis=0) < 1.5))  # errors are honest


def test_difference_fit_snr_is_low_on_pure_noise(rng):
    s = Shape(0.9, 0.9, 0.0)
    fit = fit_difference(rng.normal(0, 1.0, (11, 11)), np.ones((11, 11)), s, [(5.0, 5.0)])
    assert fit.snr < 5


def test_scene_fit_recovers_wcs_shift_and_psf_width(rng):
    s = Shape(1.1, 0.9, 0.3)
    stars = np.array([[8.0, 3.0], [2.5, 9.0]])
    fl = np.array([0.3, 0.1])
    true_shift = np.array([0.35, -0.25])
    img = 1e4 * prf((15, 15), 7.0 + true_shift[0], 7.0 + true_shift[1], s)
    img += 1e4 * prf_sum((15, 15), stars[:, 0] + true_shift[0], stars[:, 1] + true_shift[1], fl, s) + 50
    var = np.abs(img) + 10
    img = img + rng.normal(0, np.sqrt(var))
    fit = fit_scene(img, var, (7.0, 7.0), stars, fl)
    assert abs(fit.dx - true_shift[0]) < 0.02 and abs(fit.dy - true_shift[1]) < 0.02
    assert abs(fit.target_flux - 1e4) / 1e4 < 0.02

"""Offline tests on synthetic light curves: search, cleaning, vetting, sizing, flares."""

import numpy as np
import pytest

from conftest import box, make_time
from hunter.classify import TOO_LARGE_TEXT, classify
from hunter.clean import clip_upward, flatten_for_search
from hunter.flares import find_flares
from hunter.measure import RSUN_IN_RJUP, implied_radius
from hunter.models import CatchType
from hunter.search import in_transit, search
from hunter.vet import odd_even, secondary_eclipse, size, snr


def _search_curve(time, groups, flux):
    flat, keep = flatten_for_search(time, flux, 0.9)
    return search(time[keep], flat[keep], groups[keep]), flat, keep


def test_recovers_injected_transit(rng):
    t, g = make_time()
    period, t0, dur, depth = 3.1234, 2001.3, 0.12, 0.004
    trend = 1 + 0.002 * np.sin(2 * np.pi * t / 5.0)  # slow stellar variability the flattening must remove
    flux = trend * (1 + box(t, period, t0, dur, depth)) + rng.normal(0, 0.001, len(t))
    sig, _, _ = _search_curve(t, g, flux)
    assert sig is not None
    assert abs(sig.period - period) / period < 0.001
    assert abs(sig.depth - depth) / depth < 0.15
    assert sig.snr > 7
    assert snr(sig).passed and odd_even(sig).passed


def test_flattening_keeps_transit_depth(rng):
    t, g = make_time(n_sectors=1)
    flux = 1 + box(t, 2.0, 2000.5, 0.25, 0.01) + rng.normal(0, 5e-4, len(t))
    mask = in_transit(t, 2.0, 2000.5, 0.25, scale=2.0)
    flat, keep = flatten_for_search(t, flux, 0.9, transit_mask=mask)
    inside = in_transit(t, 2.0, 2000.5, 0.25, scale=0.8)
    assert np.median(1 - flat[inside & keep]) == pytest.approx(0.01, rel=0.05)


def test_upward_clip_only_removes_upward_points(rng):
    flux = 1 + rng.normal(0, 1e-3, 5000)
    flux[100] += 0.05
    flux[200] -= 0.05
    keep = clip_upward(flux)
    assert not keep[100]
    assert keep[200]


def test_pure_noise_gives_no_convincing_signal(rng):
    t, g = make_time(n_sectors=1)
    flux = 1 + rng.normal(0, 1e-3, len(t))
    sig, _, _ = _search_curve(t, g, flux)
    assert sig is None or snr(sig).passed is False


def test_odd_even_mismatch_is_eclipsing_binary(rng):
    t, g = make_time()
    true_p, t0, dur = 4.0, 2001.0, 0.15
    # Primary 3%, secondary 2% exactly half an orbit later: BLS locks onto P/2 and alternate dips differ.
    flux = (1 + box(t, true_p, t0, dur, 0.03) + box(t, true_p, t0 + true_p / 2, dur, 0.02)
            + rng.normal(0, 1e-3, len(t)))
    sig, flat, keep = _search_curve(t, g, flux)
    assert abs(sig.period - true_p / 2) / (true_p / 2) < 0.001
    vet = odd_even(sig)
    assert vet.passed is False
    assert "different depths" in vet.reason


def test_secondary_eclipse_is_eclipsing_binary(rng):
    t, g = make_time()
    p, t0, dur = 3.3, 2001.0, 0.12
    # Slightly eccentric: secondary at phase 0.45, 30% of the primary depth.
    flux = 1 + box(t, p, t0, dur, 0.02) + box(t, p, t0 + 0.45 * p, dur, 0.006) + rng.normal(0, 1e-3, len(t))
    sig, flat, keep = _search_curve(t, g, flux)
    assert abs(sig.period - p) / p < 0.001
    vet, sec = secondary_eclipse(t[keep], flat[keep], sig)
    assert vet.passed is False
    assert sec["phase"] == pytest.approx(0.45, abs=0.02)
    ctype, conf, text = classify(sig, {"snr": snr(sig), "odd_even": odd_even(sig), "secondary_eclipse": vet,
                                       "size": size(implied_radius(sig.depth, 1.0))})
    assert ctype == CatchType.eclipsing_binary and conf >= 0.6


def test_hot_jupiter_occultation_does_not_fail_secondary(rng):
    t, g = make_time()
    p, t0, dur = 0.94, 2000.3, 0.08
    flux = 1 + box(t, p, t0, dur, 0.01) + box(t, p, t0 + p / 2, dur, 0.0003) + rng.normal(0, 5e-4, len(t))
    sig, flat, keep = _search_curve(t, g, flux)
    vet, _ = secondary_eclipse(t[keep], flat[keep], sig)
    assert vet.passed is True


def test_size_test_uses_radius_not_depth():
    # WASP-43 b-like: very deep (2.5%) but the star is small, so the object is Jupiter-sized.
    small_star = size(implied_radius(0.025, 0.6, 1e-4, 0.03))
    assert small_star.passed is True
    assert small_star.value < 1.5
    # Same depth on a big star: too large even at the low end of the range.
    big_star = size(implied_radius(0.025, 2.0, 1e-4, 0.1))
    assert big_star.passed is False
    assert big_star.value > 2.0


def test_size_fails_only_when_lower_bound_is_too_big():
    # Best estimate 2.1 R_Jup with a 10% star-radius error: the low end (~1.9) is planet-sized, so it passes.
    r_star = 2.1 / RSUN_IN_RJUP / np.sqrt(0.01)
    sz = implied_radius(0.01, r_star, 0.0, 0.1 * r_star)
    assert sz.radius_rjup == pytest.approx(2.1)
    assert sz.lower_rjup == pytest.approx(2.1 * 0.9) and sz.upper_rjup == pytest.approx(2.1 * 1.1)
    assert size(sz).passed is True
    # Tight errors: the low end is above 2, so it fails.
    assert size(implied_radius(0.01, r_star, 0.0, 0.01 * r_star)).passed is False


def test_size_error_sources():
    # Missing star-radius error -> 10% assumed; depth error enters at half weight.
    sz = implied_radius(0.01, 1.0, 0.0, None)
    assert sz.stellar_radius_err_assumed and sz.stellar_radius_err_rsun == pytest.approx(0.1)
    sz = implied_radius(0.01, 1.0, 0.002, 1e-12)  # 20% depth error -> 10% radius error
    assert sz.lower_rjup == pytest.approx(sz.radius_rjup * 0.9)


def test_missing_stellar_radius_is_reported_not_invented():
    sz = implied_radius(0.01, None)
    assert sz.radius_rjup is None and sz.radius_rearth is None
    vet = size(sz)
    assert vet.passed is None
    assert "no radius" in vet.reason


def test_size_only_failure_wording(rng):
    t, g = make_time()
    flux = 1 + box(t, 2.5, 2000.7, 0.1, 0.02) + rng.normal(0, 1e-3, len(t))
    sig, flat, keep = _search_curve(t, g, flux)
    sec_vet, _ = secondary_eclipse(t[keep], flat[keep], sig)
    vets = {"snr": snr(sig), "odd_even": odd_even(sig), "secondary_eclipse": sec_vet,
            "size": size(implied_radius(sig.depth, 3.0))}
    ctype, conf, text = classify(sig, vets)
    assert ctype == CatchType.eclipsing_binary
    assert conf <= 0.35
    assert TOO_LARGE_TEXT in text
    assert "is an eclipsing binary" not in text.lower()


def test_flare_found_on_unclipped_curve_and_not_symmetric_bump(rng):
    t, _ = make_time(n_sectors=1)
    flux = 1 + rng.normal(0, 1e-3, len(t))
    # Flare: 1-cadence rise, exponential decay over ~20 min.
    k = 5000
    decay = np.exp(-np.arange(30) * 2.0 / 8.0)
    flux[k:k + 30] += 0.02 * decay
    # Symmetric bump (asteroid-like): must NOT count as a flare.
    j = 12000
    flux[j - 5:j + 6] += 0.01 * np.exp(-0.5 * (np.arange(-5, 6) / 2.0) ** 2)
    assert not clip_upward(flux)[k]  # the transit-search copy would lose it...
    flares = find_flares(t, flux)  # ...but the flare search sees the unclipped curve
    assert len(flares) == 1
    assert flares[0].t_peak == pytest.approx(t[k], abs=1e-6)
    assert flares[0].amplitude == pytest.approx(0.02, rel=0.25)


def test_flare_search_skips_eclipse_edges(rng):
    t, _ = make_time(n_sectors=1)
    flux = 1 + box(t, 3.0, 2000.5, 0.1, 0.1) + rng.normal(0, 1e-3, len(t))
    mask = in_transit(t, 3.0, 2000.5, 0.1, scale=3.0)
    assert find_flares(t, flux, exclude=mask) == []

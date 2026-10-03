"""The monitor record built from hunt's per-star result has the API's shape and says outcomes in words."""

import json

import numpy as np

from scheduler import monitor_record as mr


def summary():
    return {
        "tic": 42, "star": {"tic": 42, "ra": 10.123456, "dec": -5.5, "tmag": 9.8, "teff": 3300.0, "rad": 0.3},
        "sectors": [10, 11],
        "masked_known": [{"name": "TOI-1.01", "period_d": 2.0, "t0_btjd": 1500.0, "mask_half_width_h": 3.0},
                         {"name": "Planet b", "period_d": 2.001, "t0_btjd": 1500.0, "mask_half_width_h": 3.0}],
        "signals": [
            {"n": 1, "period_d": 5.0, "t0_btjd": 1501.0, "duration_h": 2.0, "depth_ppm": 800.0, "snr": 12.0,
             "sde": 11.0, "n_transits": 4, "failed_stage": None, "failed_checks": []},
            {"n": 2, "period_d": 9.0, "t0_btjd": 1502.0, "duration_h": 2.0, "depth_ppm": 300.0, "snr": 8.0,
             "sde": 5.0, "n_transits": 2, "failed_stage": "sde", "failed_checks": []},
            {"n": 3, "period_d": 1.3, "t0_btjd": 1500.1, "duration_h": 1.0, "depth_ppm": 900.0, "snr": 20.0,
             "sde": 15.0, "n_transits": 9, "failed_stage": "checks", "failed_checks": ["odd_even"],
             "failed_reasons": {"odd_even": "Alternate dips differ: an eclipsing binary."}},
        ],
        "dips": [{"n": 1, "kind": "single", "mid_times_btjd": [1510.0], "duration_h": 5.0, "depth_ppm": 2000.0,
                  "snr": 13.0, "period_d": None, "failed_stage": None, "failed_checks": []}],
    }


def test_record_shape_and_outcomes():
    t = np.concatenate([np.arange(1500, 1520, 2 / 1440), np.arange(1527, 1547, 2 / 1440)])
    f = np.where(np.arange(len(t)) % 50 == 0, np.nan, 1.0)
    g = np.where(t < 1525, 10, 11)
    rec = mr.build(summary(), t, f, g, queue="deep")
    json.dumps(rec, allow_nan=False)
    assert rec["tic"] == 42 and rec["ra"] == 10.12346 and rec["radius_rsun"] == 0.3
    assert rec["outcome"] == "candidate"
    assert rec["observed_from"] == "2019-01-16T12:00:00Z"  # BTJD 1500
    assert len(rec["lightcurve"]["t"]) == len(rec["lightcurve"]["f"]) <= mr.MAX_POINTS
    assert rec["bin_minutes"] == 30  # 40 days of 2-min data fit in 2,000 half-hour bins
    outs = [(d["kind"], d["outcome"]) for d in rec["detections"]]
    assert outs == [("periodic", "known"), ("periodic", "candidate"), ("duo", "rejected"),
                    ("periodic", "rejected"), ("single", "candidate")]
    known = rec["detections"][0]
    assert "TOI-1.01" in known["reason"] and "also listed as Planet b" in known["reason"]
    assert rec["detections"][3]["reason"] == "Alternate dips differ: an eclipsing binary."
    assert rec["detections"][4]["id"] == "s1"
    assert mr.promising(summary())


def test_long_baseline_is_binned_down():
    t = np.arange(0, 1000, 2 / 1440)  # ~720k points
    rec = mr.build({"tic": 1, "star": {}, "sectors": [1]}, t, np.ones_like(t), np.ones(len(t), int), queue="deep")
    assert len(rec["lightcurve"]["t"]) <= mr.MAX_POINTS
    assert rec["bin_minutes"] > mr.BASE_BIN_MIN
    assert rec["outcome"] == "none"


def test_not_promising():
    s = {"signals": [{"snr": 6.0, "failed_stage": "snr"}, {"snr": 30, "failed_stage": "known"}], "dips": []}
    assert not mr.promising(s)

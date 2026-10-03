# Day-one data

What the site shows at go-live, until the daily search (Kaggle, `kaggle/`) runs. Real data only; sent to the API
over HTTPS with the ingest token (docs/DEPLOY.md, B6). Built by `make_dayone.py` (its docstring has the command).

| Folder / file | What |
|---|---|
| `monitor/` | 201 monitor records: the 26 Sep 2026 sweep (hunt's fast search, 200 stars; 14 with a stored curve) and the two leads searched again by the final deep search (with their stitched curves, 30-min bins). TIC 76923707 was in both; its deep record is the one kept. |
| `candidates/` | Empty: neither lead survived vetting. |
| `summary.json` | The 26 Sep sweep's summary: the funnel on the Candidates page. |
| `leads.json` | Each lead's verdict and the reason the site shows. |
| `vetting/` | The evidence: each lead's search record with skyvet's full vetting block, and the pixel check. |

Checked on 27 Sep against a local API on Postgres: 201 stars, 431 signals (130 already known, 301 rejected),
0 candidates; both leads appear in the log as rejected, with the reasons below.

## The two leads (DEEPHUNT's calibration run, 27 Sep 2026)

Each was searched again with the final deep search (QLP fix and scattered-light mask), pixel-checked in every
sector, and vetted with skyvet (LEO-vetter, TRICERATOPS, Gaia DR3, VSX).

**TIC 360955814** (M dwarf, 3,335 K, 0.32 R☉, Tmag 10.9): P 12.731743 d, 523 ppm, 3.8 h, 11 transits; ≈ 0.8 R⊕ if real.
**Rejected.**
- The final deep search finds it again (P 12.731741 d, SNR 12.3, SDE 11.6, every check passed).
- Pixel check: *inconclusive* in all 9 sectors: the dip is not visible in the pixels (best difference-image SNR
  4.0 < 5), so its source can't be located.
- skyvet on the five SPOC 2-min sectors (13, 66, 67, 93, 94): **fail**. TRICERATOPS NFPP 0.219 > 0.1 (FPP 0.615;
  most probable: TP 0.34, EBx2P 0.17). LEO-vetter: signal too weak in these sectors (MES 2.3), with 7 more
  false-alarm flags; its pixel test puts the source 10.3″ from the target, next to Gaia DR3 6632099966599883264
  (TIC 1816575428, G 18.1, 3.5″ away).
- skyvet on the newest three (QLP sectors 102–104, after the QLP fix): **flag**. 8 LEO false-alarm flags (a
  grazing, unphysical fit); TRICERATOPS ran out of its 900-s budget.
- Most of the signal comes from the 200-s QLP full-frame sectors 101–104, the ones with heavy unflagged
  scattered light; per transit the depths range from −16 to 832 ppm. Gaia lists 24 neighbours within 63″ bright
  enough to cause the dip.

**TIC 76923707** (TOI-181's host, K dwarf, 0.81 R☉, Tmag 10.5): P 9.482272 d, 538 ppm, 6.0 h, 11 transits.
**Rejected.**
- Not TOI-181 b: P / P_b = 2.092, not a simple alias; the lead's transits drift ~10 h per two orbits of b and fall
  −14 to +38 h from b's transits. The two dips nearest b (−4.0 h, −2.7 h) carry no depth (184 ± 192, −89 ± 231
  ppm); dropping them strengthens the signal. The final deep search recovers TOI-181 b separately (SNR 152).
- The final deep search itself now rejects it on the sector-depth check; the 11 depths disagree (χ² ≈ 42 for 10
  degrees of freedom; sector 29 gives 1,262 and 915 ppm, others near zero); a 6.0-h dip is long for a 9.5-d orbit
  of this star (≈ 3.4 h for a central transit).
- Pixel check: *inconclusive* (best SNR 2.9 < 5); sectors 2 and 69 show the opposite of a dip (SNR −3.2, −5.5).
- skyvet (SPOC sectors 69, 96, 106): **fail**. LEO-vetter: significant secondary eclipse (a false-positive test),
  plus 5 false-alarm flags (MES 4.1). TRICERATOPS NFPP 0.664 (FPP 1.0; most probable: an eclipsing binary on the
  neighbour TIC 76923709). The star is a known rotational variable (ASAS-SN V J232841.41-342929.1, 25.2 d,
  0.06 mag), and Gaia DR3 flags it as variable.

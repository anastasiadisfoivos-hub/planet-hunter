# Next data: fainter stars, Gaia, and Chile/ESO archives

Checked 2026-09-26. Every fact below has a source link.

## Three-line plan

1. **TGLC:** run the `tglc` package on recent full-frame images for M dwarfs and small stars at Tmag 13–16
   (MAST has TGLC only for S1–55). Search them with a looser noise model, and treat the results as TGLC-only
   candidates, which the TOI team has never promoted.
2. **Gaia DR3:** for every candidate, pull RUWE, `ipd_frac_multi_peak`, `non_single_star`, the RV-constancy
   p-value and the `vari_eclipsing_binary` match, and add them as checks. Re-run the checks on DR4 when it
   ships on 2 Dec 2026.
3. **ESO:** query the public HARPS RV catalogue and the ESPRESSO/HARPS Phase 3 products (TAP `ivoa.ObsCore`)
   for archival RVs of each candidate host. A km/s swing rules out a planet; a flat series is only supporting
   evidence. Rubin cannot vet TESS transits.

## 1. TGLC faint-star light curves (to T ≈ 16)

TGLC (TESS-Gaia Light Curve; Han & Brandt 2023, AJ 165, 71) fits TESS full-frame images with an effective PSF.
Gaia DR3 positions and fluxes are the priors, which removes light from neighbouring stars. It reaches "16th TESS
magnitude" with "≲2% at 16th TESS magnitude even in crowded fields" (https://arxiv.org/abs/2301.03704).

- **Coverage:** the MAST HLSP (DOI 10.17909/610m-9474, https://archive.stsci.edu/hlsp/tglc) covers only
  Sectors 1–55, about 255 M light curves. "The TGLC light curves for Sectors 12-55 are not yet available via the
  MAST Portal, API, or astroquery, but can be accessed for bulk download via the provided curl script."
- **Recent sectors:** "As of Sector 94, QLP is now using the TESS-Gaia Light Curve (TGLC) methodology"
  (https://archive.stsci.edu/hlsp/qlp; Petitpas et al. 2026, RNAAS 10, QLP Data Release Notes 004). QLP stops
  at Tmag 13.5, though. **Our QLP inputs from S94 on are already TGLC photometry**, and the faint end
  (13.5–16) needs our own run.
- **Making our own:** `pip install tglc` (Python 3.10–3.12,
  https://github.com/TeHanHunter/TESS_Gaia_Light_Curve). QLP's package also installs as `tglc`, so keep them in
  separate environments. It needs FFI cutouts through TESScut, so it is CPU-heavy per star. Budget it separately
  from the main sweep and run it on the top few thousand faint M dwarfs, not millions of stars.
- **Caveats:**
  - Compare `cal_aper_flux` with `cal_psf_flux` for each candidate. The README warns that "neither flux choice
    guarantees the correct amplitude."
  - MAST notes that dim stars (≲15 Tmag) near a variable source can have negative flux in some cadences.
  - At T = 15–16, a 2% precision per cadence reaches only Jupiter-sized planets around sun-like stars, but
    Earth-to-Neptune-sized planets around late M dwarfs. **Target faint M dwarfs only.**
  - The pixel check matters more here: faint targets have more bright neighbours.
- **Submission reality:** no CTOI has been promoted without a SPOC/QLP TCE (Guerrero et al. 2021; see
  EXOFOP.md). A TGLC-only candidate needs its own follow-up and paper.

## 2. Gaia DR3 (now) and DR4 (2 Dec 2026)

Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1. Useful columns
(https://gea.esac.esa.int/archive/documentation/GDR3/Gaia_archive/chap_datamodel/sec_dm_main_source_catalogue/ssec_dm_gaia_source.html):

| Column / table | Why it helps | Check |
|---|---|---|
| `ruwe` | a poor single-star fit hints at an unresolved binary | flag > 1.4 (Lindegren 2018, GAIA-C3-TN-LU-LL-124) |
| `ipd_frac_multi_peak` | "the detection may be a visually resolved double star" | flag > 10 |
| `non_single_star` | Gaia's own binary solution (astrometric / spectroscopic / eclipsing) | flag ≠ 0 |
| `rv_chisq_pvalue`, `rv_amplitude_robust` | RV variability on bright stars; an EB swings by km/s | flag p < 0.01 with `rv_renormalised_gof` > 4 and `rv_nb_transits` ≥ 10 (the documented cut) |
| `vari_eclipsing_binary` | 2,184,477 EB candidates (Mowlavi et al. 2023, A&A 674, A16) | reject on a period match at the target or a neighbour |
| cone ≤ 1′ | neighbour list for dilution and the pixel check | already used by `pixels/` |

**DR4:** "Coming up: 2 December 2026" (https://www.cosmos.esa.int/web/gaia/data-release-4). It covers 66
months, about twice DR3, and adds epoch photometry and RV time series for everyone plus better binary
solutions. Plan a re-check of every candidate against DR4 in December.

## 3. Chile / ESO archive (public, useful for vetting)

- **Access policy:** the proprietary period is "typically one year"; after that the data are public
  (https://archive.eso.org/cms/eso-data-access-policy.html).
- **ESO HARPS RV catalogue** (12 Dec 2023): "289843 observations of 6488 unique astronomical objects",
  2003–2023, with a pipeline RV precision of about 0.5 m/s (https://www.eso.org/sci/publications/announcements/sciann17609.html;
  Barbieri et al., arXiv:2312.06586). This is the quickest win: one cross-match per candidate host.
- **HARPS-RVBank:** Trifonov et al. 2020, A&A 636, A74 (> 212,000 RVs of ~3,000 stars), updated by Perdelwitz et al.
  2024, A&A 683, A125 (252,615 RVs of 5,239 stars) (https://github.com/3fon3fonov/HARPS_RVBank).
- **Phase 3 products:**
  - HARPS: the s1d spectrum, plus CCF and bisector files in an ancillary tar
    (https://support.eso.org/en-US/kb/articles/harps-how-to-get-the-pipeline-generated-files-ccf-s1d-e2ds-bis-int-guide).
  - ESPRESSO (Pepe et al. 2021, A&A 645, A96): the RV is in the header keyword `HIERARCH ESO QC CCF RV`.
- **Query:** TAP `ivoa.ObsCore` at https://archive.eso.org/programmatic/ (`obs_collection` = HARPS / ESPRESSO,
  cone on the target), or `astroquery.eso`.
- **How it helps:** our targets are mostly fainter M dwarfs, so only a small fraction will have archival RVs.
  Where they exist:
  - variation of several km/s → EB or a blended binary: reject;
  - flat at the m/s level → supports a planet or a background blend, but it does not measure a mass;
  - a known long-term RV trend → flag it.
  It never replaces new follow-up.

## 4. What is NOT usable: Rubin/LSST for transits

- **Saturated:** single-visit saturation is about r ≈ 15.8 (u 14.7 … y 13.9)
  (https://www.rubin.community/t/saturation-limits/12649). Every Tmag ≤ 13 target is saturated, and T ≈ 16
  targets are at the edge.
- **Alerts don't fire on transits:** alerts are issued for difference-image sources at SNR ≥ 5 (LSE-163). A
  0.1–1% dip on a bright star does not come close.
- **Cadence:** about 800 visits per field over 10 years in six bands (Ivezić et al. 2019, ApJ 873, 111), so
  visits are nights apart. A transit of a few hours is almost never caught, and single points cannot be
  phase-folded with any useful precision.
- **Rights:** "Prompt processed images and the annual data releases have a proprietary period of two years"
  (https://rubinobservatory.org/for-scientists/data-products/data-policy). Only data-rights holders can use
  them. Alerts are public, but see the points above.
- **Southern sky only.**

Rubin could later help identify faint EBs near TGLC targets, from DR1 catalogues and variability, but not
before DR1, and only with data rights.

## References

Barbieri et al. 2023, arXiv:2312.06586 · Gaia Collaboration, Vallenari et al. 2023, A&A 674, A1 · Guerrero et al. 2021,
ApJS 254, 39 · Han & Brandt 2023, AJ 165, 71 · Ivezić et al. 2019, ApJ 873, 111 · Mayor et al. 2003, Msngr 114, 20
(HARPS) · Mowlavi et al. 2023, A&A 674, A16 · Pepe et al. 2021, A&A 645, A96 · Perdelwitz et al. 2024, A&A 683, A125 ·
Petitpas et al. 2026, RNAAS 10 · Trifonov et al. 2020, A&A 636, A74

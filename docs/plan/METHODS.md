# Methods

planet-hunter searches public NASA TESS data for stars that dim briefly and regularly, the way a star does when
a planet passes in front of it. This page explains what we search, how, what we check, and what our results do
and do not mean.

## Data

TESS (Ricker et al. 2015) watches each patch of sky for about 27 days at a time. We use light curves (brightness
over time) already published at MAST, the public archive at the Space Telescope Science Institute: SPOC 2-minute
light curves (Jenkins et al. 2016), TESS-SPOC (Caldwell et al. 2020) and QLP (Huang et al. 2020; Kunimoto et al.
2021) light curves from the full-frame images. Star properties come from the TESS Input Catalog (Stassun et al.
2019), and neighbouring stars from Gaia DR3 (Gaia Collaboration, Vallenari et al. 2023).

We search stars down to TESS magnitude 13, starting with small, cool stars (M dwarfs). On a small star, a planet
blocks a larger share of the light, so its dips are deeper. For stars that already have a known planet, TESS
Object of Interest (TOI), community candidate (CTOI) or eclipsing-binary listing, the known signals are masked
out first, so we look only for additional planets.

## Search

Bad points are dropped and the slow wobbles of the star and spacecraft are removed with a running robust average
(Hippke et al. 2019). We then test thousands of trial periods from half a day upward with Box Least Squares
(Kovács, Zucker & Mazeh 2002, in Astropy; Astropy Collaboration 2022), reading the data with Lightkurve
(Lightkurve Collaboration 2018). A deeper search, being added now, joins every sector of a star, adds Transit
Least Squares (Hippke & Heller 2019) for small planets, and looks for long-period planets with only one or two
dips. We look for up to three signals per star.

A signal is kept only if it is strong (signal-to-noise ratio of at least 10, plus a clear peak over the other
trial periods) and shows at least three separate dips.

## Checks

Most dips that look like planets are not planets. Every signal goes through automatic checks, and one failure is
enough to drop it:

- **Odd and even dips** differ in depth: likely two stars eclipsing each other, not a planet.
- **A secondary dip** half an orbit later: the glow of a star, which a planet would not show.
- **Too big:** the implied object is larger than twice Jupiter.
- **Wrong length:** a dip much longer or shorter than a planet orbiting this star could make.
- **Wrong period:** the true period is really half, double or triple the one found.
- **Spacecraft events:** the dips line up with thruster firings or bad data.
- **Inconsistent depth** from one sector to the next.

Signals that match a known planet, TOI, CTOI or eclipsing binary on the same star, or on a listed star within
2.5 arcminutes, are removed.

## Pixel check

A TESS pixel is 21 arcseconds wide, so a nearby eclipsing binary can leak light in and fake a planet. For each
candidate we subtract the images taken during the dips from those just before and after. The difference shows
where the light went missing, and we compare that spot with the target and every Gaia neighbour able to cause
the dip (the method of Bryson et al. 2013). The result is *on target*, *possible neighbour*, *off target* or
*inconclusive*.

## Vetting

Candidates that pass are shown in the app with their light curves, pixel images and every check result, so that
people can inspect them and flag problems. To measure completeness, we add fake planets to real light curves
and rerun everything. Of 2,000 fake planets on 200 quiet stars, we recovered 61%: 28% at 1–2 Earth radii, about
70% above 3, over 80% at periods under 2 days, and 7% at 10–15 days.

## Submission

Since 19 August 2026, ExoFOP, the archive where the TESS follow-up community shares candidates, accepts community
candidates only after they are published in a peer-reviewed journal. Our route is therefore to write up the best
candidates in a paper first, then upload them to ExoFOP as CTOIs. The TESS team decides whether a CTOI becomes a
TOI (Guerrero et al. 2021).

## Limits

- Stars fainter than magnitude 13 are not searched yet, and neither are stars with only one sector of data.
- Planets smaller than about twice Earth's size, and orbits longer than about 10 days, are mostly missed.
- Our checks cannot rule out every false positive. A faint eclipsing binary sitting almost directly behind the
  target looks the same in TESS data. Ruling it out takes sharper images or spectra from telescopes on the ground.
- Our automatic checks do not replace the TESS team's own vetting.

## What "candidate" means

A **candidate** is a repeating dip that passed every check we could run. It is **not a planet and not a
discovery.** Most candidates from any transit survey turn out to be something else. A candidate becomes a
planet only after independent follow-up, usually a measurement of the star's wobble (radial velocity) or a
statistical validation, published in a refereed paper.

## References

- Astropy Collaboration 2022, ApJ 935, 167
- Bryson, S. T. et al. 2013, PASP 125, 889
- Caldwell, D. A. et al. 2020, RNAAS 4, 201
- Gaia Collaboration, Vallenari, A. et al. 2023, A&A 674, A1
- Guerrero, N. M. et al. 2021, ApJS 254, 39
- Hippke, M. & Heller, R. 2019, A&A 623, A39
- Hippke, M. et al. 2019, AJ 158, 143
- Huang, C. X. et al. 2020, RNAAS 4, 204
- Jenkins, J. M. et al. 2016, Proc. SPIE 9913, 99133E
- Kovács, G., Zucker, S. & Mazeh, T. 2002, A&A 391, 369
- Kunimoto, M. et al. 2021, RNAAS 5, 234
- Lightkurve Collaboration 2018, Astrophysics Source Code Library, ascl:1812.013
- Ricker, G. R. et al. 2015, JATIS 1, 014003
- Stassun, K. G. et al. 2019, AJ 158, 138

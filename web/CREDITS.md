# Credits and data sources

## Planet Finder (DEMO DATA until the live API is connected)

- `public/data/finder/*`: made-up candidates with simulated light curves, built by
  `components/finder/data/build-finder-mock.mjs`, and pixel images borrowed from two real PIXELS runs.
- Planet hosts (`public/data/hosts.json`, a frozen file since v2): NASA Exoplanet Archive, Planetary Systems
  Composite Parameters (`pscomppars`). This research has made use of the NASA Exoplanet Archive, which is operated
  by the California Institute of Technology, under contract with NASA under the Exoplanet Exploration Program.
  Distances are the archive's `sy_dist`, mostly from TICv8 (Stassun et al. 2019, Gaia DR2 parallaxes).

## Pictures

Every picture is a real photograph or real instrument data, in `public/images/`, with its credit and licence in
`public/images/credits.json` and on `/credits`.

## Code

- Geist and Geist Mono (SIL OFL). Phosphor Icons (MIT).

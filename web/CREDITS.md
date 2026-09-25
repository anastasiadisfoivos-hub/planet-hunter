# Credits and data sources

## Events (DEMO DATA until the live service is connected)

- `public/data/events.mock.json` and `status.mock.json` are **real recorded data**, built by
  `scripts/build-events-mock.mjs`: the events service (`skyevents.ingest`) run offline on its recorded real week
  (2026-09-18 to 2026-09-25: Rubin via Fink, ZTF via ALeRCE, TNS, MPC, JPL, CNEOS, NASA DONKI, GCN, IceCube,
  GraceDB), plus the PICTURES session's 20 real example events and their verified pictures (images/EXAMPLES.md).
  Each picture's caption, credit and licence come with it and are shown in the app.
- Rubin alerts heatmap: `public/data/heatmap.rubin-sample.json`, `skysources.heatmap.build_heatmap` run on its
  recorded real answers (ALeRCE LSST stamp classes and the Fink SSO sample, night of 2026-07-14), HEALPix RING.
- Earth inset coastlines: Natural Earth 1:110m land (public domain), via the world-atlas package
  (`scripts/build-land.mjs`).
- The Sun's position: low-precision solar coordinates from the Astronomical Almanac (`lib/sun.ts`).

## Real data on the map

- **Rubin survey footprint.** Rubin Observatory scheduler, `rubin_scheduler.scheduler.utils.get_current_footprint`
  ([lsst/rubin_scheduler](https://github.com/lsst/rubin_scheduler)) v4.5.0 with data `scheduler_2026_07_23`, following the
  SCOC Phase 3 recommendations ([PSTN-056](https://pstn-056.lsst.io)). Built by `scripts/rubin_footprint.py`.
- **Planet hosts.** NASA Exoplanet Archive, Planetary Systems Composite Parameters (`pscomppars`). This research has made
  use of the NASA Exoplanet Archive, which is operated by the California Institute of Technology, under contract with
  NASA under the Exoplanet Exploration Program. Distances are the archive's `sy_dist`, mostly from TICv8 (Stassun et
  al. 2019, Gaia DR2 parallaxes). Built by `scripts/build-hosts.mjs`.
- **Bright stars.** Yale Bright Star Catalogue, 5th revised ed. (Hoffleit & Warren 1991), VizieR V/50.
- **Star colours.** Mitchell Charity, "What color are the stars?" (http://www.vendian.org/mncharity/dir3/starcolor/)
  and its blackbody table, "What color is a blackbody?"
  (http://www.vendian.org/mncharity/dir3/blackbody/UnstableURLs/bbr_color.html): sRGB, D65 white, CIE 1964 10°
  observer, 1000 K to 40000 K. Built by `scripts/build-star-colors.mjs`. Temperatures: `st_teff` from the Exoplanet
  Archive (TIC values for most hosts); for bright stars, Teff from B−V by Ballesteros (2012), EPL 97, 34008. Colours
  get one display saturation boost (×1.75), noted in "About this map".
- **Stellar radii and magnitudes.** Exoplanet Archive `st_rad` and `sy_vmag`, same table as above.

## Positions and sizes behind the illustrated sky

The "Artistic nebulae & clouds" layer draws procedural shapes; **positions and sizes are real**; shapes are
illustrations, not photographs. All catalogues are via VizieR (CDS, Strasbourg), built by `scripts/build-sky-objects.mjs`:

- Sharpless (1959), *A Catalogue of H II Regions*, VII/20: emission nebulae.
- Rodgers, Campbell & Whiteoak (1960), southern H-alpha emission regions, VII/216: emission nebulae south of -27°.
- Lynds (1962), *Catalogue of Dark Nebulae*, VII/7A: dark clouds (opacity 4 and up, area 0.25 deg² and up).
- Green (2009), *A Catalogue of Galactic Supernova Remnants*, VII/272: remnants 20′ and larger.
- SIMBAD positions for a short list of famous objects (Orion, Carina, Lagoon, Eagle, Trifid, Tarantula, Rosette, North
  America, Gum, Pleiades, Rho Ophiuchi, Witch Head, M78, Iris, Coalsack, Horsehead, Pipe).
- Magellanic Cloud positions and sizes: SIMBAD (LMC 80.894°, -69.756°; SMC 13.187°, -72.829°).
- The Milky Way band follows the IAU galactic coordinate system (Hipparcos equatorial-to-galactic rotation).

This research has made use of the VizieR catalogue access tool and the SIMBAD database, CDS, Strasbourg, France.

## Code

- Simplex noise: "webgl-noise" by Ian McEwan and Stefan Gustavson (Ashima Arts), MIT licence,
  https://github.com/ashima/webgl-noise
- HEALPix lookups: `@hscmap/healpix` (MIT).
- Close-up star shading follows the approach in B. Podgursky, procedural star rendering (bpodgursky.com, 2017) and
  S. Lee, realistic Sun with shaders (sangillee.com, 2024): layered simplex noise for granulation, linear limb
  darkening, and a fresnel-falloff corona. Illustrations, not simulations.
- camera-controls by yomotsu (MIT). postprocessing and @react-three/postprocessing by pmndrs (Zlib, MIT).
- three.js, @react-three/fiber, @react-three/drei (MIT). Geist and Geist Mono (SIL OFL). Phosphor Icons (MIT).

# Credits and data sources

## Real data on the map

- **Rubin survey footprint.** Rubin Observatory scheduler, `rubin_scheduler.scheduler.utils.get_current_footprint`
  ([lsst/rubin_scheduler](https://github.com/lsst/rubin_scheduler)) v4.5.0 with data `scheduler_2026_07_23`, following the
  SCOC Phase 3 recommendations ([PSTN-056](https://pstn-056.lsst.io)). Built by `scripts/rubin_footprint.py`.
- **Planet hosts.** NASA Exoplanet Archive, Planetary Systems Composite Parameters (`pscomppars`). This research has made
  use of the NASA Exoplanet Archive, which is operated by the California Institute of Technology, under contract with
  NASA under the Exoplanet Exploration Program. Distances are the archive's `sy_dist`, mostly from TICv8 (Stassun et
  al. 2019, Gaia DR2 parallaxes). Built by `scripts/build-hosts.mjs`.
- **Bright stars.** Yale Bright Star Catalogue, 5th revised ed. (Hoffleit & Warren 1991), VizieR V/50.

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
- three.js, @react-three/fiber, @react-three/drei (MIT). Geist and Geist Mono (SIL OFL). Phosphor Icons (MIT).

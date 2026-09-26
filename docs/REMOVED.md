# Removed in v2

v2 turns planet-hunter into the **Planet Finder only**, with a live monitor of the nightly sweep. Everything
that served the sky events, the 3D sky map and the Lab is gone: **450 files**, listed in full at the
end. Nothing was tagged; the last full site is the existing tag `v1-spotter`.

## What went

**Sky events** (`/events`, `/events/[id]`)
- `events/` (package `skyevents`): the fetchers for Rubin via Fink, ZTF via ALeRCE, TNS, MPC, JPL, CNEOS, NASA
  DONKI, GCN, IceCube and GraceDB, de-duplication and the query layer; `events/ci/ingest.yml`.
- `sources/` (package `skysources`): Rubin alerts, heatmap, schedule, solar-system objects, stream status.
- `images/` (package `skypictures`): the real pictures for events (survey cutouts, SDO frames, the aurora map).
- `contracts/`: the old shared contract (Sphere, Discovery, Forecast, StarTarget, heatmap schemas).
- API: `GET /events`, `GET /events/{id}`, `GET /status`, `python -m api.ingest`, `api/ci/ingest.yml`,
  `storage/events_sql.py`.
- Web: the events gallery and event pages, `components/events`, most of `components/gallery`,
  `public/data/events.mock.json`, `status.mock.json`, `heatmap.rubin-sample.json`, `scripts/build-events-mock.mjs`,
  `scripts/build-picture-marks.mjs`, and 102 pictures in `public/images/{events,sky,feature}` that only events,
  the sky and the Lab showed (with their entries in `public/images/credits.json`: 102 removed, 22 kept).

**The 3D sky map** (`/sky`; `/map` redirected there)
- Web: `app/sky`, `components/map` (scene, shaders, flight, filters, overlays), `state/store.tsx`,
  `lib/{galactic,hosts,images,markers,sky,skyTexture,starColor,starColorTable,sun}.ts`, the `/map` redirect in
  `next.config.ts`, `public/data/{sky,sky-objects.json,bright-stars.json,land-110m.json,rubin-footprint.json}`,
  `scripts/{build-sky,build-sky-objects,build-bright-stars,build-land,build-star-colors,build-hosts}.mjs`,
  `scripts/rubin_footprint.py`, and the npm packages three, @react-three/fiber, drei and postprocessing,
  postprocessing, camera-controls, @hscmap/healpix, topojson-client, world-atlas and their types.
- Docs: `web/docs/spotmap`, `web/docs/mapui`, `web/docs/graphics-pass`.

**The Lab and Analyze a star** (`/lab`, `/lab/*`, `/lab/star/[tic]`)
- API: `POST /analyze`, `GET /jobs/{id}`, `GET /stars/{tic}/analysis`, `GET /stars/{tic}/lab`,
  `GET /stars/{tic}/lightcurve` (the finder never called it: candidates carry their own curves),
  `python -m api.precompute`, `api/ci/precompute.yml`, the analyze queue, the NASA Exoplanet Archive adapter,
  the SPECTRA index and the fake TESS analyzer.
- Web: `app/lab`, `components/lab` (all but two helpers, below), `public/data/lab` (including the SPECTRA
  stand-ins in `lab/spectra-mock`), `public/data/analysis`, `web/docs/lab`.
- There was no top-level `spectra/` folder and no `web/public/data/spectra` in v2's sources; the Lab's spectra
  data lived in `web/public/data/lab/spectra-mock`, removed above.

**Database.** Migration `0006_finder_only` (Postgres and SQLite) drops `events`, `event_sources`,
`ingest_status`, `star_analyses`, `star_names`, `analyze_jobs`, `star_lightcurves`, `known_planets`, the first
prototype's `traps`, `discoveries`, `catches`, `jobs` (Postgres only), and the `ph_sep_deg()` function. The old
migration files stay, so databases that applied them stay consistent.

**Tests** that covered only removed code: `api/tests/{test_analyze,test_events,test_fold,test_ingest,test_lab,
test_precompute,sample_events}.py`; `web/tests/{analyze,flight,galactic,images,markers,rig,sky,skyTexture,
starColor}.test.ts`, `web/tests/lab/*`, `web/tests/map/*`; the events-mock tests in `web/tests/events.test.ts`;
the `/map` redirect test in `web/tests/shell.test.ts`.

## What stays

- **Kept on purpose:** `api/` finder routes, admin export, `finder_ingest`, the new `/monitor/*` routes;
  `pixels/`, `hunt/`, `pipeline/` (hunt and the known-list re-check use `hunter`); `api/ci/finder.yml`,
  `hunt/ci/sweep.yml`; `/finder`, `/finder/[id]`, `/finder/sensitivity`, `/credits`, the home page.
- **Kept only because a file owned by another session imports it.** Delete each once that import goes:

  | Kept | Imported by |
  |---|---|
  | `components/lab/chart.tsx`, `components/lab/hooks.ts`, `components/lab/lab.module.css` | `components/finder/*` (`LoadError`, `linear`, `ticks`, `nf0`, `useWidth`) |
  | `components/gallery/EventTile.tsx`, `gallery.module.css`, `text.ts`; `components/map/CategoryGlyph.tsx`, `map.module.css`; `lib/events.ts`, `lib/eventStyle.ts`, `lib/contract.ts` | `components/home/ThisWeek.tsx` (and `components/picture/TypoTile.tsx`) |
  | `getAllEvents()` (always `[]`) and `clockNow()` in `lib/api.ts` | `components/home/ThisWeek.tsx` |
  | `lib/data.ts` (now only the `HostsFile` type) and `public/data/hosts.json` (frozen; its builder needed the Rubin footprint) | `components/shell/StarSearch.tsx`; `getMapHostTics()` for `components/finder/Report.tsx` |
  | 5 pictures (`sky/eso0733a.jpg`, `feature/heic0715a.jpg`, `feature/heic0406a.jpg`, `data/wasp18-tess-pixels-s0104.png`, `events/donki-2026-09-19T17-57-00-FLR-001.jpg`) | `app/page.tsx` |

- **Links still pointing at removed routes** (owned by MONITOR-UI, left for it): the top bar's Events, Sky and
  Lab entries (`components/shell/nav.ts`), the home page's Lab and Famous-stars sections, and the event links
  from `EventTile`.

## Every file removed

<details><summary>Python packages (115 files)</summary>

- `contracts/CONTRACT.md`
- `contracts/CONVENTIONS.md`
- `contracts/schemas/Discovery.schema.json`
- `contracts/schemas/Forecast.schema.json`
- `contracts/schemas/Sphere.schema.json`
- `contracts/schemas/StarTarget.schema.json`
- `contracts/schemas/heatmap.schema.json`
- `events/.gitignore`
- `events/.python-version`
- `events/README.md`
- `events/ci/ingest.yml`
- `events/pyproject.toml`
- `events/scripts/record_fixtures.py`
- `events/src/skyevents/__init__.py`
- `events/src/skyevents/adapters/__init__.py`
- `events/src/skyevents/adapters/_http.py`
- `events/src/skyevents/adapters/cneos.py`
- `events/src/skyevents/adapters/comets.py`
- `events/src/skyevents/adapters/donki.py`
- `events/src/skyevents/adapters/gcn.py`
- `events/src/skyevents/adapters/gracedb.py`
- `events/src/skyevents/adapters/icecube.py`
- `events/src/skyevents/adapters/mpc.py`
- `events/src/skyevents/adapters/rubin.py`
- `events/src/skyevents/adapters/tns.py`
- `events/src/skyevents/adapters/ztf.py`
- `events/src/skyevents/cli.py`
- `events/src/skyevents/dedup.py`
- `events/src/skyevents/ingest.py`
- `events/src/skyevents/models.py`
- `events/src/skyevents/query.py`
- `events/src/skyevents/util.py`
- `events/tests/conftest.py`
- `events/tests/fixtures/http/cneos_2026-09.json`
- `events/tests/fixtures/http/donki_storm_2026-08.json`
- `events/tests/fixtures/http/gracedb_S251117dq.json`
- `events/tests/fixtures/http/live_week.json`
- `events/tests/recording.py`
- `events/tests/test_adapters.py`
- `events/tests/test_cli.py`
- `events/tests/test_dedup.py`
- `events/tests/test_live_week.py`
- `events/tests/test_query.py`
- `events/uv.lock`
- `images/.gitignore`
- `images/.python-version`
- `images/EXAMPLES.md`
- `images/README.md`
- `images/pyproject.toml`
- `images/scripts/examples.py`
- `images/scripts/record_noaa.py`
- `images/src/skypictures/__init__.py`
- `images/src/skypictures/cli.py`
- `images/src/skypictures/context.py`
- `images/src/skypictures/core.py`
- `images/src/skypictures/credits.py`
- `images/src/skypictures/cutouts.py`
- `images/src/skypictures/earth.py`
- `images/src/skypictures/models.py`
- `images/src/skypictures/net.py`
- `images/src/skypictures/py.typed`
- `images/src/skypictures/sun.py`
- `images/tests/conftest.py`
- `images/tests/fixtures/example_events.json`
- `images/tests/fixtures/example_pictures.json`
- `images/tests/fixtures/http/examples.json`
- `images/tests/fixtures/http/noaa.json`
- `images/tests/fixtures/images/panstarrs_outside_footprint.jpg`
- `images/tests/fixtures/images/rubin_science_cutout.png`
- `images/tests/fixtures/noaa_event.json`
- `images/tests/recording.py`
- `images/tests/test_cli.py`
- `images/tests/test_context.py`
- `images/tests/test_cutouts.py`
- `images/tests/test_examples.py`
- `images/tests/test_sun_earth.py`
- `images/uv.lock`
- `sources/.gitignore`
- `sources/.python-version`
- `sources/README.md`
- `sources/pyproject.toml`
- `sources/scripts/record_fixtures.py`
- `sources/src/skysources/__init__.py`
- `sources/src/skysources/alerts.py`
- `sources/src/skysources/classes.py`
- `sources/src/skysources/fink.py`
- `sources/src/skysources/heatmap.py`
- `sources/src/skysources/http.py`
- `sources/src/skysources/models.py`
- `sources/src/skysources/py.typed`
- `sources/src/skysources/schedule.py`
- `sources/src/skysources/solar_system.py`
- `sources/src/skysources/sso.py`
- `sources/src/skysources/status.py`
- `sources/src/skysources/util.py`
- `sources/tests/conftest.py`
- `sources/tests/contract.py`
- `sources/tests/fixtures/fink_ssobulk_subset.parquet`
- `sources/tests/fixtures/http/alerts_deep_field.json`
- `sources/tests/fixtures/http/alerts_ecliptic.json`
- `sources/tests/fixtures/http/heatmap.json`
- `sources/tests/fixtures/http/schedule.json`
- `sources/tests/fixtures/http/skybot.json`
- `sources/tests/fixtures/http/status.json`
- `sources/tests/fixtures/scenarios.py`
- `sources/tests/fixtures/skybot/10.0000_5.0000_0.5000_2461308.66667.xml`
- `sources/tests/fixtures/skybot/317.1800_-21.1000_0.3000_2461231.83898.xml`
- `sources/tests/recording.py`
- `sources/tests/test_alerts.py`
- `sources/tests/test_heatmap.py`
- `sources/tests/test_schedule.py`
- `sources/tests/test_solar_system.py`
- `sources/tests/test_status.py`
- `sources/tests/test_units.py`
- `sources/uv.lock`

</details>

<details><summary>API (26 files)</summary>

- `api/ci/ingest.yml`
- `api/ci/precompute.yml`
- `api/src/api/adapters/exoarchive.py`
- `api/src/api/adapters/real.py`
- `api/src/api/analysis.py`
- `api/src/api/fakes/archive.py`
- `api/src/api/fakes/tess.py`
- `api/src/api/ingest.py`
- `api/src/api/jobs.py`
- `api/src/api/known_systems.py`
- `api/src/api/lab.py`
- `api/src/api/lightcurve.py`
- `api/src/api/models.py`
- `api/src/api/precompute.py`
- `api/src/api/routes/analyze.py`
- `api/src/api/routes/events.py`
- `api/src/api/routes/stars.py`
- `api/src/api/spectra_index.py`
- `api/src/api/storage/events_sql.py`
- `api/tests/sample_events.py`
- `api/tests/test_analyze.py`
- `api/tests/test_events.py`
- `api/tests/test_fold.py`
- `api/tests/test_ingest.py`
- `api/tests/test_lab.py`
- `api/tests/test_precompute.py`

</details>

<details><summary>Web: routes, components, lib, tests, scripts (98 files)</summary>

- `web/app/events/[id]/page.tsx`
- `web/app/events/page.tsx`
- `web/app/lab/fingerprints/page.tsx`
- `web/app/lab/hear-a-star/page.tsx`
- `web/app/lab/hubble/page.tsx`
- `web/app/lab/layout.tsx`
- `web/app/lab/page.tsx`
- `web/app/lab/star/[tic]/page.tsx`
- `web/app/lab/thermometer/page.tsx`
- `web/app/sky/page.tsx`
- `web/components/events/EventImage.tsx`
- `web/components/events/events.module.css`
- `web/components/gallery/CompactSky.tsx`
- `web/components/gallery/EventPage.tsx`
- `web/components/gallery/Gallery.tsx`
- `web/components/lab/ChemicalFingerprint.tsx`
- `web/components/lab/Fingerprints.tsx`
- `web/components/lab/HearStar.tsx`
- `web/components/lab/Hubble.tsx`
- `web/components/lab/Intro.tsx`
- `web/components/lab/LabFrame.tsx`
- `web/components/lab/LabNav.tsx`
- `web/components/lab/Thermometer.tsx`
- `web/components/lab/data/build-mocks.mjs`
- `web/components/lab/data/build-star-lab.mjs`
- `web/components/lab/frame.module.css`
- `web/components/lab/index.module.css`
- `web/components/lab/physics.ts`
- `web/components/lab/spectra.ts`
- `web/components/lab/star/Card.tsx`
- `web/components/lab/star/HearCard.tsx`
- `web/components/lab/star/KeplerCard.tsx`
- `web/components/lab/star/MeasureCard.tsx`
- `web/components/lab/star/SpectraCards.tsx`
- `web/components/lab/star/StarLab.tsx`
- `web/components/lab/star/ThermoCard.tsx`
- `web/components/lab/star/shared.tsx`
- `web/components/lab/star/star.module.css`
- `web/components/lab/stars.ts`
- `web/components/lab/transit.ts`
- `web/components/map/EarthInset.tsx`
- `web/components/map/EventDetail.tsx`
- `web/components/map/FilterBar.tsx`
- `web/components/map/LayersControl.tsx`
- `web/components/map/Overlay.tsx`
- `web/components/map/RollingCount.tsx`
- `web/components/map/SkyMapApp.tsx`
- `web/components/map/StarDetail.tsx`
- `web/components/map/StatusBanner.tsx`
- `web/components/map/dismiss.ts`
- `web/components/map/filterModel.ts`
- `web/components/map/motion.ts`
- `web/components/map/scene/Constellations.tsx`
- `web/components/map/scene/Scene.tsx`
- `web/components/map/scene/constants.ts`
- `web/components/map/scene/flight.ts`
- `web/components/map/scene/markerFade.ts`
- `web/components/map/scene/noise.ts`
- `web/components/map/scene/rig.ts`
- `web/components/map/scene/shaders.ts`
- `web/components/map/scene/skyBake.ts`
- `web/components/map/scene/starShaders.ts`
- `web/components/map/scene/stars.tsx`
- `web/components/map/urlFilters.ts`
- `web/lib/galactic.ts`
- `web/lib/hosts.ts`
- `web/lib/images.ts`
- `web/lib/markers.ts`
- `web/lib/sky.ts`
- `web/lib/skyTexture.ts`
- `web/lib/starColor.ts`
- `web/lib/starColorTable.ts`
- `web/lib/sun.ts`
- `web/scripts/build-bright-stars.mjs`
- `web/scripts/build-events-mock.mjs`
- `web/scripts/build-hosts.mjs`
- `web/scripts/build-land.mjs`
- `web/scripts/build-picture-marks.mjs`
- `web/scripts/build-sky-objects.mjs`
- `web/scripts/build-sky.mjs`
- `web/scripts/build-star-colors.mjs`
- `web/scripts/rubin_footprint.py`
- `web/state/store.tsx`
- `web/tests/analyze.test.ts`
- `web/tests/flight.test.ts`
- `web/tests/galactic.test.ts`
- `web/tests/images.test.ts`
- `web/tests/lab/physics.test.ts`
- `web/tests/lab/spectra.test.ts`
- `web/tests/lab/transit.test.ts`
- `web/tests/map/dismiss.test.ts`
- `web/tests/map/filters.test.ts`
- `web/tests/map/markerFade.test.ts`
- `web/tests/markers.test.ts`
- `web/tests/rig.test.ts`
- `web/tests/sky.test.ts`
- `web/tests/skyTexture.test.ts`
- `web/tests/starColor.test.ts`

</details>

<details><summary>Web: data (28 files)</summary>

- `web/public/data/analysis/wasp-18/result.json`
- `web/public/data/analysis/wasp-18/tic100100827_sig1_folded.png`
- `web/public/data/bright-stars.json`
- `web/public/data/events.mock.json`
- `web/public/data/heatmap.rubin-sample.json`
- `web/public/data/lab/hubble.demo.json`
- `web/public/data/lab/spectra-mock/elements.json`
- `web/public/data/lab/spectra-mock/planets/wasp-121-b.atmosphere.json`
- `web/public/data/lab/spectra-mock/planets/wasp-18-b.atmosphere.json`
- `web/public/data/lab/spectra-mock/planets/wasp-39-b.atmosphere.json`
- `web/public/data/lab/spectra-mock/stars/100100827.abundances.json`
- `web/public/data/lab/spectra-mock/stars/100100827.gaia_xp.json`
- `web/public/data/lab/spectra-mock/stars/181949561.abundances.json`
- `web/public/data/lab/spectra-mock/stars/181949561.gaia_xp.json`
- `web/public/data/lab/spectra-mock/stars/22529346.abundances.json`
- `web/public/data/lab/spectra-mock/stars/22529346.gaia_xp.json`
- `web/public/data/lab/spectra-mock/sun_spectrum.json`
- `web/public/data/lab/star-lab.mock.json`
- `web/public/data/lab/wasp-121.result.json`
- `web/public/data/lab/wasp-18.result.json`
- `web/public/data/land-110m.json`
- `web/public/data/rubin-footprint.json`
- `web/public/data/sky-objects.json`
- `web/public/data/sky/LICENSE-d3-celestial.txt`
- `web/public/data/sky/constellation-bounds.json`
- `web/public/data/sky/constellation-lines.json`
- `web/public/data/sky/constellation-names.json`
- `web/public/data/status.mock.json`

</details>

<details><summary>Web: event and sky pictures (102 files)</summary>

- `web/public/images/events/donki-2026-08-08T18-00-00-GST-001.jpg`
- `web/public/images/events/donki-2026-09-20T22-38-00-CME-001.jpg`
- `web/public/images/events/donki-2026-09-21T09-09-00-CME-001.jpg`
- `web/public/images/events/donki-2026-09-24T02-53-00-CME-001.jpg`
- `web/public/images/events/donki-2026-09-24T09-23-00-CME-001.jpg`
- `web/public/images/events/donki-2026-09-24T14-45-00-CME-001.jpg`
- `web/public/images/events/donki-2026-09-25T11-09-00-CME-001.jpg`
- `web/public/images/events/gcn-GRB260924A.jpg`
- `web/public/images/events/gcn-GRB_260922A.jpg`
- `web/public/images/events/gcn-GRB_260924A.jpg`
- `web/public/images/events/gcn-GRB_260925A.jpg`
- `web/public/images/events/gracedb-S251117dq.jpg`
- `web/public/images/events/icecube-143143_38400235.jpg`
- `web/public/images/events/jpl-2026_SA8.jpg`
- `web/public/images/events/jpl-29P-Schwassmann-Wachmann.jpg`
- `web/public/images/events/jpl-3I-ATLAS.jpg`
- `web/public/images/events/rubin-170028485637046645.jpg`
- `web/public/images/events/rubin-170028485643862094.jpg`
- `web/public/images/events/rubin-170028485646483572.jpg`
- `web/public/images/events/rubin-170028485650153688.jpg`
- `web/public/images/events/rubin-170587117894238279.jpg`
- `web/public/images/events/rubin-313677516805505078.jpg`
- `web/public/images/events/rubin-313761043604045880.jpg`
- `web/public/images/events/rubin-314007345846812735.jpg`
- `web/public/images/events/rubin-obj-170587117839187981.jpg`
- `web/public/images/events/rubin-obj-170587117894238279.jpg`
- `web/public/images/events/tns-2026aagh.jpg`
- `web/public/images/events/tns-2026aajs.jpg`
- `web/public/images/events/tns-2026abvs.jpg`
- `web/public/images/events/tns-2026acna.jpg`
- `web/public/images/events/tns-2026acow.jpg`
- `web/public/images/events/tns-AT2017gfo.jpg`
- `web/public/images/events/ztf-ZTF18aaaaljy.jpg`
- `web/public/images/events/ztf-ZTF18aahouhg.jpg`
- `web/public/images/events/ztf-ZTF18abuvchc.jpg`
- `web/public/images/events/ztf-ZTF22abegjtx.jpg`
- `web/public/images/events/ztf-ZTF25abdfzfi.jpg`
- `web/public/images/events/ztf-ZTF26abemjfk.jpg`
- `web/public/images/events/ztf-ZTF26abeqbvy.jpg`
- `web/public/images/events/ztf-ZTF26abkjlpd.jpg`
- `web/public/images/events/ztf-ZTF26abnuiar.jpg`
- `web/public/images/events/ztf-ZTF26abspxxp.jpg`
- `web/public/images/events/ztf-ZTF26abussvm.jpg`
- `web/public/images/events/ztf-ZTF26abwacec.jpg`
- `web/public/images/events/ztf-ZTF26abwpoui.jpg`
- `web/public/images/events/ztf-ZTF26abxaktw.jpg`
- `web/public/images/feature/PIA11984.jpg`
- `web/public/images/feature/noirlab2521a.jpg`
- `web/public/images/feature/weic2205a.jpg`
- `web/public/images/sky/eso0932a-3072.jpg`
- `web/public/images/sky/eso0932a-6000.jpg`
- `web/public/images/sky/where/gcn-GRB260924A.jpg`
- `web/public/images/sky/where/gcn-GRB_260921B.jpg`
- `web/public/images/sky/where/gcn-GRB_260922A.jpg`
- `web/public/images/sky/where/gcn-GRB_260923A.jpg`
- `web/public/images/sky/where/gcn-GRB_260924A.jpg`
- `web/public/images/sky/where/gcn-GRB_260925A.jpg`
- `web/public/images/sky/where/gracedb-S251117dq.jpg`
- `web/public/images/sky/where/icecube-143143_38400235.jpg`
- `web/public/images/sky/where/jpl-2026_SA8.jpg`
- `web/public/images/sky/where/jpl-29P-Schwassmann-Wachmann.jpg`
- `web/public/images/sky/where/jpl-3I-ATLAS.jpg`
- `web/public/images/sky/where/jpl-P-2026_R1.jpg`
- `web/public/images/sky/where/mpc-A11H8ut.jpg`
- `web/public/images/sky/where/mpc-A11Hfh5.jpg`
- `web/public/images/sky/where/mpc-C46K1R1.jpg`
- `web/public/images/sky/where/mpc-JAN1359.jpg`
- `web/public/images/sky/where/mpc-LSs0088.jpg`
- `web/public/images/sky/where/mpc-LSs0092.jpg`
- `web/public/images/sky/where/mpc-P12qyGM.jpg`
- `web/public/images/sky/where/mpc-P22qwo3.jpg`
- `web/public/images/sky/where/mpc-TR0000.jpg`
- `web/public/images/sky/where/rubin-170028485637046645.jpg`
- `web/public/images/sky/where/rubin-170028485643862094.jpg`
- `web/public/images/sky/where/rubin-170028485646483572.jpg`
- `web/public/images/sky/where/rubin-170028485650153688.jpg`
- `web/public/images/sky/where/rubin-170587117894238279.jpg`
- `web/public/images/sky/where/rubin-313677516805505078.jpg`
- `web/public/images/sky/where/rubin-313761043604045880.jpg`
- `web/public/images/sky/where/rubin-314007345846812735.jpg`
- `web/public/images/sky/where/rubin-obj-170587117839187981.jpg`
- `web/public/images/sky/where/rubin-obj-170587117894238279.jpg`
- `web/public/images/sky/where/tns-2026aagh.jpg`
- `web/public/images/sky/where/tns-2026aajs.jpg`
- `web/public/images/sky/where/tns-2026abvs.jpg`
- `web/public/images/sky/where/tns-2026acna.jpg`
- `web/public/images/sky/where/tns-2026acow.jpg`
- `web/public/images/sky/where/tns-AT2017gfo.jpg`
- `web/public/images/sky/where/ztf-ZTF18aaaaljy.jpg`
- `web/public/images/sky/where/ztf-ZTF18aahouhg.jpg`
- `web/public/images/sky/where/ztf-ZTF18abuvchc.jpg`
- `web/public/images/sky/where/ztf-ZTF22abegjtx.jpg`
- `web/public/images/sky/where/ztf-ZTF25abdfzfi.jpg`
- `web/public/images/sky/where/ztf-ZTF26abemjfk.jpg`
- `web/public/images/sky/where/ztf-ZTF26abeqbvy.jpg`
- `web/public/images/sky/where/ztf-ZTF26abkjlpd.jpg`
- `web/public/images/sky/where/ztf-ZTF26abnuiar.jpg`
- `web/public/images/sky/where/ztf-ZTF26abspxxp.jpg`
- `web/public/images/sky/where/ztf-ZTF26abussvm.jpg`
- `web/public/images/sky/where/ztf-ZTF26abwacec.jpg`
- `web/public/images/sky/where/ztf-ZTF26abwpoui.jpg`
- `web/public/images/sky/where/ztf-ZTF26abxaktw.jpg`

</details>

<details><summary>Web: design screenshots (81 files)</summary>

- `web/docs/graphics-pass/1440-1-default.jpg`
- `web/docs/graphics-pass/1440-2-midflight.jpg`
- `web/docs/graphics-pass/1440-3-red-dwarf.jpg`
- `web/docs/graphics-pass/1440-4-blue-white.jpg`
- `web/docs/graphics-pass/390-1-default.jpg`
- `web/docs/graphics-pass/390-2-midflight.jpg`
- `web/docs/graphics-pass/390-3-red-dwarf.jpg`
- `web/docs/graphics-pass/390-4-blue-white.jpg`
- `web/docs/lab/1440-hear-folded.jpg`
- `web/docs/lab/1440-hear-playing.jpg`
- `web/docs/lab/1440-hubble-distance.jpg`
- `web/docs/lab/1440-hubble-fit.jpg`
- `web/docs/lab/1440-lab.jpg`
- `web/docs/lab/1440-lab_fingerprints.jpg`
- `web/docs/lab/1440-lab_hear-a-star.jpg`
- `web/docs/lab/1440-lab_hubble.jpg`
- `web/docs/lab/1440-lab_thermometer.jpg`
- `web/docs/lab/1440-map-bright-deeplink.jpg`
- `web/docs/lab/1440-map-host-deeplink.jpg`
- `web/docs/lab/1440-map-lablink.jpg`
- `web/docs/lab/1440-sun-telluric.jpg`
- `web/docs/lab/1440-thermo-picked.jpg`
- `web/docs/lab/390-hear-playing-reduced.jpg`
- `web/docs/lab/390-lab.jpg`
- `web/docs/lab/390-lab_fingerprints.jpg`
- `web/docs/lab/390-lab_hear-a-star.jpg`
- `web/docs/lab/390-lab_hubble.jpg`
- `web/docs/lab/390-lab_thermometer.jpg`
- `web/docs/lab/390-map-host-deeplink.jpg`
- `web/docs/lab/390-sun-telluric.jpg`
- `web/docs/lab/star/map-open-in-lab.jpg`
- `web/docs/lab/star/pollux-1440.jpg`
- `web/docs/lab/star/pollux-390-locked.jpg`
- `web/docs/lab/star/wasp121-1440.jpg`
- `web/docs/lab/star/wasp121-390-top.jpg`
- `web/docs/lab/star/wasp39-after-1440.jpg`
- `web/docs/lab/star/wasp39-analyzing.jpg`
- `web/docs/lab/star/wasp39-before-1440.jpg`
- `web/docs/mapui/1440-chips-toggled.png`
- `web/docs/mapui/1440-default.png`
- `web/docs/mapui/1440-empty-state.png`
- `web/docs/mapui/1440-layers-open.png`
- `web/docs/mapui/1440-more-open.png`
- `web/docs/mapui/390-chips-toggled.png`
- `web/docs/mapui/390-default.png`
- `web/docs/mapui/390-empty-state.png`
- `web/docs/mapui/390-layers-open.png`
- `web/docs/mapui/390-more-open.png`
- `web/docs/mapui/README.md`
- `web/docs/mapui/audit.md`
- `web/docs/mapui/filter-fade-frames.png`
- `web/docs/mapui/filter-fade.gif`
- `web/docs/spotmap/1440-1-default.jpg`
- `web/docs/spotmap/1440-1b-marker-click.jpg`
- `web/docs/spotmap/1440-2-filters.jpg`
- `web/docs/spotmap/1440-3-supernova-detail.jpg`
- `web/docs/spotmap/1440-4-solar-flare-detail.jpg`
- `web/docs/spotmap/1440-5-fireball-detail.jpg`
- `web/docs/spotmap/1440-6-red-dwarf.jpg`
- `web/docs/spotmap/1440-7-blue-white.jpg`
- `web/docs/spotmap/1440-8-zoom-after.jpg`
- `web/docs/spotmap/1440-8-zoom-before.jpg`
- `web/docs/spotmap/1440-8-zoom-crops-before-after.png`
- `web/docs/spotmap/1440-analyze-done.jpg`
- `web/docs/spotmap/1440-analyze-result.jpg`
- `web/docs/spotmap/1440-analyze-running.jpg`
- `web/docs/spotmap/1440-bright-star-panel.jpg`
- `web/docs/spotmap/1440-default-after-hosts-on.jpg`
- `web/docs/spotmap/1440-default-after.jpg`
- `web/docs/spotmap/1440-default-before.jpg`
- `web/docs/spotmap/1440-filters-scrolled-end.jpg`
- `web/docs/spotmap/1440-fireball-report-time.jpg`
- `web/docs/spotmap/1440-markers-crop-before-after.jpg`
- `web/docs/spotmap/1440-stars-off-hint.jpg`
- `web/docs/spotmap/390-1-default.jpg`
- `web/docs/spotmap/390-2-filters-sheet.jpg`
- `web/docs/spotmap/390-3-feed-sheet.jpg`
- `web/docs/spotmap/390-4-detail-sheet.jpg`
- `web/docs/spotmap/390-5-shown-on-map.jpg`
- `web/docs/spotmap/390-6-solar-flare-sheet.jpg`
- `web/docs/spotmap/390-star-sheet.jpg`

</details>

# skyspectra: chemical fingerprints for planet-hunter

Every element absorbs and emits light at its own wavelengths. That is how we know what stars and
planets are made of. This package fetches the **real** data behind the web LAB's "Chemical
fingerprints" view and writes it as small static JSON files.

```sh
uv run skyspectra build --out DIR [--tic-file FILE] [--only elements sun stars planets]
```

`--tic-file` picks the host stars. It accepts the map's `hosts.json` (an object with a `tic` list),
a JSON list of TIC ids, or plain text with one TIC per line. Without it, every host in the NASA
Exoplanet Archive is used. For the map:

```sh
uv run skyspectra build --out data --tic-file ../web/public/data/hosts.json
```

**The built data set for the 1,749 map hosts is committed in [`data/`](data/)**: 2,408 files,
17.4 MB of compact JSON. Floats are rounded to 4 significant figures, except wavelengths, which
keep their native precision. At 4 significant figures, neighbouring 0.08 nm solar bins, the Na D
lines, and JWST points 0.0014 µm apart would collapse onto each other. It contains 898 stars with
abundances, 1,395 with Gaia XP spectra, and 111 planets with transmission spectra (6 with
curated detections). Rerun the command above to refresh it.

You don't need any accounts, keys or signups. Every answer is cached in `SKYSPECTRA_CACHE`
(default `~/.cache/skyspectra`), and each host is rate-limited (0.5 to 1 s between requests). The
first full run for the 1,749 map hosts takes about 1.5 hours: about 25 minutes of Hypatia and
about 1 hour of Gaia DataLink, which takes about 1 s per star. A rerun from a warm cache takes seconds.

## Output (the LAB contract)

| file | content |
|---|---|
| `elements.json` | `[{symbol, name, lines:[{nm, relative_intensity, species, ion, nist_intensity, aki_per_s?}], source, credit, licence, version, citation}]` for 20 elements (H He Li C N O Na Mg Al Si S K Ca Ti Cr Mn Fe Ni Sr Ba). Air wavelengths, 300 to 1100 nm. Each species gets its strongest visible lines plus a few near-UV/IR ones, and every Fraunhofer line labelled in the Sun file is included. `relative_intensity` is 1.0 for the strongest line **of that species** (NIST intensities are only comparable within one spectrum). |
| `sun_spectrum.json` | `{wavelength_nm[], flux[], lines:[{nm, element, label, origin, atlas_min_nm, atlas_min_flux, telluric}], source, credit, licence}`. The Kurucz 2005 Kitt Peak solar flux atlas: residual flux (continuum = 1) averaged into 0.08 nm bins, 4,875 points over 380 to 770 nm. The window runs to 770 nm so that it includes the O2 A band. There are 16 solar lines with `"origin": "sun"`: Ca II K and H, the Balmer lines H-alpha to H-delta, Ca I g, the G band, Fe I c, d and E2, Mg b1, b2 and b4, and Na D1 and D2. A solar label is kept only if the full-resolution atlas has a real line core within 0.04 nm that is at least 15% deep. There are also 3 telluric features with `"origin": "earth_atmosphere"`: the O2 A band (759 nm), the O2 B band (687 nm) and the H2O a band (718 nm), made by Earth's air above Kitt Peak. |
| `stars/<tic>.abundances.json` | `{tic, name, hypatia_name, elements:[{symbol, x_h_dex, err_dex, n_catalogs, references}], source, credit, licence}`. These are Hypatia Catalog median [X/H] values (Lodders 2009 solar scale), and `err_dex` is Hypatia's `plusminus`. One file for each host that Hypatia has abundances for. |
| `stars/<tic>.gaia_xp.json` | `{tic, name, gaia_dr3_source_id, wavelength_nm[343], flux[], flux_error[], flux_unit, source, credit, licence}`. The Gaia DR3 XP sampled mean spectrum: 336 to 1020 nm in 2 nm steps, in W m⁻² nm⁻¹. |
| `planets/<slug>.atmosphere.json` | `slug` is the lowercase name with spaces turned into hyphens (`WASP-121 b` → `wasp-121-b`). `{planet, host, tic, detections:[{species, instrument, reference:{title, authors, year, journal, doi, doi_url, ads}, status, note?, abstract_quote, curated:true}], detections_note, spectrum:{wavelength_um[], depth_ppm[], err_ppm[], bandwidth_um[], depth_from, reference, bibcode, instrument, facility, …}\|null, spectra_available:[…], source, credit, licence}`. These are NASA Exoplanet Archive transmission spectra. The spectrum with the most points is kept, and every other published one is listed. `detections` comes from the curated list below. |
| `planets/detections_curated.json` | 46 hand-curated detections for 10 well-studied planets: WASP-121 b, WASP-39 b, HD 209458 b, HD 189733 b, WASP-17 b, K2-18 b, TRAPPIST-1 b (none, explained in a note), 55 Cnc e, GJ 1214 b and WASP-96 b. Every entry was taken from the paper's own abstract (`abstract_quote`), with bibliographic data checked against Crossref. `status` is `detected`, `tentative` (the abstract hedges) or `contested` (a later peer-reviewed paper disputes it, cited in `note`). These are merged into the matching planet files. 55 Cnc e, HD 209458 b and HD 189733 b are not map hosts, so their curations appear only in this file. The ADS links follow the standard bibcode format but could not be opened automatically, because ADS blocks scripts. The DOI is the verified link. |
| `index.json` | Counts, `total_bytes`, and every file per TIC and per planet with its byte size. It also holds the full sources/licences table and `requested_tics_not_in_archive`. |

Extra fields beyond the contract are additive. The LAB can ignore them.

## Sources and licences

| data | source | licence / terms |
|---|---|---|
| Line lists | NIST Atomic Spectra Database v5.12 (Kramida et al. 2024, doi:10.18434/T4W30F) | NIST Standard Reference Data. It is free online but copyrighted by the U.S. Secretary of Commerce (15 U.S.C. §290e), and must be cited. |
| Solar spectrum | Kurucz 2005 Kitt Peak Solar Flux Atlas (Kurucz 2005, MSAIS 8, 189; FTS data by Kurucz, Furenlid, Brault & Testerman 1984) | No licence is stated. R. L. Kurucz distributes it publicly for scientific use. Cite Kurucz (2005). |
| Stellar abundances | Hypatia Catalog API v2.2 (Hinkel et al. 2014, AJ 148, 54) | Free, and no key is needed. No explicit licence is stated. Cite Hinkel et al. (2014). |
| Stellar spectra | Gaia DR3 XP sampled spectra via the ESA Gaia Archive DataLink (De Angeli et al. 2023; Montegriffo et al. 2023) | CC BY-SA 3.0 IGO. Credit ESA/Gaia/DPAC. |
| Curated detections | The cited papers' abstracts, curated by hand for planet-hunter | Compilation CC0 1.0. The short abstract quotes are for attribution; their copyright stays with the publishers. |
| Planet atmospheres | NASA Exoplanet Archive Atmospheric Spectroscopy table (TAP `spectra`) and its spectrum files | Public, with the archive acknowledgement required. Also cite each spectrum's paper (`reference`, `bibcode`). |

Every output file carries its own `source`, `credit` and `licence`. Because `elements.json` is a
list, those fields are on each element in it.

## Caveats

- **Detections are curated, not scraped.** The NASA Exoplanet Archive records spectra, not which
  species each paper claims to detect. The IAC ExoAtmospheres database has per-planet species but
  states no licence, so it is not used. Instead, `detections` comes only from the hand-curated
  list, and every other planet has `detections: []`. To add a planet, edit
  `src/skyspectra/detections_curated.json`; `tests/test_atmospheres.py` checks its shape.
- The archive serves spectrum files under a per-visit workspace path taken from its atmospheres
  viewer page (`/workspace/TMP_…/atmospheres/tab1/data/<spec_path>`). This is how the viewer
  itself loads them, but the path is not a documented API. If the page changes, planets still get
  files, with `spectrum: null` and `spectra_available` filled from TAP.
- Relative intensities in NIST depend on the light source used, so they are only a guide to
  which lines are strong.

## Tests

```sh
uv run pytest               # offline: replays recorded real responses
uv run python scripts/record.py   # re-record tests/fixtures/http/sample.json.gz from the live services
```

The fixture is a real recording of every request for a small sample: H, Na, Ca and Fe; the Na D
and Ca H&K windows of the atlas; WASP-121 and HD 189733; and TIC 1, which is not a host. Three big
answers are trimmed to the rows the sample uses: the atlas, and the archive's host and spectrum
tables.

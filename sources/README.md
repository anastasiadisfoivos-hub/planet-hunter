# skysources

Data clients for planet-hunter's sky: Rubin/LSST alert-broker objects, Rubin's visit schedule,
known solar-system objects, and a whole-sky heatmap. Python 3.12, `uv`. No logins or API keys.

```python
from skysources import alerts, schedule, known_solar_system, build_heatmap

sphere = {"ra_deg": 317.18, "dec_deg": -21.1, "radius_deg": 0.3}
alerts(sphere, "2026-07-10T00:00:00Z", "2026-07-11T12:00:00Z")   # -> list[Discovery]
schedule(sphere, "2026-07-10T00:00:00Z", "2026-07-12T00:00:00Z") # -> list[Visit]
known_solar_system(sphere, "2026-09-25T04:00:00Z")               # -> list[KnownSolarSystemObject]
build_heatmap(nights=3)                                          # -> heatmap.json dict
```

```sh
uv sync
uv run pytest                                          # offline, replays recorded real responses
uv run skysources-heatmap --nights 3 --out heatmap.json                 # window ends now
uv run skysources-heatmap --nights 3 --until latest --out heatmap.json  # ends at last night with alerts
uv run python scripts/record_fixtures.py               # re-record fixtures (network)
```

Shapes follow the SHARED CONTRACT exactly ([models.py](src/skysources/models.py)).

## Where the data comes from

| Function | Service | Login |
|---|---|---|
| `alerts` | [Fink LSST API](https://api.lsst.fink-portal.org) `/conesearch` (+ `/sso`, `/ssobulk`, `/cutouts`, `/sources`) | none |
| `schedule` | Rubin [ObsLocTAP](https://usdf-rsp.slac.stanford.edu/obsloctap/) `/schedule` ([docs](https://obsloctap.lsst.io), [code](https://github.com/lsst-dm/obsloctap)) | none |
| `known_solar_system` | IMCCE [SkyBoT](https://ssp.imcce.fr/webservices/skybot/) via `astroquery.imcce.Skybot`, observatory X05 (Rubin) | none |
| `build_heatmap` | [ALeRCE LSST](https://api-lsst.alerce.online/object_api/docs) `list_objects` + Fink `/ssobulk` | none |

### Why Fink

Among the brokers that carry LSST alerts (checked 2026-09-25):

| Broker | LSST without login | Cone search | Class + confidence | Cutouts |
|---|---|---|---|---|
| **Fink** | yes | yes, ≤ 5°, with time window | CATS class + score; SIMBAD / TNS / VSX / Gaia cross-match | PNG/FITS URL, science / template / difference |
| ALeRCE | yes | yes (arcsec) | stamp classifier SN/AGN/VS/asteroid/bogus + probability | endpoint returned HTTP 500 for every LSST object tried |
| ANTARES | yes | Elasticsearch `sky_distance` | filter tags, no single probability | public PNGs |
| Lasair | API needs a token (free account) | ≤ 1000″ | Sherlock context class, no probability | FITS public |
| Babamul | stats only; data needs a JWT | — | boolean filters | token |
| Pitt-Google | needs a Google Cloud project (requester-pays) | BigQuery | UPSILoN / SuperNNova | Avro in paid bucket |
| AMPEL | archive host did not resolve | — | — | — |

Fink is the only one with all four: no login, cone + time window, a class **with a number**,
and working cutout URLs. It also exposes Rubin's own IDs (`diaObjectId`, `ssObjectId`,
`diaSourceId`). ALeRCE is used only for the heatmap, where a fast whole-sky listing matters
and cutouts don't.

## IDs: one Discovery per object

- `rubin:obj:<diaObjectId>`: Fink cone-search rows (one row per diaObject, carrying its latest
  alert). `detected_at` and cutouts come from that latest alert; `raw.alert_count` =
  `r:nDiaSources`. `raw.first_detected_at` is the first alert.
- `rubin:ss:<ssObjectId>`: Rubin detections linked to a catalogued orbit, from Fink's SSO bulk
  file. Rubin's `ssObjectId` is the packed MPC provisional designation read as a big-endian
  integer (`2011 BU146` → `K11BE6U` → `21164710888289877`). It is taken from Fink `/sso` when
  that call is made, and otherwise computed; tests check the two agree.
  About 0.03% of objects have old `A924 EV`-style designations that Fink can't resolve. Those
  fall back to `rubin:ss:<designation>`.

## Class → CatchType mapping

The first rule that matches decides the type. Code: [classes.py](src/skysources/classes.py).

**Static-sky objects (Fink)**

| Order | Field | Broker label | CatchType | confidence |
|---|---|---|---|---|
| 1 | `f:xm_tns_type` | `SN…`, `SLSN…` | supernova | 1.0 (reported classification) |
| | | `TDE…` | tidal_disruption_event | 1.0 |
| | | `Kilonova` | kilonova | 1.0 |
| | | `AGN`, `QSO`, `Blazar` | active_galaxy | 1.0 |
| | | `M dwarf` (flare) | flare | 1.0 |
| | | `Nova`, `CV`, `LBV`, `Varstar` | variable_star | 1.0 |
| | | `Microlens…` | microlensing | 1.0 |
| 2 | `f:xm_simbad_otype` (≤ 1″) | `SN*`, `SN?` | supernova | 1.0 |
| | | `QSO`, `AGN`, `Sy1`, `Sy2`, `SyG`, `Bla`, `BLL`, `LIN` (+ `?` forms) | active_galaxy | 1.0 |
| | | `EB*`, `El*` (+ `?`) | eclipsing_binary | 1.0 |
| | | `Fl*`, `Fl?` | flare | 1.0 |
| | | `Lev`, `LeI` | microlensing | 1.0 |
| | | `Pl`, `Pl?` | planet_candidate | 1.0 |
| | | `V*`, `RR*`, `Ce*`, `dS*`, `LP*`, `Mi*`, `Ro*`, `BY*`, `RS*`, `CV*`, `No*`, `Y*O`, `TT*`, `Be*`, `WR*` … (full list in code) | variable_star | 1.0 |
| | | `G`, `*` and other host/position types | *(no override; falls through)* | |
| 3 | `f:xm_vsx_Type` | `E`, `EA`, `EB`, `EW`, `ELL` … | eclipsing_binary | 1.0 |
| | | `UV`, `UVN`, `FLARE` | flare | 1.0 |
| | | any other VSX type | variable_star | 1.0 |
| 4 | `f:clf_cats_class` (CATS) | 11 SN-like | supernova | `f:clf_cats_score` |
| | | 12 Fast (kilonova / microlensing / nova) | unknown | score |
| | | 13 Long (superluminous SN / TDE) | unknown | score |
| | | 21 Periodic (RR Lyrae / eclipsing binary) | variable_star | score |
| | | 22 Non-periodic (AGN) | active_galaxy | score |
| | | -1 not processed | unknown | 0.0 |

CATS 12 and 13 are groups that mix several of our types, so they map to `unknown` rather than a
guess. The explanation text still names the group.

**Solar-system objects**

| Source | Label | CatchType |
|---|---|---|
| SkyBoT class | `NEA>…` (Apollo/Aten/Amor/Atira) | near_earth_object |
| | `KBO>…`, `TNO…` | trans_neptunian_object |
| | `Comet…` | comet |
| | `MB>…`, `Hungaria`, `Mars-Crosser`, `Trojan`, `Centaur`, other | asteroid |
| designation | `nI/…` | interstellar_object |
| | `C/`, `P/`, `D/`, `X/`, `nP` | comet |
| distance from the Sun at detection (when SkyBoT has no class) | r ≥ 30.07 AU | trans_neptunian_object |
| | r < 1.3 AU (so perihelion < 1.3 AU) | near_earth_object |
| | otherwise | asteroid |

For `alerts()`, SSO confidence is 1.0: Rubin linked the detection to a catalogued orbit. Each
distance rule is a sufficient condition, so the type can be too generic (an NEA seen at 2 AU
stays "asteroid") but not wrong.

**Heatmap (ALeRCE stamp classifier, top class)**: `SN`→supernova, `AGN`→active_galaxy,
`VS`→variable_star, `bogus`→dropped. ALeRCE `asteroid` is skipped, because known
solar-system objects come from Fink's SSO file and use the rules above.

`known_status`: `known` if Fink found a SIMBAD or Gaia DR3 counterpart (`f:is_cataloged`), a
TNS name, a VSX match, or it's a solar-system object; otherwise `not_on_lists`.

## Heatmap

`{generated_at, grid: "healpix nside=32", cells: [{pix, counts}]}`. The grid uses **RING
ordering** (the healpy / astropy-healpix default) and only non-empty cells are listed.
Each count is one object with alerts in the window, counted at its position.

## Rate limits and behaviour seen

Every client allows at most one request per second per host (ALeRCE: 2/s). Answers are cached
on disk (`~/.cache/skysources`, override with `SKYSOURCES_CACHE`, disable with
`SKYSOURCES_NO_CACHE=1`): 15 min for windows reaching into the future, 6 h for past ones, 24 h
for the Fink SSO bulk file. Requests retry on 429 or 5xx and honour `Retry-After`.

| Service | Documented limit | Seen |
|---|---|---|
| Fink | none published, no rate headers | 120 s server timeout; a 1° all-time cone took 48 s, a 0.3–0.5° one-night cone 8–16 s; SSO bulk is ~38 MB |
| ALeRCE | none published | pages of 5000 take 10–48 s; one night ≈ 100k SN/AGN/VS objects ≈ 2.5 min |
| ObsLocTAP | none | `time=0` queries are capped at 1000 rows (we split the window) |
| SkyBoT | none | cones ≥ 1.75° **with planets** fail as HTTP 200 + `flag -1`; we exclude planets |
| Lasair (not used) | 100 calls/h with a free token | |

## Known gaps (as of 2026-09-25)

- **The Rubin alert stream has been quiet since 2026-07-14** at every broker checked (Fink,
  ALeRCE, Lasair, ANTARES, Babamul), so `alerts()` and `build_heatmap()` for recent windows
  are empty. Use `--until latest` to anchor on the last night with data.
- **ObsLocTAP's newest row is from 2026-09-11**, so future windows return `[]`. It has no
  public TAP/ADQL, only the REST `/schedule` wrapper; the table includes Performed and
  Aborted visits, which are how we cover past windows (aborted ones are dropped unless
  `include_aborted=True`).
- `detected_at` is the object's latest alert that Fink knows about, which can fall after
  `until` for a past window.
- Fink's cone search only returns objects whose first detection or activity falls in the window
  (`kind=across`). Objects that sat quiet through the whole window are left out.

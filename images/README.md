# skypictures

Real pictures for planet-hunter's sky events. Given an `Event` (SHARED EVENT CONTRACT,
[models.py](src/skypictures/models.py)) it returns `list[Image]`: survey cutouts, a colour
picture of that exact patch of sky, the Sun at the time of a flare, or NOAA's aurora forecast map.
Each `Image` carries `url` (full size) and `thumb_url` (a smaller rendering from the same source, or
the same URL when the source has only one size; `null` only on images from elsewhere that lack one).
Nothing is generated or painted. Every image has a credit, a licence and a caption that says
what it shows. Python 3.12, `uv`, no logins or API keys.

```python
from skypictures import pictures_for

images = pictures_for(event)        # checked: dead, non-image and blank URLs dropped
images = pictures_for(event, check=False)   # no network for the checks (width/height = None)
```

```sh
uv sync
uv run pytest                                            # offline, replays recorded real answers
uv run skypictures events.json -o site/events.json       # enrich every event; prints dead-link stats
uv run --group examples python scripts/examples.py       # rebuild the 20 real examples (network)
uv run python scripts/record_noaa.py                     # re-record the aurora-map checks (network)
```

The CLI accepts a JSON list of events, or an object with an `events` list (other keys are kept).
Images already on an event are kept, re-checked and de-duplicated. Nothing is downloaded for
re-hosting: every image links to its source (the site's host keeps no disk).

[EXAMPLES.md](EXAMPLES.md) has one real event per type with every image URL, caption and credit.

## What each event type gets

Display order: `sky_context` (the colour picture comes first), `solar`, `forecast_map`, then `cutout_reference`
→ `cutout_new` → `cutout_difference` (before, after, what changed).

| Frame | Types | Pictures |
|---|---|---|
| sky | supernova, tidal_disruption_event, kilonova, nova, active_galaxy_flare, variable_star, stellar_flare, microlensing, asteroid, unknown | colour sky context, plus Rubin or ZTF cutouts when the event carries a Rubin `diaSourceId` or a ZTF `objectId` |
| sky | near_earth_object, comet, interstellar_object, gamma_ray_burst, neutrino, gravitational_wave | colour sky context (wider, or sized to the error region); cutouts too if a survey ID is present |
| sun | solar_flare | SDO/AIA 131 Å at the flare peak (or reported time), with the reported region described |
| sun | coronal_mass_ejection | SDO/AIA 193 Å, plus SOHO LASCO C2 (else C3) from 0–3 h after the reported time |
| earth | geomagnetic_storm | `forecast_map`: NOAA's latest aurora forecast for the matching hemisphere (both if no latitude), only while the storm is ongoing / began in the last 24 h |
| earth | fireball | nothing: CNEOS reports have no imagery, and none is made up |

### Survey cutouts (Fink)

- Rubin: `https://api.lsst.fink-portal.org/api/v1/cutouts?diaSourceId=…&kind=Template|Science|Difference&output-format=PNG`
  (0.2″ per pixel, 30–60 px seen). The ID is read from `raw.latest_diaSourceId` (what skysources
  writes), `diaSourceId` / `r:diaSourceId` anywhere in `raw`, or the Fink cutout URLs in `raw.cutouts`.
- ZTF: `https://api.ztf.fink-portal.org/api/v1/cutouts?objectId=…&candid=…` (1″ per pixel, 63 px).
  `objectId` comes from `raw` or a `ZTF…` name in `id` / `source_url`. Without a `candid` it is
  Fink's latest alert for the object, and the caption says so.
- Rubin is used when both are present. The PNGs are small: show them with `image-rendering: pixelated`.

### Sky context (CDS hips2fits)

`https://alasky.cds.unistra.fr/hips-image-services/hips2fits?hips=…&width=800&height=800&fov=…&ra=…&dec=…&format=jpg`,
thumbnail 256 px. The image is centred on the event, and the caption gives the position ("Crosshair:
… at the exact centre, RA …, Dec …").

- **Survey**: the first colour survey whose footprint contains the point, according to the CDS
  MocServer: DESI Legacy Surveys DR10 → Pan-STARRS1 → DSS2 (all-sky). Fields wider than 0.5° use DSS2.
- **Field of view**: host-galaxy scale for extragalactic transients (2.5′ supernova/kilonova,
  1.5′ TDE/AGN), 1.5′ for stars, 20–30′ for asteroids/NEOs/comets, and 2.4 × the error radius
  when that is larger (capped at 60°).
- **Honesty**: these are archival pictures. Captions say when the survey was taken and that the
  transient or moving object is not in it, or that the star is shown as it was then. Outside its
  footprint Pan-STARRS returns an all-white frame; the pixel check rejects it.

### The Sun (NASA SDO, SOHO via Helioviewer)

- SDO's own archive of static JPEGs (`https://sdo.gsfc.nasa.gov/assets/img/browse/YYYY/MM/DD/…_1024_0131.jpg`,
  thumbnail `_512_`): the nearest frame within 2 h is taken from the day's directory listing.
- If there is none, Helioviewer `getClosestImage` + `downloadImage` (within 6 h).
- LASCO frames come from Helioviewer and must fall 0–3 h after the CME time. A frame from before
  the CME cannot show it, so none is returned rather than a misleading one.
- Regions like `N14E90` (from `raw.sourceLocation`, as DONKI gives it, or found in `raw` / `summary`)
  are put in plain words in the caption: "on the left (east) edge of the disk, 14° north of the equator".

### Aurora maps (NOAA SWPC)

The stable "latest" images NOAA's [product page](https://www.swpc.noaa.gov/products/aurora-30-minute-forecast)
uses: `https://services.swpc.noaa.gov/images/aurora-forecast-{northern,southern}-hemisphere.jpg`
(800 px, one size, so `thumb_url` = `url`). Kind `forecast_map`, caption "NOAA aurora forecast,
latest (model): …, not a photograph". The picture behind the URL refreshes every few minutes, so it
is only attached while it can still describe the storm: ongoing or begun within the last 24 h.
Older storms get none. (SWPC's time-stamped frames are deleted after about a day, and re-hosting is
not an option, so there is no way to show a past storm's map.)

## Dead links

`pictures_for` fetches each URL once (GET, because hips2fits answers HEAD with 405). It keeps the URL
only if it returns HTTP 200 with an image content type, Pillow can decode it, and it is not a single
flat colour. True `width`/`height` come from that decode. Results are cached in `~/.cache/skypictures`
(`SKYPICTURES_CACHE`): good answers for 7 days, failures for 1 hour. One source failing never costs an
event its other pictures. The CLI prints how many URLs it checked and dropped, and why.

## Credits and licences

Read on 2026-09-25 from each source's terms page and, for HiPS, its `properties` file
(`obs_copyright`, `hips_license`). Code: [credits.py](src/skypictures/credits.py).

| Source | Credit line | Licence / terms |
|---|---|---|
| Rubin cutouts (Fink) | NSF–DOE Vera C. Rubin Observatory / LSST; cutout served by the Fink broker | World-public alert data, no proprietary period ([Rubin](https://rubinobservatory.org/for-scientists/data-products/alerts-and-brokers)) |
| ZTF cutouts (Fink) | Zwicky Transient Facility (Caltech / Palomar Observatory); cutout served by the Fink broker | ZTF public alert stream, credit ZTF and Fink |
| DESI Legacy Surveys DR10 | … colour HiPS by CDS; cut with CDS hips2fits | Public data, acknowledgement required ([terms](https://www.legacysurvey.org/acknowledgment/)); HiPS ODbL-1.0 |
| Pan-STARRS1 DR1 | PS1 Science Consortium via MAST/STScI; HiPS by CDS | Public release, acknowledgement required; HiPS ODbL-1.0 |
| DSS2 | STScI/NASA; POSS-II Caltech/Palomar, UK Schmidt AAO/ROE; HiPS by CDS | Plates © AURA, Caltech, AAO, UK PPARC; use with the STScI acknowledgement ([terms](http://archive.stsci.edu/dss/copyright.html)); HiPS ODbL-1.0 |
| SDO/AIA | Courtesy of NASA/SDO and the AIA, EVE, and HMI science teams | Not copyrighted; credit required ([rules](https://sdo.gsfc.nasa.gov/data/rules.php)) |
| SOHO/LASCO (Helioviewer) | SOHO/LASCO (ESA & NASA); rendered by Helioviewer.org | Free to use with credit |
| NOAA OVATION | NOAA Space Weather Prediction Center, OVATION aurora model | Public domain (U.S. Government work) |

DSS2 is the only source whose images remain under copyright (the plate owners listed above). Its
terms page asks for acknowledgement and does not state a non-commercial condition. It is the fallback
outside the Legacy Surveys / Pan-STARRS footprints and for wide fields. If the site ever becomes
commercial, confirm DSS terms with STScI or drop DSS2 from `context.PREFERENCE`.

## Tests

`uv run pytest`: 88 tests, no network. `tests/conftest.py` blocks `httpx`, and every answer is
replayed from `tests/fixtures/http/*.json` (recorded by the scripts above). They cover the 20 real
examples replayed end to end, contract shape, ID extraction, survey footprint choice, blank /
error / truncated image rejection on real bytes, SDO/Helioviewer/LASCO timing rules, region
wording, the NOAA 24-hour rule and hemispheres, thumbnails and their fallback, and the CLI (list
and wrapped input, existing images, `--no-check`).

# skyevents

What is happening in the sky right now, as one list of **Events**: supernovae and other
transients, new near-Earth objects and comets, solar flares, CMEs and geomagnetic storms,
fireballs, gamma-ray bursts, neutrinos and gravitational waves, each with a real distance or 3D
position where one exists. Python 3.12, `uv`. Free sources only, no logins, no API keys.

```sh
uv sync
uv run events-ingest --since 7d --out events.json   # also writes status.json next to it
uv run pytest                                       # offline, replays recorded real responses
uv run python scripts/record_fixtures.py            # re-record fixtures (network)
uv run python scripts/record_fixtures.py distances  # only the distance lookups, on top of live_week
```

```python
from skyevents import query
query({"categories": ["transients"], "min_confidence": 0.8, "limit": 20})            # reads events.json
query({"region": {"ra_deg": 83.6, "dec_deg": 22.0, "radius_deg": 5}}, events=my_events)
```

The Event shape is the SHARED EVENT CONTRACT ([models.py](src/skyevents/models.py)). This
package fills `images` only where a source already hands over picture URLs (Rubin cutouts);
PICTURES fills the rest.

## Sources

| Source (`Event.source`) | What | Service | Window | Live if newest event younger than |
|---|---|---|---|---|
| `rubin` | Rubin/LSST transients | Fink LSST `/api/v1/tags`, via `sources/skysources` | `[since, until]`; while paused, `latest_observed_window(n)` | 72 h (`stream_status()`) |
| `ztf` | ZTF transients, northern sky | [ALeRCE ZTF API](https://api.alerce.online/ztf/v1/docs) | last detection in window | 3 d |
| `tns` | classified supernovae, TDEs | [TNS](https://www.wis-tns.org) public search, CSV | first seen within 30 d | 3 d (any new report) |
| `mpc` | possible NEOs, possible comets | MPC [NEOCP](https://www.minorplanetcenter.net/iau/NEO/toconfirm_tabular.html) JSON, [PCCP](https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html) text | last sighting in window | 3 d |
| `jpl` | newly designated comets, interstellar objects | JPL [SBDB Query](https://ssd-api.jpl.nasa.gov/doc/sbdb_query.html) + [Horizons](https://ssd-api.jpl.nasa.gov/doc/horizons.html) | first observed within 60 d | 90 d |
| `cneos` | fireballs | [CNEOS fireball API](https://ssd-api.jpl.nasa.gov/doc/fireball.html) | in window | 60 d |
| `donki` | solar flares, CMEs, geomagnetic storms | [NASA DONKI](https://kauai.ccmc.gsfc.nasa.gov/DONKI/) | in window | 7 d |
| `gcn` | gamma-ray bursts, Einstein Probe X-ray transients | [GCN Circulars](https://gcn.nasa.gov/circulars) | in window | 3 d |
| `icecube` | high-energy neutrinos | [GCN Classic AMON table](https://gcn.gsfc.nasa.gov/amon_icecube_gold_bronze_events.html) | in window | 30 d |
| `gracedb` | gravitational waves | [GraceDB](https://gracedb.ligo.org) public API | in window | 14 d |

Why some windows differ from `--since`: a supernova's TNS classification arrives days to weeks
after its first detection, a comet found three weeks ago is still news, and while Rubin's stream
is paused its newest events are older than any short window. In every case `observed_at` stays
the real date, and `query(since=...)` filters on it.

### Choices worth knowing

- **Rubin**: `skysources.stream_status()` decides live/paused. While paused, the adapter queries
  `skysources.latest_observed_window(n)` for the same number of nights, so the feed shows
  Rubin's latest real events with their true dates. `status.json` says which window was used.
  Those events carry `raw.from_latest_observed_window = true`, so a UI can keep them out of a
  "recent" feed (`query(since=...)` already does, since it filters on `observed_at`) and offer
  "Rubin's latest nights" as a separate toggle.
  Types come from `skysources.alerts.fink_row_to_discovery` (the table in `sources/README.md`).
  `brightness_mag` is the brightness of the change (difference-image flux), and it is `null`
  when the object faded.
- **ZTF**: Fink's ZTF API did not answer within 60–75 s on 2026-09-25, so ZTF uses ALeRCE. It
  takes the light-curve classifier (supernova types, TDE, microlensing, and CV/Nova only when
  the object is new) plus the first-image classifier for objects first seen in the window.
- **TNS** needs no account for its public search. A free bot account would give exact
  classification dates through the TNS API, but this feed doesn't need it. The CSV has no
  report date, so `reported_at = observed_at`.
- **GCN**: Notices need a (free) Kafka login, so the adapter reads Circulars, which are
  public. Each burst's position is the smallest error circle among its first circular and up
  to 2 position circulars (Swift-XRT > Swift-BAT > Fermi GBM > EP > SVOM).
- **GraceDB**: confidence is p_astro = 1 − P(terrestrial) from the alert. Unmodelled burst
  alerts publish no classification; for those, confidence = 1 / (1 + false alarms per year)
  (one per year → 0.5, one per century → 0.99), or 0.5 with no FAR. The summary says which,
  and `raw.confidence_from` records it.
- **GraceDB**: the position is the most probable pixel of the sky map. `error_deg` is the
  radius of a circle with the 90% area; the true area is in `raw.area90_deg2`.
- **Geomagnetic storms** are global. Their Earth-frame point is the geomagnetic north pole
  (`raw.location_note`).
- When a source gives no report time (CNEOS, TNS, JPL, IceCube table),
  `reported_at = observed_at` and `raw.reported_at_known = false`.

### Confidence

| basis | meaning | used by |
|---|---|---|
| `official_report` | a human or official catalogue says so; confidence 1.0 (PCCP "possible comet": 0.5) | TNS, GCN, DONKI, CNEOS, JPL, MPC PCCP, Rubin rows with a TNS type |
| `catalogue_match` | the position matches a known object's catalogue type | Rubin rows typed from SIMBAD/VSX |
| `machine_guess` | a classifier's number, labelled "guess" in the summary | Rubin CATS, ALeRCE, MPC NEO score, IceCube signalness, GraceDB P(astro) |

Summaries never say "discovered", and every event links its source (`source_url`, plus every
merged member in `raw.sources`).

## De-duplication

Two events from different sources are the same object if:

1. **Name**: they share a name in `raw.names`, compared without case, spaces or the
   `SN`/`AT`/`TDE` prefix. Examples: TNS lists ZTF's id as the internal name; Rubin's TNS
   cross-match `AT 2026x` matches `tns:2026x`; `GRB 260920B` matches `EP260920b`.
2. **Position + time**, sky frame only, same category, compatible types (equal, or one
   `unknown`):
   - transients: separation ≤ max(2″, err₁ + err₂), observed within 60 days;
   - high energy: separation ≤ err₁ + err₂, observed within 1 hour.

Solar-system, Sun and Earth events join by name only. Matching is transitive.

The merged event keeps the best member's id, type, title and summary. "Best" means
`official_report` > `catalogue_match` > `machine_guess`, then source priority
(tns, gcn, gracedb, icecube, jpl, mpc, donki, cneos, rubin, ztf). It also takes:
- the tightest position;
- the earliest `reported_at`;
- the latest `observed_at`, with the earliest kept in `raw.first_observed_at`;
- all images;
- `raw.sources` with every member's link, and `raw.merged_ids`.

## Distances and 3D positions

After de-duplication every sky event gets a real distance where one exists, and every
Solar-System object a real 3D position. Both are optional fields of the sky `Location`, so
records without them stay valid:

```
distance:  {pc, pc_low, pc_high, redshift, basis: parallax|redshift|gw_estimate|catalogue|unknown}
ephemeris: {helio_xyz_au: [x, y, z], earth_distance_au, sun_distance_au, epoch}
```

Solar-System objects carry `ephemeris`; every other sky event carries `distance` (basis
`unknown`, all numbers null, when nothing measured it), and so does a Solar-System object whose
position could not be computed. Sun- and Earth-frame events get neither.
`raw.distance_from` says where each value came from (e.g. "GCN Circular 45740: ...").

| type | how | basis |
|---|---|---|
| comet, interstellar object (JPL) | [Horizons](https://ssd-api.jpl.nasa.gov/doc/horizons.html) vectors at `observed_at`: Sun-centred, ecliptic J2000, geometric | ephemeris |
| NEOCP / PCCP objects (MPC) | Horizons doesn't know temporary designations, so [JPL Scout](https://ssd-api.jpl.nasa.gov/doc/scout.html)'s 50 sampled orbits, each moved to `observed_at` with two-body Kepler motion; the median position, with the 16-84% Earth-distance spread in `raw.ephemeris_spread` | ephemeris |
| supernova, TDE, kilonova, AGN flare, `unknown` (position ≤ 2″) | the transient's own TNS redshift → `redshift`; else TNS host-galaxy redshift, else a SIMBAD galaxy/AGN/QSO with a redshift within 2″ → `catalogue` | redshift, catalogue |
| nova | as above (a nova in another galaxy), else Gaia as below | redshift, catalogue, parallax |
| variable star, stellar flare, microlensing | nearest Gaia DR3 source within 1.5″, distance = 1000 / parallax, only if parallax/error > 5; a weaker match is named in `raw.distance_note` | parallax |
| gamma-ray burst (and Einstein Probe transients) | the redshift a GCN Circular reports (spectroscopic first; from the subject's "z = …", else the body's "redshift (of) z = …") | redshift |
| gravitational wave | the GraceDB sky map's DISTMEAN ± DISTSTD → `pc`, `pc_low`, `pc_high` | gw_estimate |
| neutrino | nothing measures it | unknown |

- **Cosmology**: redshift → luminosity distance in astropy's `Planck18`, the same kind of
  distance a gravitational-wave sky map gives. Redshift distances carry no bounds.
- **Parallax**: bounds are 1000 / (parallax ± error). Gaia's small parallax zero-point is not
  corrected.
- **Earth**: `earth_distance_au` uses ERFA's Earth position (it agrees with Horizons to
  3·10⁻⁸ au); the Kepler step agrees with Horizons to 2·10⁻⁶ au after 30 days. Both are tested
  against recorded Horizons answers.
- **Why not ALeRCE host data**: ALeRCE's public ZTF API has no host-galaxy or redshift endpoint,
  so SIMBAD is the host catalogue.
- **Cost**: TNS objects with a redshift first seen from 90 days before the oldest candidate
  (500 per request, at most 6 requests, 5 s apart), SIMBAD and Gaia in batches of 50 cones per
  ADQL query, one Horizons or Scout request per Solar-System object, and only the redshift
  circulars of each burst. About a minute for a week. Ephemerides and TAP answers are cached
  (past epochs never change).

A failing lookup leaves its events at `unknown` and is named in `status.json` under
`distances.lookups`; it never stops the feed.

## query(filters)

`types`, `categories` (`transients`, `solar_system`, `sun_space_weather`, `earth_atmosphere`,
`high_energy`, plus `other` for `unknown`), `since` / `until` (on `observed_at`), `sources` (a
merged event matches any member), `frame` (`sky`/`sun`/`earth`), `region`
(`{ra_deg, dec_deg, radius_deg}`, sky events only), `min_confidence`, `offset` / `limit`
(default 100, max 1000). Results are sorted newest first. Bad filters raise `ValueError`.

## Output

- `events.json`: `{generated_at, since, until, count, events: [Event]}`.
- `status.json`: `{generated_at, window, events_before_dedup, events, events_in_window, sources: {name: {state:
  live|paused|unknown, live, last_event_at, events, events_fetched, error, live_within_hours,
  distance: {sky_events, with_distance, share}, ...}}, distances: {cosmology, lookups, by_type:
  {type: {events, with_distance, share, basis: {basis: count}}}}}`. `distance.share` is the share
  of a source's sky events (a merged event counts for every member) with a distance or an
  ephemeris; `null` for sources with no sky events. `events` counts only events observed inside the requested window. `events_fetched`
  also counts older ones: a paused source's latest nights, or TNS/JPL lookbacks. The top-level
  `events_in_window` does the same after de-duplication. Rubin adds
  `window`, `last_scheduled_visit_at` and a `note` while it is paused.

A failing source is reported in `status.json` and skipped; it never stops the feed.
[ci/ingest.yml](ci/ingest.yml) is an hourly GitHub Action; copy it to `.github/workflows/`.

## Rate limits and caching

Everything goes through `skysources`' HTTP client, which gives:
- an on-disk cache in `~/.cache/skysources` (`SKYSOURCES_CACHE` moves it, `SKYSOURCES_NO_CACHE=1`
  turns it off);
- retries on 429 and 5xx, honouring `Retry-After`;
- at most 1 request per second per host by default.

Per-host limits: TNS 1 request per 5 s, ALeRCE 2/s. Live feeds are cached for 15 min,
GCN circulars and GraceDB alert files for 30 days (they never change), and Horizons ephemerides
for a day. A full 7-day run makes about 70 requests, most of them GCN circulars that are cached afterwards.

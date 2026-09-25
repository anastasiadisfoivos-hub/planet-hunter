# Conventions

These conventions sit on top of [CONTRACT.md](CONTRACT.md) and never change it. The TRAPS session (api/) owns this file.

## Discovery IDs identify the object, not a single detection

| Case | ID | Notes |
|---|---|---|
| Rubin, non-solar-system | `rubin:obj:<diaObjectId>` | Never the alertId. One supernova produces many alerts but has one ID. |
| Rubin, solar system | `rubin:ss:<ssObjectId>` | |
| TESS transit signal | `tess:<tic>:sig:<n>` | `n` counts from 1 per star. See the matching rule below. |
| TESS flare | `tess:<tic>:flare:<peak BTJD rounded to 0.01>` | For example `tess:25155310:flare:2345.67` (always two decimals). |

### Matching TESS signals on a re-hunt
- A transit-signal Discovery carries its period in `raw.period_days` (a float, in days).
- On a re-hunt, the API compares each new signal with the star's existing `tess:<tic>:sig:*` Discoveries. They match if the periods agree within 1%, or if one period is a clean alias of the other: a ratio of 2, 3, 1/2 or 1/3, also within 1%.
- A match **updates** the existing record and keeps its ID. A signal with no match gets the next free `n`.
- pipeline/ may return any provisional `n`. The API assigns the final IDs, so pipeline/ doesn't need to know what has already been stored.

### Flares
- A flare Discovery carries `raw.peak_btjd` (a float). The API rebuilds the ID from it, so a flare seen again always gets the same ID.

## Updates, not duplicates
- When a Discovery with an existing ID arrives again with new data, the stored record is replaced by the newer one, except:
  - `detected_at` keeps the first detection time;
  - `raw.updated_at` (ISO-8601 UTC) is set to the time of the update.
- An update never creates a new catch. Each player catches a given Discovery at most once.

## Field formats
- `StarTarget.tic_id`: an integer. The API also accepts a string of digits and converts it.
- `origin`: an opaque string supplied by the source module. The API passes it through unchanged.
- `cutouts.before` / `now` / `difference`: a URL string, or `null`.
- `light_curve`: `{"time_btjd": [...], "flux": [...]}`, binned to at most 2000 points (pipeline/'s format), or `null`/absent.
- Timestamps are ISO-8601 UTC.

## API parameter: `/forecast?window=`
- A duration starting now: `<N>h` or `<N>d`, for example `12h` or `7d`. Allowed range: 1h to 30d.
- Or an ISO-8601 interval `start/end`, for example `2026-10-01T00:00:00Z/2026-10-03T00:00:00Z`, where end is after start and the span is at most 30 days.
- Default: `7d`.

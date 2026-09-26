# public/data/monitor: the monitor's mock data

Everything here is **real data**. Nothing is simulated. It stands in for the FINDER API routes (`/monitor/now`, `/monitor/log`,
`/monitor/coverage`, `/monitor/stats`, `/finder/candidates…`, `/finder/sensitivity`) until they are live, and the site shows it
as a **replay of the 26 Sep 2026 search**, never as live.

Built by `components/monitor/data/build_monitor_data.py`, run with the HUNT session's environment:

    cd ~/ph-hunt/hunt && uv run python ~/ph-monitorui/web/components/monitor/data/build_monitor_data.py

## Where each piece came from

| file | source |
| --- | --- |
| `stars/<tic>.json` (19 stars the monitor replays) | TESS light curves (SPOC and TESS-SPOC PDCSAP flux, from MAST), each **searched again with `hunt.analyse`** so every detection carries hunt's own reason. 5 are **hunt's recorded test fixtures** (`hunt/tests/data/*.npz`: TIC 415739607, 408512382, 175516858, 254113311, 76923707); 11 are stars from the **2026-09-26 sweep** (`hunt/out/sweep_final`), downloaded again from MAST; 3 are the stand-in TOIs below. |
| `log.json`, `coverage.json` | All 200 stars of the **2026-09-26 sweep** (position, sectors, every signal and the stage it failed at; `searched_at` is the time each star's result was written), plus the fixture and stand-in stars. Observation dates come from each star's downloaded light curve. |
| `stats.json` | Counted from `log.json`; `sweep_2026_09_26` is the sweep's own funnel (`hunt/results/sweep_2026-09-26_top200_summary.json`). |
| `candidates/*.json` | The sweep found **no new candidate**. These four are **stand-ins**: real TESS Objects of Interest (TOI-7303.01, TOI-4257.01, TOI-1027.01, TOI-1364.01) found again by `hunt.analyse` with the known-object lists switched off, so their checks, curves and scores are hunt's own. Each record says so in `stand_in`. The vetting block's Gaia values are live **Gaia DR3** queries (RUWE, neighbours within 42″, variability flag) and its variability match is **AAVSO VSX** (VizieR B/vsx). LEO and TRICERATOPS have not been run: `ran: false`. Votes start at zero. |
| `candidates/tic75208638-01.json` `pixels` | The real PIXELS-session run on TOI-4257, sector 62 (`components/finder/data/pixels-toi4257-s0062.json`). |
| `sensitivity.json` | hunt's injection-recovery run (`hunt/results/sensitivity.json`: 200 stars, 2000 injections), regridded to the FINDER shape. |

## What is reduced, and how

* Light curves are normalised per sector (divided by the sector median) and **binned to 10 minutes**. The shape is the star's; only
  the resolution is lower, to keep each file near 150 kB.
* For objects already known (masked before the search), the depth is measured in the data at the listed ephemeris, or at the one hunt
  re-located when the planet's transit times drift (TOI-1130). For TOI-1130 c the drift makes that measured depth an underestimate.
* Two of the TOIs tried (TOI-1001.01, TOI-1036.01) fail hunt's checks, so they are not used as stand-ins.

SHARED CONTRACT (identical in all five briefs. Do NOT change it. If you need a change, STOP and report.)
Layout: pipeline/ · sources/ · forecast/ · api/ · web/. Each Python folder: own pyproject, Python 3.12, uv.
Sphere = {ra_deg, dec_deg, radius_deg (0.05–10)}
StarTarget = {tic_id}
CatchType = asteroid | near_earth_object | trans_neptunian_object | comet | interstellar_object |
  supernova | active_galaxy | tidal_disruption_event | microlensing | kilonova | variable_star |
  flare | eclipsing_binary | planet_candidate | unknown
Discovery = {id, type, confidence 0–1, source "rubin"|"tess", origin, ra_deg, dec_deg, detected_at,
  name_if_known, known_status "known"|"not_on_lists"|"unchecked", cutouts {before, now, difference},
  light_curve (optional), explanation, links [{label, url}], raw}
Forecast = {sphere, window {start, end}, rubin_visit_probability, visits [{time, band}],
  expected [{type, mean_count}], known_solar_system_objects [{name, type, ra_deg, dec_deg}],
  generated_at, inputs_used [string]}
heatmap.json = {generated_at, grid "healpix nside=N", cells [{pix, counts {CatchType: n}}]}
Honesty rule: never "new planet" or "discovered". Types are best guesses with a confidence.

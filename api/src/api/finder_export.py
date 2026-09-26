"""Candidates as an ExoFOP-TESS "Bulk Parameter Upload" file that creates Community TOIs (CTOIs).

Format: ExoFOP's documented planet-parameter template,
  https://exofop.ipac.caltech.edu/tess/templates/params_planet_YYYYMMDD_001.txt
linked from https://exofop.ipac.caltech.edu/tess/help.php ("Bulk Parameter Upload") and
https://exofop.ipac.caltech.edu/tess/planet_parameters_help.php. It is pipe-delimited ("|"), one
header row with the columns below in this order; lines starting with "\\" are explanations that
ExoFOP ignores. File name: params_planet_YYYYMMDD_nnn.txt.

Per row (flag = newctoi): target TIC<tic>.<nn>, disposition PC, discovery blank (= TESS),
period (days), epoch (BJD = BTJD + 2457000, must be > 2000000), depth (ppm), duration (hours),
radius (Earth radii), tag, prop_period 0 (required for new CTOIs), paper URL, notes (<= 120
characters, required for a new CTOI).

The owner submits the file to ExoFOP by hand. ExoFOP's candidate guidelines
(https://exofop.ipac.caltech.edu/tess/candidate_help.php) require a published paper's URL for a
new CTOI, and ask that the TIC's next free .nn be used: both are the owner's to check.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api import honesty

# Verbatim from ExoFOP's template, including its mixed *_unc / *_err spellings.
COLUMNS = (
    "target", "flag", "disp", "discovery", "candname", "period", "period_unc", "epoch",
    "epoch_unc", "depth", "depth_unc", "duration", "duration_unc", "inc", "inc_unc", "imp",
    "imp_unc", "r_planet", "r_planet_err", "ar_star", "ar_star_err", "radius", "radius_unc",
    "mass", "mass_unc", "temp", "temp_unc", "insol", "insol_unc", "dens", "dens_unc", "sma",
    "sma_unc", "ecc", "ecc_unc", "arg_peri", "arg_peri_err", "time_peri", "time_peri_unc", "vsa",
    "vsa_unc", "tag", "group", "prop_period", "paper", "notes",
)  # fmt: skip
TEMPLATE_URL = "https://exofop.ipac.caltech.edu/tess/templates/params_planet_YYYYMMDD_001.txt"
BTJD_OFFSET = 2457000.0
RJUP_IN_REARTH = 71492.0 / 6378.1  # IAU nominal equatorial radii
MAX_NOTES = 120


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("|", "/").split())


def _num(value: Any, fmt: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return ""
    return format(value, fmt)


def target_name(candidate_id: str) -> str:
    tic, n = candidate_id.split("_")
    return f"TIC{int(tic)}.{int(n):02d}"


def default_tag(today: datetime) -> str:
    return f"{today:%Y%m%d}_planethunter_ctoi"


def file_name(today: datetime) -> str:
    return f"params_planet_{today:%Y%m%d}_001.txt"


def pixel_note(verdict: str | None) -> str:
    """What the pixel check said, always stated: "inconclusive" and "not run" included."""
    if verdict is None:
        return "no pixel check yet"
    if verdict == "inconclusive":
        return "pixel check inconclusive"
    return f"pixel check: {verdict}"


def notes_for(candidate_id: str, rec: dict[str, Any], verdict: str | None) -> str:
    # The pixel note comes second so the 120-character cut never drops it.
    parts = [f"planet-hunter candidate {candidate_id}", pixel_note(verdict)]
    if isinstance(rec.get("n_transits"), int):
        parts.append(f"{rec['n_transits']} TESS transits")
    if isinstance(rec.get("snr"), int | float):
        parts.append(f"SNR {rec['snr']:.1f}")
    text = honesty.soften(_clean("; ".join(parts)))
    return text[:MAX_NOTES]


def row_for(candidate: dict[str, Any], tag: str, paper_url: str | None) -> dict[str, str]:
    rec = candidate["record"]
    radius = rec.get("radius_rjup")
    radius_unc = None
    if isinstance(radius, int | float):
        spreads = [
            abs(v - radius)
            for v in (rec.get("radius_low"), rec.get("radius_high"))
            if isinstance(v, int | float) and not isinstance(v, bool)
        ]
        radius_unc = max(spreads) * RJUP_IN_REARTH if spreads else None
        radius = radius * RJUP_IN_REARTH
    row = dict.fromkeys(COLUMNS, "")
    row.update(
        target=target_name(candidate["id"]),
        flag="newctoi",
        disp="PC",
        period=_num(rec.get("period_d"), ".6f"),
        epoch=_num(rec["t0_btjd"] + BTJD_OFFSET, ".6f"),
        depth=_num(rec.get("depth_ppm"), ".1f"),
        duration=_num(rec.get("duration_h"), ".4f"),
        radius=_num(radius, ".3f"),
        radius_unc=_num(radius_unc, ".3f") if radius_unc is not None else "",
        tag=_clean(tag),
        prop_period="0",
        paper=_clean(paper_url),
        notes=notes_for(candidate["id"], rec, candidate.get("pixel_verdict")),
    )
    return row


def build_file(
    candidates: list[dict[str, Any]], today: datetime, tag: str | None, paper_url: str | None
) -> str:
    tag = tag or default_tag(today)
    lines = [
        f"\\ ExoFOP-TESS bulk parameter upload (flag newctoi), format of {TEMPLATE_URL}",
        f"\\ {len(candidates)} planet-hunter candidate(s), exported {today:%Y-%m-%d}."
        " Submit by hand at https://exofop.ipac.caltech.edu/tess/ (Bulk Parameter Upload).",
        "\\ Before uploading: check each TIC's next free .nn on ExoFOP and edit `target`.",
    ]
    if not paper_url:
        lines.append(
            "\\ WARNING: `paper` is empty. ExoFOP requires a published paper URL for newctoi"
            " (https://exofop.ipac.caltech.edu/tess/candidate_help.php)."
        )
    lines.append("|".join(COLUMNS))
    for c in candidates:
        row = row_for(c, tag, paper_url)
        lines.append("|".join(row[col] for col in COLUMNS))
    return "\n".join(lines) + "\n"

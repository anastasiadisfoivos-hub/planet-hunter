"""Turn a signal plus its vetting results into a best-guess type, a confidence and a plain-English story.

Wording rule: never "new planet" or "discovered". Types are best guesses with a confidence.
"""

from __future__ import annotations

import math

from .models import CatchType
from .search import Signal
from .vet import VetResult

TOO_LARGE_TEXT = "too large to be a planet; could be a small star or a blended signal"


def _saturating(x: float, scale: float) -> float:
    return 1 - math.exp(-max(x, 0.0) / scale)


def classify(sig: Signal, vets: dict[str, VetResult]) -> tuple[CatchType | None, float, str]:
    """Returns (type or None if no convincing signal, confidence 0-1, explanation)."""
    if vets["snr"].passed is False:
        return None, 0.0, vets["snr"].reason

    summary = (f"A dip of {sig.depth * 100:.3f}% repeats every {sig.period:.4f} days and lasts about "
               f"{sig.duration * 24:.1f} hours.")
    eb_tests = [v for v in (vets["odd_even"], vets["secondary_eclipse"]) if v.passed is False]
    strength = _saturating(sig.snr - 7, 30)

    if eb_tests:
        conf = min(0.95, 0.6 + 0.1 * (len(eb_tests) - 1) + 0.2 * strength)
        why = " ".join(v.reason for v in eb_tests)
        return (CatchType.eclipsing_binary, round(conf, 2),
                f"Best guess: two stars eclipsing each other (an eclipsing binary). {summary} {why}")

    if vets["size"].passed is False:
        conf = 0.3
        return (CatchType.eclipsing_binary, conf,
                f"Best guess, with low confidence: an eclipsing binary. {summary} The object is {TOO_LARGE_TEXT}. "
                f"{vets['size'].reason} Alternate dips match and there is no strong second dip, so this is "
                f"not a sure binary either.")

    conf = 0.5 + 0.4 * strength
    caveat = ""
    if vets["size"].passed is None:
        conf -= 0.15
        caveat = " We could not check its size, so this guess is weaker."
    return (CatchType.planet_candidate, round(conf, 2),
            f"Best guess: a planet candidate. {summary} The dips are regular, alternate dips match and there is "
            f"no strong second dip halfway round the orbit, which is what an object passing in front of the star "
            f"would look like. {vets['size'].reason} A candidate is not a confirmed planet: other things, such as "
            f"a faint background binary, can look the same.{caveat}")

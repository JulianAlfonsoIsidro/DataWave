"""Which fields a user must fill in before a job can run (pure, no Streamlit).

The pages mark these with an asterisk and stop the run with one plain message
naming what is missing, before any loader or computation starts.

* New Promo: Eligible Segments and Channels are required. With no segment the
  audience is empty; with no channel every lead has "no reachable channel" and
  expected joiners silently drop to 0. Reward is only recommended: it is
  descriptive and changes no number.
* Personas: when "Split into groups first" is ticked, at least one "Split by"
  attribute is required, otherwise the run quietly builds without a split.
  (At least one attribute is already checked by ``persona_page.validation_error``.)
"""

from __future__ import annotations

from typing import Iterable, Sized

PROMO_REQUIRED = ("Eligible Segments", "Channels")
REQUIRED_MARK = " *"
RECOMMENDED_NOTE = "Recommended"


def missing_promo_fields(eligible_segments: Sized | None, channels: Sized | None) -> list[str]:
    """Names of the required New Promo fields that are empty, in form order."""
    missing: list[str] = []
    if not eligible_segments:
        missing.append("Eligible Segments")
    if not channels:
        missing.append("Channels")
    return missing


def missing_persona_split(split_ticked: bool, grouping_attributes: Iterable[str] | None) -> bool:
    """True when the split box is ticked but no "Split by" attribute is chosen."""
    return bool(split_ticked) and not list(grouping_attributes or [])


def required_message(missing: Iterable[str]) -> str:
    """One plain sentence naming the empty required fields."""
    names = list(missing)
    if not names:
        return ""
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"Fill in {joined} before running. Fields marked * are required."

"""Sign-off reset for the Download Leads review card (audit item 1.1).

Pure logic, no Streamlit. A tick on "I Checked These Figures" belongs to the
figures it was made for. When the promo id, threshold type, threshold value or
run changes, every tick is cleared (Requirements 1.1, 2.1, 3.1, 3.2).
"""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

REVIEW_KEY_PREFIX = "review_ok_"
SIGNATURE_STATE_KEY = "review_figures_signature"


def figures_signature(
    promo_id: Any, threshold_type: Any, threshold_value: float, run_seq: int
) -> tuple[str, str, float, int]:
    """A hashable fingerprint of the figures the review card describes."""
    return (
        str(promo_id),
        str(threshold_type),
        round(float(threshold_value), 6),
        int(run_seq),
    )


def clear_stale_signoffs(state: MutableMapping, signature: tuple) -> bool:
    """Untick every sign-off when ``signature`` differs from the stored one.

    The first call only stores the signature. Returns True when ticks were
    cleared. Only keys starting with ``REVIEW_KEY_PREFIX`` are touched, and
    none is ever set to True.
    """
    previous = state.get(SIGNATURE_STATE_KEY)
    if previous is None:
        state[SIGNATURE_STATE_KEY] = signature
        return False
    if previous == signature:
        return False
    for key in list(state.keys()):
        if isinstance(key, str) and key.startswith(REVIEW_KEY_PREFIX):
            state[key] = False
    state[SIGNATURE_STATE_KEY] = signature
    return True


def persona_signature(persona_result: Any) -> tuple[str, int, str]:
    """(promo id or "", number of personas, narration source) of a persona run."""
    if persona_result is None:
        return ("", 0, "")
    promo = ""
    labels = getattr(persona_result, "labels", None)
    try:
        if labels is not None and "promo_id" in labels.columns and len(labels):
            first = labels["promo_id"].dropna()
            promo = str(first.iloc[0]) if len(first) else ""
    except Exception:  # signature must never break a render
        promo = ""
    count = 0
    for pset in getattr(persona_result, "persona_sets", None) or []:
        personas = getattr(pset, "personas", None)
        count += len(personas) if personas is not None else 1
    return (promo, count, str(getattr(persona_result, "narration_source", "")))

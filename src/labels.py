"""Label_Map: one plain-language label source for the whole UI.

Maps raw driver, feature, and exclusion codes to Title Case phrases so no raw
code (and no underscore) reaches the screen. Persona attribute wording is not
duplicated: unknown codes are delegated to
``part5_personas.labels.attribute_label`` and finally to a Title Case fallback.

Governing spec: Part 7 Requirements 4.1, 4.2, 4.3, 4.5.
"""

from __future__ import annotations

import re

from part5_personas.labels import attribute_label

# Driver/feature codes to plain phrases (Requirement 4.1).
FEATURE_LABELS: dict[str, str] = {
    "out_other_bank": "Money Sent To Other Banks",
    "ext_outflow_ratio": "Share Of Spending Leaving The Bank",
    "spend_share_retail": "Retail Spending",
    "latest_adb": "Current Average Balance",
    "avg_contacts_per_month": "Recent Contact Frequency",
    "digital_app_user": "Uses The Mobile App",
    "ndb_flag": "On The Do Not Bother List",
    "investment_propensity_decile": "Investment Interest",
    "mechanic": "Promo Mechanic",
    "threshold_php": "Promo Threshold",
}

# Exclusion codes to plain phrases (Requirement 4.1).
EXCLUSION_LABELS: dict[str, str] = {
    "ndb": "On The Do Not Bother List",
    "over_contacted": "Contacted Too Often",
    "no reachable channel": "No Reachable Channel",
}

# Driver codes that never appear on a decision card (Requirement 4.4).
HIDDEN_DRIVER_CODES = frozenset({"mechanic", "threshold_php"})

_ELLIPSIS = "..."


def _fallback(code: str) -> str:
    """Underscores to single spaces, collapse whitespace, Title Case (4.3)."""
    text = re.sub(r"[_\s]+", " ", str(code)).strip()
    return text.title()


def _persona_known(code: str) -> bool:
    """True when the persona label path has a real entry for ``code``."""
    if code.startswith("owns_") and len(code) > len("owns_"):
        return True
    from part5_personas.labels import _ATTRIBUTE_LABELS

    return code in _ATTRIBUTE_LABELS


def is_known(code: str) -> bool:
    """True when ``code`` resolves without using the Title Case fallback."""
    return code in EXCLUSION_LABELS or code in FEATURE_LABELS or _persona_known(code)


def plain_label(code: str) -> str:
    """Return the plain Title Case label for ``code``; never contains ``_``.

    Order: exclusions, features, persona attribute labels, Title Case fallback
    (Requirements 4.1, 4.3).
    """
    if code in EXCLUSION_LABELS:
        return EXCLUSION_LABELS[code]
    if code in FEATURE_LABELS:
        return FEATURE_LABELS[code]
    if _persona_known(code):
        label = attribute_label(code).replace("_", " ").title()
        return re.sub(r"\s+", " ", label).strip()
    return _fallback(code)


def plain_driver_phrase(code: str, max_chars: int = 60) -> str:
    """Return :func:`plain_label` limited to ``max_chars`` characters (4.5)."""
    phrase = plain_label(code)
    if max_chars <= 0:
        return ""
    if len(phrase) <= max_chars:
        return phrase
    if max_chars <= len(_ELLIPSIS):
        return phrase[:max_chars]
    return phrase[: max_chars - len(_ELLIPSIS)].rstrip() + _ELLIPSIS

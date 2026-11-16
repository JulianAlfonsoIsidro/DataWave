"""Pure helpers for the Part 8 group picker (F7, F6, F9; Requirements 12-18, 22).

No Streamlit import. Decides which Group_Visual fits a persona run (map,
3D ring, Toggle_Card or none), builds its items, and holds the small rules the
iframe mirrors (glass level, shortest ring step) plus the component-value sync
rule and the group-change check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Mapping, Sequence

from webapp_core.region_map import MAP_AREAS, build_region_map

PickerKind = Literal["none", "map", "carousel", "toggle"]
MAX_COMBINED_GROUPS = 12
MULTI_SEP = " | "  # existing group-key separator for multi-column splits
LABEL_SEP = " · "  # how a combined group is shown
REGION_COLUMN = "region"

_YES_NO_KEYS = ({"0", "1"}, {"0.0", "1.0"})

# Sprite ids in app/static/group_picker/illustrations.svg (Category list).
VALUE_ART: dict[str, dict[str, str]] = {
    "segment": {
        "Mass": "segment-mass", "Mid-Market": "segment-mid",
        "Affluent-Preferred": "segment-pref", "Affluent-Gold": "segment-gold",
    },
    "age_band": {
        "18-24": "age-18-24", "25-34": "age-25-34", "35-44": "age-35-44",
        "45-54": "age-45-54", "55+": "age-55-plus",
    },
    "sec_class": {
        "A": "sec-a", "B1": "sec-b1", "B2": "sec-b2", "C1": "sec-c1", "C2": "sec-c2", "D": "sec-d",
    },
    "inflow_type": {
        "Business": "inflow-business", "Mixed": "inflow-mixed",
        "Remittance": "inflow-remittance", "Salary": "inflow-salary",
    },
    "online_shopper": {
        "Low": "shop-1", "Medium": "shop-2", "High": "shop-3",
        "Very High": "shop-4", "Ultra High": "shop-5",
    },
}
# One distinct icon per yes/no column (Requirement 16.12).
YES_NO_ART: dict[str, str] = {
    "digital_app_user": "yn-app",
    "frugal_flag": "yn-frugal",
    "email_valid": "yn-email",
    "mobile_valid": "yn-mobile",
    "owns_Credit Card": "yn-card",
    "owns_Insurance": "yn-insurance",
    "owns_Investment": "yn-investment",
    "owns_Loan": "yn-loan",
}
UNKNOWN_ART = "unknown"

# Ring order for ordinal columns (the dropdown keeps the run order).
VALUE_ORDER: dict[str, tuple[str, ...]] = {
    "segment": ("Mass", "Mid-Market", "Affluent-Preferred", "Affluent-Gold"),
    "age_band": ("18-24", "25-34", "35-44", "45-54", "55+"),
    "sec_class": ("A", "B1", "B2", "C1", "C2", "D"),
    "online_shopper": ("Low", "Medium", "High", "Very High", "Ultra High"),
}


@dataclass(frozen=True)
class PickerItem:
    """One selectable group. ``value`` is the group key (a dropdown option)."""

    value: str
    label: str
    lead_count: int | None
    selectable: bool
    art: str
    # Picture id in app/static/group_picker/img/ (cut from the supplied
    # category sheets); "" falls back to the ``art`` sprite.
    image: str = ""


@dataclass(frozen=True)
class PickerPlan:
    """Which visual to draw and its items."""

    kind: PickerKind
    column: str | None
    items: tuple[PickerItem, ...]
    yes_no: bool = False  # Toggle_Card layout: column icon + check / cross
    unmatched: tuple[str, ...] = ()
    column_art: str = UNKNOWN_ART  # the yes/no column's own icon


NONE_PLAN = PickerPlan("none", None, ())


def art_for(column: str, value: str) -> str:
    """Sprite id for one value, or the neutral placeholder (Requirement 16.4)."""
    return VALUE_ART.get(column, {}).get(str(value), UNKNOWN_ART)


def image_for(column: str, value: str, *, yes_no: bool = False) -> str:
    """Picture id for one value ("" when the column has no picture).

    Category values reuse their sprite id (``segment-mass``); a yes/no value
    is the column icon plus ``-yes`` / ``-no`` (``yn-card-yes``).
    """
    if yes_no:
        base = YES_NO_ART.get(column)
        if base is None:
            return ""
        return f"{base}-yes" if str(value) in ("1", "1.0") else f"{base}-no"
    return VALUE_ART.get(column, {}).get(str(value), "")


def is_yes_no_value(value: str) -> bool:
    """True for a single 0/1 group value (also 0.0/1.0)."""
    return str(value) in ("0", "1", "0.0", "1.0")


def is_yes_no(keys: Sequence[str]) -> bool:
    """True when the two group keys are 0 and 1 (also 0.0 and 1.0)."""
    return set(map(str, keys)) in _YES_NO_KEYS


def _value_label(column: str, value: str, column_label: Callable[[str], str]) -> str:
    if str(value) in ("1", "1.0"):
        return f"{column_label(column)}: Yes"
    if str(value) in ("0", "0.0"):
        return f"{column_label(column)}: No"
    return str(value)


def _ring_order(column: str, keys: list[str]) -> list[str]:
    order = VALUE_ORDER.get(column)
    if not order:
        return keys
    rank = {v: i for i, v in enumerate(order)}
    return sorted(keys, key=lambda k: (rank.get(k, len(order)), keys.index(k)))


def plan_picker(
    split_columns: Sequence[str],
    group_keys: Sequence[str],
    lead_counts: Mapping[str, int],
    column_label: Callable[[str], str] = str,
) -> PickerPlan:
    """Decide the Group_Visual for a persona run (Property 8, Requirements 12.8,
    13.1, 15.1, 15.11, 15.12, 18.4, 18.5).

    ``group_keys`` are the run's group keys in run order (the dropdown order,
    without "All groups"); a multi-column key joins values with ``" | "``.
    ``lead_counts`` maps group key to leads; an empty mapping means counts are
    unknown, and every item stays selectable.
    """
    cols = [str(c) for c in split_columns]
    keys = [str(k) for k in group_keys]
    if not cols or len(keys) <= 1:
        return NONE_PLAN
    known = bool(lead_counts)

    def count(key: str) -> int | None:
        return int(lead_counts[key]) if key in lead_counts else (0 if known else None)

    def selectable(key: str) -> bool:
        c = count(key)
        return c is None or c > 0

    if len(cols) == 1:
        column = cols[0]
        if column == REGION_COLUMN:
            pairs = [(k, count(k) or 0) for k in keys]
            result = build_region_map(pairs)
            present = set(keys)
            items = tuple(
                PickerItem(e.region, e.region, count(e.region) if e.region in present else 0,
                           e.region in present and selectable(e.region), "region")
                for e in result.entries
            )
            return PickerPlan("map", column, items, unmatched=result.unmatched)
        if len(keys) == 2:
            yes_no = is_yes_no(keys)
            ordered = sorted(keys, key=lambda k: k not in ("1", "1.0")) if yes_no else keys
            col_art = YES_NO_ART.get(column, UNKNOWN_ART)
            items = tuple(
                PickerItem(k, _value_label(column, k, column_label), count(k), selectable(k),
                           "yn-check" if yes_no and k in ("1", "1.0")
                           else "yn-cross" if yes_no else art_for(column, k),
                           image_for(column, k, yes_no=yes_no))
                for k in ordered
            )
            return PickerPlan("toggle", column, items, yes_no=yes_no, column_art=col_art)
        items = tuple(
            PickerItem(k, _value_label(column, k, column_label), count(k), selectable(k),
                       art_for(column, k), image_for(column, k))
            for k in _ring_order(column, keys)
        )
        return PickerPlan("carousel", column, items)

    # Multi_Split, option A: one ring of combined groups (Requirement 18.4).
    if len(keys) > MAX_COMBINED_GROUPS:
        return NONE_PLAN

    def combined(key: str) -> PickerItem:
        parts = key.split(MULTI_SEP)
        label = LABEL_SEP.join(
            _value_label(c, v, column_label) for c, v in zip(cols, parts)
        ) if len(parts) == len(cols) else key
        art = art_for(cols[0], parts[0]) if parts else UNKNOWN_ART
        image = image_for(cols[0], parts[0], yes_no=is_yes_no_value(parts[0])) if parts else ""
        return PickerItem(key, label, count(key), selectable(key), art, image)

    items = tuple(combined(k) for k in keys)
    kind: PickerKind = "toggle" if len(keys) == 2 else "carousel"
    return PickerPlan(kind, None, items)


def group_changed(prev: str | None, current: str | None, *, reveal: bool) -> bool:
    """True iff both are not None, they differ, and this is not the reveal render
    (Property 12, Requirements 22.13, 22.14)."""
    return prev is not None and current is not None and prev != current and not reveal


def shortest_step(front: int, target: int, n: int) -> int:
    """Signed ring steps from ``front`` to ``target`` with minimal magnitude.

    In ``[-(n // 2), n // 2]``; a tie (even ``n``, opposite item) rotates left
    (``-(n // 2)``). Mirrored in ``picker.js`` (Property 13).
    """
    if n <= 1:
        return 0
    return ((target - front + n + n // 2) % n) - n // 2


def glass_level(index: int, front: int, n: int) -> int:
    """0 for the front item, 1 for ring distance 1, 2 for distance >= 2.

    Symmetric and wrap-aware; for ``n <= 4`` levels are capped at 1
    (Property 11).
    """
    if n <= 0:
        return 0
    d = min((index - front) % n, (front - index) % n)
    if d == 0:
        return 0
    if d == 1 or n <= 4:
        return 1
    return 2


@dataclass(frozen=True)
class SyncDecision:
    """``apply``: the option to select now (or None); ``last``: the event to remember."""

    apply: str | None
    last: object


def resolve_component_value(last: object, new: object, options: Sequence[str]) -> SyncDecision:
    """Apply a component event once, never reverting a dropdown change (Property 9).

    ``new`` is ``{"value": <group key>, "nonce": <int>}`` or None. It is applied
    only when it is not None, differs from the last handled event, and its value
    is one of the dropdown options. ``last`` always becomes ``new`` when ``new``
    is not None, so a bad or repeated event is never retried.
    """
    if new is None:
        return SyncDecision(None, last)
    if new == last:
        return SyncDecision(None, last)
    value = new.get("value") if isinstance(new, Mapping) else None
    apply = value if isinstance(value, str) and value in options else None
    return SyncDecision(apply, new)


__all__ = [
    "MAP_AREAS", "MAX_COMBINED_GROUPS", "MULTI_SEP", "LABEL_SEP", "PickerItem", "PickerPlan",
    "plan_picker", "image_for", "group_changed", "shortest_step", "glass_level", "SyncDecision",
    "resolve_component_value", "art_for", "is_yes_no", "VALUE_ART", "YES_NO_ART", "UNKNOWN_ART",
]

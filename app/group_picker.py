"""Streamlit wrapper for the Part 8 Group_Component (F6, F7, F9; Requirement 12).

One bidirectional component (``components.declare_component(path=...)``)
serves the region map, the 3D ring and the Toggle_Card from
``app/static/group_picker/`` with no build step. Which visual to draw is
decided by ``webapp_core.group_picker_items.plan_picker``; this module only
passes the plan, the palette (light and dark values read from the design
tokens) and the selected group, and reads the component's value back before
the "Show group" dropdown is created (Requirement 12.14), with no extra rerun.

If the static files are missing, a token cannot be read, or the component
fails in the browser, nothing is shown and the dropdown keeps working
(Requirement 12.10).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, MutableMapping, Sequence

from webapp_core.group_picker_items import PickerPlan, resolve_component_value

STATIC_DIR = Path(__file__).resolve().parent / "static" / "group_picker"
COMPONENT_KEY = "p8_group_picker"
LAST_KEY = "p8_group_last"
CREDIT = "NAMRIA, PSA via OCHA"

# Non-colour tokens the iframe needs on top of theme.PICKER_TOKENS.
_EXTRA_TOKENS = (
    "--pan-dur-fast", "--pan-dur", "--pan-dur-slow", "--pan-dur-xfade", "--pan-ease",
    "--pan-dur-carousel", "--pan-ease-carousel",   # Part 9: 3D carousel turn
    "--pan-radius-md", "--pan-radius-lg", "--pan-radius-pill",
    "--pan-space-1", "--pan-space-2", "--pan-space-3", "--pan-space-4",
    "--pan-shadow", "--pan-glass-blur-1", "--pan-glass-blur-2",
    "--pan-glass-sat-1", "--pan-glass-sat-2", "--pan-glass-shadow",
    "--pan-glass-scale-1", "--pan-glass-scale-2",
    # reveal, count-up and map camera (Part 8 polish)
    "--pan-dur-reveal", "--pan-dur-roll", "--pan-dur-xfade-short", "--pan-dur-finish", "--pan-dur-spark", "--pan-dur-hold", "--pan-dur-finish-linger",
    "--pan-reveal-ring-step", "--pan-reveal-toggle-lag", "--pan-count-step",
    "--pan-map-pitch", "--pan-map-bearing", "--pan-dur-fly", "--pan-ease-fly", "--pan-dur-fill", "--pan-ease-fill", "--pan-glass-dim-1", "--pan-glass-dim-2",
)
IMG_DIR = STATIC_DIR / "img"

_component: Any = None


def _get_component() -> Any:
    global _component
    if _component is None:
        import streamlit.components.v1 as components

        _component = components.declare_component(COMPONENT_KEY, path=str(STATIC_DIR))
    return _component


def files_ready(plan: PickerPlan) -> bool:
    """True when the static files this plan needs exist (Requirement 19.8)."""
    needed = ["index.html", "picker.js", "picker.css", "illustrations.svg"]
    if plan.kind == "map":
        needed.append("ph_regions.svg")
    return all((STATIC_DIR / name).is_file() for name in needed)


def _height_px() -> int:
    import theme

    try:
        value = theme.token_pair("--pan-group-visual-h")[0]
        return int(float(value.replace("px", "").strip()))
    except Exception:  # noqa: BLE001 - presentation fallback only
        return 360


def render_group_picker(
    plan: PickerPlan,
    selected: str | None,
    *,
    column_label: str = "",
    front_value: str | None = None,
    reveal_gen: str | None = None,
    key: str = COMPONENT_KEY,
) -> bool:
    """Draw the Group_Visual for ``plan``; returns True when it was drawn.

    ``selected`` is the current dropdown value (None or "All groups" means
    nothing is selected). ``reveal_gen`` is the persona generation id while
    its reveal may still play; the iframe plays the reveal once per id.
    Skips silently for kind ``none``, missing files or
    an unreadable token, so the dropdown alone remains (Requirement 12.10).
    """
    import theme

    if plan.kind == "none" or not files_ready(plan):
        return False
    try:
        palette = theme.iframe_palette(tuple(theme.PICKER_TOKENS) + _EXTRA_TOKENS)
    except theme.TokenError:
        return False
    values = {i.value for i in plan.items}
    items = [
        {"value": i.value, "label": i.label, "count": i.lead_count,
         "selectable": i.selectable, "art": i.art,
         "image": f"img/{i.image}.png" if i.image and (IMG_DIR / f"{i.image}.png").is_file() else None}
        for i in plan.items
    ]
    _get_component()(
        kind=plan.kind,
        items=items,
        selected=selected if selected in values else None,
        front_value=front_value,
        yes_no=plan.yes_no,
        column_art=plan.column_art,
        column_label=column_label,
        palette=palette,
        height=_height_px(),
        credit=CREDIT,
        reveal_gen=reveal_gen,
        key=key,
        default=None,
    )
    return True


def pending_selection(state: MutableMapping[str, Any], options: Sequence[str]) -> str | None:
    """The dropdown option chosen in the Group_Visual since the last render.

    Applies ``resolve_component_value`` against the last handled event, so an
    event is applied once and a later dropdown change is never reverted
    (Requirements 12.4, 12.12, 12.13). Call before the dropdown is created.
    """
    decision = resolve_component_value(state.get(LAST_KEY), state.get(COMPONENT_KEY), options)
    state[LAST_KEY] = decision.last
    return decision.apply


__all__ = ["render_group_picker", "pending_selection", "files_ready"]

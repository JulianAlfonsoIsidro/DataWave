"""Theme for the Promo Audience Navigator webapp.

The visual identity matches the BPI website reference: a white page with
generous whitespace, a centered ~1200px column, the Poppins font, dark charcoal
text, and a deep-red primary with a red gradient for buttons and hero panels.
Gold is available only as a small accent. All titles, tabs, buttons and labels
are Title Case.

Colors were sampled from the website reference screenshot and recorded in two
places that stay in sync: the ``[theme]`` block of ``.streamlit/config.toml``
and the ``PALETTE`` dict below. The full stylesheet is a single file,
``app/styles.css``, loaded once by :func:`inject_css` -- the palette hexes also
appear there as CSS variables.

Render helpers compose the page chrome: :func:`utility_bar`, :func:`nav_bar`,
:func:`breadcrumb`, :func:`hero`, plus the reusable :func:`card`, :func:`tile`,
and :func:`chip`. ``streamlit`` is imported lazily inside each helper so
importing ``app.theme`` never requires a running Streamlit server.
"""

from __future__ import annotations

import html
from pathlib import Path

# --- palette sampled from the BPI website reference screenshot ---

PALETTE = {
    "PRIMARY_RED": "#AE1319",   # deep primary red (BPI wordmark / LOGIN button)
    "RED_BRIGHT": "#D8232A",    # lighter red (gradient end)
    "ACCENT_GOLD": "#C9A227",   # small gold accent (used sparingly, if at all)
    "PANEL_WHITE": "#FFFFFF",   # white page / cards
    "TEXT_DARK": "#2B2B2B",     # dark charcoal body text
}

# Convenience module-level aliases.
PRIMARY_RED = PALETTE["PRIMARY_RED"]
RED_BRIGHT = PALETTE["RED_BRIGHT"]
ACCENT_GOLD = PALETTE["ACCENT_GOLD"]
PANEL_WHITE = PALETTE["PANEL_WHITE"]
TEXT_DARK = PALETTE["TEXT_DARK"]

# The app title is text only -- no logo image.
APP_TITLE = "Promo Audience Navigator"

# The main nav items, in Title Case, matching the tab order in main.py.
NAV_ITEMS = ["New Promo", "Results", "Past Promos"]

# The single stylesheet, resolved relative to this file so it loads from any cwd.
_STYLES_PATH = Path(__file__).resolve().parent / "styles.css"


def build_css() -> str:
    """Return the single CSS block injected once into the page.

    Reads ``app/styles.css`` verbatim and wraps it in a ``<style>`` tag. The
    stylesheet carries the full BPI-website visual system (white page, Poppins,
    red gradient buttons and hero, cards, tiles, chips, hidden Streamlit chrome)
    and defines the palette hexes as CSS variables, so the sampled colors appear
    in the returned string.
    """
    # "utf-8-sig" drops a leading byte-order mark (BOM) if an editor on Windows
    # adds one. A BOM in front of the stylesheet makes the browser discard the
    # first rule block (the :root color variables), which leaves every red
    # gradient panel and button blank white. The lstrip is a second guard.
    css = _STYLES_PATH.read_text(encoding="utf-8-sig").lstrip("﻿")
    return f"<style>\n{css}\n</style>"


def inject_css() -> None:
    """Inject the single stylesheet into the page once."""
    import streamlit as st

    st.markdown(build_css(), unsafe_allow_html=True)


def utility_bar() -> None:
    """Render the top utility bar: context text left, small links right."""
    import streamlit as st

    st.markdown(
        (
            '<div class="pan-utility">'
            '<div class="pan-utility-left">You are in '
            "<b>Campaign Analytics</b></div>"
            '<div class="pan-utility-right">'
            '<a href="#">About</a><a href="#">Docs</a><a href="#">Support</a>'
            "</div></div>"
            '<hr class="pan-rule" />'
        ),
        unsafe_allow_html=True,
    )


def nav_bar(active: str = "New Promo", title: str = APP_TITLE) -> None:
    """Render the main nav bar: red text brand left, nav items right.

    The brand is the text title only (no logo image). ``active`` names the nav
    item to highlight in red with a thin red underline; the rest are dark text.
    """
    import streamlit as st

    items = "".join(
        (
            f'<span class="pan-navitem{" active" if item == active else ""}">'
            f"{html.escape(item)}</span>"
        )
        for item in NAV_ITEMS
    )
    st.markdown(
        (
            '<div class="pan-nav">'
            f'<div class="pan-brand">{html.escape(title)}</div>'
            f'<div class="pan-navitems">{items}</div>'
            "</div>"
            '<hr class="pan-rule" />'
        ),
        unsafe_allow_html=True,
    )


# Backwards-compatible alias: the earlier shell called ``header`` to render the
# title. It now renders the nav bar, keeping the text-title-only contract.
def header(title: str = APP_TITLE) -> None:
    """Render the brand/nav header (text title only, no image)."""
    nav_bar(active="New Promo", title=title)


def breadcrumb(*crumbs: str) -> None:
    """Render a gray breadcrumb row, e.g. ``breadcrumb("Home", "Results")``."""
    import streamlit as st

    if not crumbs:
        crumbs = ("Home",)
    sep = '<span class="sep">&rsaquo;</span>'
    trail = sep.join(html.escape(c) for c in crumbs)
    st.markdown(f'<div class="pan-breadcrumb">{trail}</div>', unsafe_allow_html=True)


def hero_kpi_html(number: str, label: str, foot: str = "") -> str:
    """Return the HTML for the hero's red-gradient KPI panel.

    Large white ``number`` over a small ``label``, with an optional ``foot``
    line. Used on the right side of the hero in place of a photo.
    """
    foot_html = (
        f'<div class="kpi-foot">{html.escape(foot)}</div>' if foot else ""
    )
    return (
        '<div class="pan-hero-kpi">'
        f'<div class="kpi-label">{html.escape(label)}</div>'
        f'<div class="kpi-number">{html.escape(str(number))}</div>'
        f"{foot_html}</div>"
    )


def hero_text_html(title: str, subtitle: str) -> str:
    """Return the HTML for the hero's left column: big title + one-line sub."""
    return (
        f'<div class="pan-hero-title">{html.escape(title)}</div>'
        f'<div class="pan-hero-sub">{html.escape(subtitle)}</div>'
    )


# --- metric_panel kept as a thin compatibility wrapper over the KPI panel ---
def metric_panel(number: str, caption: str) -> None:
    """Render the headline KPI as the red-gradient hero panel.

    Retained for callers that show the standalone headline number (e.g. the
    WHAT-IF tab). Renders the same red-gradient KPI block used in the hero.
    """
    import streamlit as st

    st.markdown(hero_kpi_html(number, caption), unsafe_allow_html=True)


def card(heading: str, body_html: str) -> None:
    """Render a white rounded content card.

    White background, 16px corners, soft shadow, a red section heading, a light
    gray divider, then ``body_html`` (which the caller builds safely).
    """
    import streamlit as st

    st.markdown(
        (
            '<div class="pan-card">'
            f'<div class="pan-card-heading">{html.escape(heading)}</div>'
            '<hr class="pan-divider" />'
            f"{body_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def tile(title: str, body_html: str, *, emphasis: bool = False) -> None:
    """Render one 2x2-grid tile.

    ``emphasis=True`` renders the red-gradient tile with white text (used for
    Ready Toppers); otherwise a white tile with a thin red border.
    """
    import streamlit as st

    kind = "red" if emphasis else "white"
    st.markdown(
        (
            f'<div class="pan-tile {kind}">'
            f'<div class="pan-tile-title">{html.escape(title)}</div>'
            f"{body_html}</div>"
        ),
        unsafe_allow_html=True,
    )


def chip(text: str) -> str:
    """Return the HTML for a small stat chip (inline, pill-shaped)."""
    return f'<span class="pan-chip">{html.escape(str(text))}</span>'
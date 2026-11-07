"""Theme for the Promo Audience Navigator webapp.

The visual identity takes influence from the BPI website and app (palette, type
feel, spacing, tone) without using any BPI logo, wordmark or asset: a calm
light-or-dark page, a centered ~1200px column, Dax headings with Avenir Next
body, dark text, and a deep-red primary with a red gradient for buttons and the
hero panel. Gold is a small decorative accent only. All titles, tabs, buttons
and labels are Title Case.

Colours live in exactly one place, section 1 ("design tokens") of
``app/styles.css``, as ``light-dark()`` custom properties. ``PALETTE`` below
mirrors the light values and the ``[theme]`` block of ``.streamlit/config.toml``
so the three stay in sync (tests compare them). Type, radius, spacing and motion
tokens are likewise defined once: type here, the rest in the stylesheet.

Light and dark mode are resolved in the browser: every colour token is a
`light-dark()` pair, and Streamlit sets `color-scheme` on its root element
the moment the theme changes in Settings (top-right menu). Nothing is decided
on the server, so a switch never waits for a rerun; outside the app root the
stylesheet follows the operating-system preference.

Render helpers compose the page chrome (:func:`utility_bar`, :func:`nav_bar`,
:func:`context_banner`, :func:`hero_text_html`), the reusable :func:`card`,
:func:`tile` and :func:`chip`, small markup helpers for label/value fields and
tables, and :func:`loading`, the shared wait indicator. ``streamlit`` is imported
lazily inside each helper so importing ``app.theme`` never requires a running
Streamlit server.
"""

from __future__ import annotations

import html
from contextlib import contextmanager
from pathlib import Path

# --- palette: LIGHT values, mirrored from styles.css section 1 ---

PALETTE = {
    "PRIMARY_RED": "#AE1319",   # deep primary red
    "RED_BRIGHT": "#D8232A",    # lighter red (gradient end)
    "ACCENT_GOLD": "#E0A800",   # decorative accent only (never carries text)
    "PANEL_WHITE": "#FFFFFF",   # white surface
    "TEXT_DARK": "#1F2328",     # body text
}

# Convenience module-level aliases.
PRIMARY_RED = PALETTE["PRIMARY_RED"]
RED_BRIGHT = PALETTE["RED_BRIGHT"]
ACCENT_GOLD = PALETTE["ACCENT_GOLD"]
PANEL_WHITE = PALETTE["PANEL_WHITE"]
TEXT_DARK = PALETTE["TEXT_DARK"]

# --- type tokens: the single source of truth for fonts, weights and sizes ---
#
# Dax (headings) and Avenir Next (body/UI) are commercial: their files live,
# git-ignored, in app/static/fonts/{dax-web,avenir-next-web}. When a file is
# missing the browser falls back along the stack, so the app still renders on
# any machine (Bahnschrift for headings, Segoe UI for body). Manrope (SIL OFL)
# is bundled in app/static/fonts/manrope and used for numbers. The
# ``[[theme.fontFaces]]`` entries in .streamlit/config.toml load the files.

FONT_FAMILIES = {
    "heading": "Dax",
    "body": "Avenir Next",
    "number": "Manrope",
}

FONT_STACKS = {
    "heading": ("Dax", "Bahnschrift", "Segoe UI", "sans-serif"),
    "body": ("Avenir Next", "Segoe UI", "Arial", "sans-serif"),
    "number": ("Manrope", "Avenir Next", "Segoe UI", "sans-serif"),
}

FONT_WEIGHTS = {"regular": 400, "medium": 500, "demi": 600, "bold": 700}

# role -> (font key, weight, font size, line height)
TYPE_ROLES = {
    "title": ("heading", 700, "2.5rem", "1.1"),
    "section": ("heading", 500, "1.5rem", "1.2"),
    "subsection": ("heading", 500, "1.25rem", "1.2"),
    "card-title": ("heading", 500, "1.125rem", "1.25"),
    "body": ("body", 400, "1rem", "1.55"),
    "kpi-hero": ("number", 700, "2.75rem", "1.05"),
    "kpi-tile": ("number", 700, "1.5rem", "1.05"),
    "caption": ("body", 400, "0.8125rem", "1.4"),
    "button": ("body", 600, "0.9375rem", "1.2"),
    "table": ("body", 400, "0.875rem", "1.4"),
    "table-head": ("body", 600, "0.8125rem", "1.3"),
}


def font_stack(key: str) -> str:
    """Return the CSS ``font-family`` value for a font key (quoted names)."""
    return ", ".join(
        name if name == "sans-serif" else f'"{name}"' for name in FONT_STACKS[key]
    )


def type_tokens_css() -> str:
    """Return a ``:root`` block exposing the type tokens as CSS variables."""
    lines = [f"  --pan-font-{key}: {font_stack(key)};" for key in FONT_STACKS]
    lines += [f"  --pan-weight-{n}: {w};" for n, w in FONT_WEIGHTS.items()]
    for role, (font, weight, size, leading) in TYPE_ROLES.items():
        lines += [
            f"  --pan-type-{role}-font: var(--pan-font-{font});",
            f"  --pan-type-{role}-weight: {weight};",
            f"  --pan-type-{role}-size: {size};",
            f"  --pan-type-{role}-leading: {leading};",
        ]
    return ":root {\n" + "\n".join(lines) + "\n}"


# Licensed font files that should exist locally (flat copies, git-ignored).
_FONTS_DIR = Path(__file__).resolve().parent / "static" / "fonts"
COMMERCIAL_FONT_FILES = (
    "avenir-next-web/AvenirNext-Regular.woff2",
    "avenir-next-web/AvenirNext-Medium.woff2",
    "avenir-next-web/AvenirNext-Demi.woff2",
    "avenir-next-web/AvenirNext-Bold.woff2",
    "dax-web/Dax-Medium.ttf",
    "dax-web/Dax-Bold.otf",
)


def missing_font_files() -> list[str]:
    """Return the commercial font files not present, i.e. using fallbacks."""
    return [f for f in COMMERCIAL_FONT_FILES if not (_FONTS_DIR / f).is_file()]


# The app title is text only -- no logo image.
APP_TITLE = "Promo Audience Navigator"

# Tab labels in workflow order (Title Case). main.py builds its tabs from this.
TAB_LABELS = [
    "New Promo",
    "Results",
    "What-If",
    "Personas",
    "Past Promos",
    "Ask Assistant",
]

# Segment -> marker shape (a shape as well as a colour, so segments differ
# without relying on colour alone). The colour comes from the CSS class.
SEGMENT_STYLES = {
    "Ready Toppers": ("diamond", "ready"),
    "Untapped Wealth": ("triangle", "untapped"),
    "Willing but Stretched": ("circle", "stretched"),
    "Not Now": ("square", "notnow"),
}

# The single stylesheet, resolved relative to this file so it loads from any cwd.
_STYLES_PATH = Path(__file__).resolve().parent / "styles.css"


def build_css() -> str:
    """Return the single CSS block injected once into the page.

    Prepends the type tokens to ``app/styles.css`` (which carries the colour,
    radius, spacing and motion tokens and every component rule) and appends the
    colour-scheme override for ``mode`` when one is given.
    """
    # "utf-8-sig" drops a leading byte-order mark (BOM) if an editor on Windows
    # adds one. A BOM in front of the stylesheet makes the browser discard the
    # first rule block, which would drop the colour tokens. The lstrip is a
    # second guard.
    css = _STYLES_PATH.read_text(encoding="utf-8-sig").lstrip("\ufeff")
    return f"<style>\n{type_tokens_css()}\n{css}\n</style>"


def inject_css() -> None:
    """Inject the single stylesheet into the page once."""
    import streamlit as st

    st.markdown(build_css(), unsafe_allow_html=True)


# --- page chrome ---


def utility_bar() -> None:
    """Render the slim top bar: where the user is (no placeholder links)."""
    st_markdown(
        '<div class="pan-utility">'
        '<div class="pan-utility-left">You are in '
        "<b>Campaign Analytics</b></div>"
        "</div>"
        '<hr class="pan-rule" />'
    )


def nav_bar(active: str = "New Promo", title: str = APP_TITLE) -> None:
    """Render the brand bar: the text title only (no logo image).

    The real navigation is the tab row, so no duplicate nav items are drawn.
    ``active`` is accepted for backward compatibility and is unused.
    """
    st_markdown(
        '<div class="pan-nav">'
        f'<div class="pan-brand">{html.escape(title)}</div>'
        "</div>"
        '<hr class="pan-rule" />'
    )


# Backwards-compatible alias: the earlier shell called ``header`` to render the
# title. It now renders the brand bar, keeping the text-title-only contract.
def header(title: str = APP_TITLE) -> None:
    """Render the brand header (text title only, no image)."""
    nav_bar(active="New Promo", title=title)


def st_markdown(markup: str) -> None:
    """Render trusted theme markup (callers escape any dynamic text)."""
    import streamlit as st

    st.markdown(markup, unsafe_allow_html=True)


def context_banner_html(items: list[str] | None) -> str:
    """Return the "Current Run" banner HTML; ``None``/empty means no run yet."""
    if not items:
        body = (
            '<span class="pan-context-item">No run yet. Design a promo in '
            "New Promo to begin.</span>"
        )
    else:
        body = "".join(
            f'<span class="pan-context-item">{html.escape(str(i))}</span>' for i in items
        )
    return (
        '<div class="pan-context">'
        '<span class="pan-context-label">Current Run</span>'
        f"{body}</div>"
    )


def context_banner(items: list[str] | None) -> None:
    """Render the current-run context banner above the tabs."""
    st_markdown(context_banner_html(items))


def section_label_html(title: str, helper: str = "") -> str:
    """Return a small labelled group heading with an optional helper line."""
    helper_html = (
        f'<span class="pan-section-help">{html.escape(helper)}</span>' if helper else ""
    )
    return (
        '<div class="pan-section-label">'
        f'<span class="pan-section-title">{html.escape(title)}</span>'
        f"{helper_html}</div>"
    )


def section_label(title: str, helper: str = "") -> None:
    """Render a labelled group heading (used to group form controls)."""
    st_markdown(section_label_html(title, helper))


def next_step_html(text: str) -> str:
    """Return a one-line "Next" cue (plain text; it is not a control)."""
    return f'<div class="pan-next"><b>Next:</b> {html.escape(text)}</div>'


def next_step(text: str) -> None:
    """Render a one-line next-step cue."""
    st_markdown(next_step_html(text))


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
        '<div class="pan-hero-text">'
        f'<div class="pan-hero-title">{html.escape(title)}</div>'
        f'<div class="pan-hero-sub">{html.escape(subtitle)}</div>'
        "</div>"
    )


# --- metric_panel kept as a thin compatibility wrapper over the KPI panel ---
def metric_panel(number: str, caption: str) -> None:
    """Render the headline KPI as the red-gradient hero panel.

    Retained for callers that show the standalone headline number (e.g. the
    WHAT-IF tab). Renders the same red-gradient KPI block used in the hero.
    """
    st_markdown(hero_kpi_html(number, caption))


# --- cards, tiles, chips, fields, tables ---


def segment_marker_html(heading: str) -> tuple[str, str]:
    """Return ``(marker_html, css_class)`` for a heading that ends in a segment.

    Matches a bare segment label ("Ready Toppers") or a promo-prefixed one
    ("P004 -- Ready Toppers"). Headings with no segment give ``("", "")``.
    """
    for segment, (shape, key) in SEGMENT_STYLES.items():
        if heading == segment or heading.endswith(f" {segment}"):
            marker = f'<span class="pan-marker pan-marker--{shape}" aria-hidden="true"></span>'
            return marker, f"pan-seg--{key}"
    return "", ""


def card(heading: str, body_html: str) -> None:
    """Render a surface card: marker (for segments), heading, divider, body."""
    marker, seg_class = segment_marker_html(heading)
    st_markdown(
        f'<div class="pan-card {seg_class}">'
        f'<div class="pan-card-heading">{marker}{html.escape(heading)}</div>'
        '<hr class="pan-divider" />'
        f"{body_html}"
        "</div>"
    )


def tile(title: str, body_html: str, *, emphasis: bool = False) -> None:
    """Render one 2x2-grid tile.

    ``emphasis=True`` renders the red-gradient tile with white text (used for
    Ready Toppers); otherwise a surface tile with a segment-coloured edge. Each
    segment also gets its own marker shape.
    """
    kind = "red" if emphasis else "white"
    marker, seg_class = segment_marker_html(title)
    st_markdown(
        f'<div class="pan-tile {kind} {seg_class}">'
        f'<div class="pan-tile-title">{marker}{html.escape(title)}</div>'
        f"{body_html}</div>"
    )


def chip(text: str) -> str:
    """Return the HTML for a small stat chip (inline, pill-shaped)."""
    return f'<span class="pan-chip">{html.escape(str(text))}</span>'


def chips_html(chips: list[str]) -> str:
    """Wrap already-built chip HTML in a wrapping row."""
    return f'<div class="pan-chips">{"".join(chips)}</div>'


def field_html(label: str, value_html: str) -> str:
    """Return one label/value pair (``value_html`` must already be escaped)."""
    return (
        '<div class="pan-field">'
        f'<span class="pan-field-label">{html.escape(label)}</span>'
        f'<span class="pan-field-value">{value_html}</span>'
        "</div>"
    )


def fields_html(rows: list[tuple[str, str]]) -> str:
    """Return a stack of label/value pairs from ``(label, escaped_value)`` rows."""
    return "".join(field_html(label, value) for label, value in rows)


# --- loading: shown only on a real wait ---

_LOADER_SUBTEXT = {
    "analysis": "This can take a moment.",
    "rescore": "Updating the results for the new threshold.",
    "personas": "This can take a moment for larger audiences.",
}


def _loader_visual(kind: str) -> str:
    if kind == "personas":
        # Tiles a-h and their colours match the swap plan in styles.css section 5.
        tiles = "".join(
            f'<span class="pan-pz-tile pan-pz-{k}{" gold" if gold else ""}"></span>'
            for k, gold in zip("abcdefgh", (1, 0, 1, 0, 1, 1, 0, 0))
        )
        return f'<div class="pan-pz" aria-hidden="true">{tiles}</div>'
    docs = '<span class="pan-doc"></span>' * 5
    return (
        '<div class="pan-docs" aria-hidden="true">'
        f'<div class="pan-docs-viewport"><div class="pan-docs-track">{docs}</div></div>'
        '<span class="pan-mag"></span></div>'
    )


def loader_html(kind: str, message: str, *, slow: bool = False) -> str:
    """Return the loader overlay markup.

    ``kind`` is ``"analysis"`` / ``"rescore"`` (documents under a magnifier) or
    ``"personas"`` (boxes settling into groups). The overlay is fixed in the
    viewport, so showing it never moves the page, and the stylesheet keeps it
    invisible for a short delay (longer when ``slow``) so a fast or cached run
    never flashes it. There is no progress bar: the wait length is unknown.
    """
    delay_class = " pan-loading--slow" if slow else ""
    sub = _LOADER_SUBTEXT.get(kind, "")
    sub_html = f'<div class="pan-loading-sub">{html.escape(sub)}</div>' if sub else ""
    return (
        f'<div class="pan-loading{delay_class}" role="status" aria-live="polite">'
        '<div class="pan-loading-card">'
        f"{_loader_visual(kind)}"
        f'<div class="pan-loading-msg">{html.escape(message)}</div>'
        f"{sub_html}"
        '<div class="pan-skel" aria-hidden="true"><span></span><span></span><span></span></div>'
        "</div></div>"
    )


@contextmanager
def loading(kind: str, message: str, *, slow: bool = False):
    """Show the loader while the ``with`` body runs, then remove it.

    Drop-in replacement for ``st.spinner``: it only wraps the existing call and
    changes no computation or caching.
    """
    import streamlit as st

    slot = st.empty()
    slot.markdown(loader_html(kind, message, slow=slow), unsafe_allow_html=True)
    try:
        yield
    finally:
        slot.empty()
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
import re
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

# --- palette: LIGHT values, mirrored from styles.css section 1 ---

PALETTE = {
    "PRIMARY_RED": "#AE1319",   # deep primary red
    "RED_BRIGHT": "#D8232A",    # lighter red (gradient end)
    "ACCENT_GOLD": "#E0A800",   # decorative accent only (never carries text)
    "PANEL_WHITE": "#FFFFFF",   # white surface
    "TEXT_DARK": "#1F2328",     # body text
    "MAP_RED": "#AE1319",           # --pan-map-fill-a (light)
    "MAP_RED_SELECTED": "#D8232A",  # --pan-map-selected (light)
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


# --- token reader: section 1 of styles.css, for surfaces outside the page CSS ---
#
# Iframes (the group picker) cannot see the page's custom properties, so they
# are handed the resolved light and dark values of the tokens they need. The
# reader parses ONLY the ``:root`` block under the "1. DESIGN TOKENS" header and
# never invents a value: anything unreadable or unknown raises TokenError.

# PALETTE key -> section 1 token. Only entries whose light value equals the
# token's light value are listed (checked against section 1).
PALETTE_TOKENS = {
    "PRIMARY_RED": "--pan-primary",           # #AE1319
    "RED_BRIGHT": "--pan-primary-to",         # #D8232A
    "ACCENT_GOLD": "--pan-gold",              # #E0A800
    "PANEL_WHITE": "--pan-surface",           # #FFFFFF
    "TEXT_DARK": "--pan-text",                # #1F2328
    "MAP_RED": "--pan-map-fill-a",            # #AE1319
    "MAP_RED_SELECTED": "--pan-map-selected", # #D8232A
}

# Tokens the group picker iframe needs (map, glass, surfaces, text, accents,
# loader).
PICKER_TOKENS = (
    "--pan-map-fill-a",
    "--pan-map-fill-b",
    "--pan-map-selected",
    "--pan-map-muted",
    "--pan-map-shadow",
    "--pan-lift",
    "--pan-dim",
    "--pan-glass-tint-1",
    "--pan-glass-tint-2",
    "--pan-glass-edge",
    "--pan-glass-fallback-1",
    "--pan-glass-fallback-2",
    "--pan-focus",
    "--pan-text",
    "--pan-text-muted",
    "--pan-surface",
    "--pan-surface-2",
    "--pan-border",
    "--pan-primary",
    "--pan-primary-text",
    "--pan-primary-tint",
    "--pan-on-primary",
    "--pan-gold",
    "--pan-series-1",
    "--pan-series-2",
    "--pan-series-3",
    "--pan-series-4",
    "--pan-series-5",
    "--pan-series-6",
    "--loader-accent",
    "--loader-accent-alt",
)


class TokenError(KeyError):
    """A design token is unknown, or the section 1 block cannot be read."""

    def __str__(self) -> str:  # KeyError would repr() the message otherwise
        return str(self.args[0]) if self.args else ""


_SECTION_1_HEADER = "1. DESIGN TOKENS"
_VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*\)")


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split ``text`` at ``sep`` outside any parentheses."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _section_one_declarations(css: str) -> dict[str, str]:
    """Return ``{--name: raw value}`` from the ``:root`` block of section 1."""
    at = css.find(_SECTION_1_HEADER)
    if at < 0:
        raise TokenError("styles.css section 1 (design tokens) block not found")
    # Comments hold the header itself, so strip them only after locating it.
    text = re.sub(r"/\*.*?\*/", "", css[at:], flags=re.S)
    m = re.search(r":root\s*\{", text)
    if not m:
        raise TokenError("styles.css section 1 (design tokens) :root block not found")
    depth, end = 1, None
    for i in range(m.end(), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        raise TokenError("styles.css section 1 (design tokens) :root block is not closed")
    out: dict[str, str] = {}
    for decl in _split_top_level(text[m.end():end], ";"):
        name, colon, value = decl.partition(":")
        name = name.strip()
        if colon and name.startswith("--") and value.strip():
            out[name] = value.strip()
    return out


def _resolve_pair(
    name: str, raw: dict[str, str], stack: tuple[str, ...] = ()
) -> tuple[str, str]:
    """Resolve one token to its ``(light, dark)`` pair, following ``var()``."""
    if name in stack:
        raise TokenError("token cycle: " + " -> ".join(stack + (name,)))
    if name not in raw:
        raise TokenError(f"unknown design token {name}")
    value, stack = raw[name], stack + (name,)

    def side(expr: str, idx: int) -> str:
        return _VAR_RE.sub(
            lambda m: _resolve_pair(m.group(1), raw, stack)[idx], expr.strip()
        )

    if value.startswith("light-dark(") and value.endswith(")"):
        parts = _split_top_level(value[len("light-dark("):-1], ",")
        if len(parts) == 2:
            return side(parts[0], 0), side(parts[1], 1)
        raise TokenError(f"design token {name} has a malformed light-dark() value")
    return side(value, 0), side(value, 1)


@lru_cache(maxsize=8)
def _read_cached(path: str, mtime_ns: int) -> dict[str, tuple[str, str]]:
    try:
        css = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise TokenError(f"styles.css section 1 (design tokens) unreadable: {exc}") from exc
    raw = _section_one_declarations(css)
    return {name: _resolve_pair(name, raw) for name in raw}


def read_tokens(css_path: Path = _STYLES_PATH) -> dict[str, tuple[str, str]]:
    """Return every section 1 custom property as a ``(light, dark)`` pair.

    Plain values give ``(v, v)``; ``light-dark(a, b)`` gives ``(a, b)``;
    ``var(--x)`` is resolved against the block, each side separately. Only
    section 1 is read. Results are cached per path and modification time.
    Raises :class:`TokenError` for an unreadable file, a missing block or a
    reference cycle; there are no fallback values.
    """
    try:
        mtime = Path(css_path).stat().st_mtime_ns
    except OSError as exc:
        raise TokenError(f"styles.css section 1 (design tokens) unreadable: {exc}") from exc
    return dict(_read_cached(str(css_path), mtime))


def token_pair(name: str) -> tuple[str, str]:
    """Return the ``(light, dark)`` pair of one token; unknown names raise."""
    tokens = read_tokens()
    if name not in tokens:
        raise TokenError(f"unknown design token {name}")
    return tokens[name]


def iframe_palette(names) -> dict[str, dict[str, str]]:
    """Return ``{"light": {name: value}, "dark": {name: value}}`` for ``names``."""
    palette: dict[str, dict[str, str]] = {"light": {}, "dark": {}}
    for name in names:
        light, dark = token_pair(name)
        palette["light"][name] = light
        palette["dark"][name] = dark
    return palette


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


# --- shared card parts: badge, banner, stat tile, bar, tooltip ---

_KINDS = ("neutral", "info", "success", "warning", "error")


def _kind_class(prefix: str, kind: str) -> str:
    return f" {prefix}--{kind}" if kind in _KINDS and kind != "neutral" else ""


def badge_html(text: str, kind: str = "neutral") -> str:
    """Return a small pill badge (e.g. the Demo Mode badge)."""
    return f'<span class="pan-badge{_kind_class("pan-badge", kind)}">{html.escape(text)}</span>'


def banner_html(text: str, kind: str = "info") -> str:
    """Return a full-width message banner."""
    return (
        f'<div class="pan-banner{_kind_class("pan-banner", kind)}" role="status">'
        f"{html.escape(text)}</div>"
    )


def tooltip_html(label: str, tip: str) -> str:
    """Return ``label`` with a hover/focus tooltip (also a native title)."""
    return (
        f'<span class="pan-tip" tabindex="0" title="{html.escape(tip, quote=True)}">'
        f"{html.escape(label)}"
        f'<span class="pan-tip-text" aria-hidden="true">{html.escape(tip)}</span></span>'
    )


def stat_tile_html(label: str, tip: str = "") -> str:
    """Return one stat tile; the tooltip is attached when ``tip`` is given."""
    inner = tooltip_html(label, tip) if tip else html.escape(label)
    return f'<div class="pan-stat">{inner}</div>'


def stat_tiles_html(tiles: list[str]) -> str:
    """Wrap already-built stat tiles in a wrapping row."""
    return f'<div class="pan-stats">{"".join(tiles)}</div>'


def bar_html(label: str, fraction: float) -> str:
    """Return a labelled horizontal bar; ``fraction`` is clamped to 0..1."""
    try:
        f = min(1.0, max(0.0, float(fraction)))
    except (TypeError, ValueError):
        f = 0.0
    return (
        '<div class="pan-bar">'
        f'<span class="pan-bar-label">{html.escape(label)}</span>'
        '<div class="pan-bar-track"><div class="pan-bar-fill" '
        f'style="width:{f * 100:.1f}%"></div></div></div>'
    )


def persona_section_html(section) -> str:
    """Render a ``webapp_core.persona_view.PersonaSection`` (Requirements 7.1-7.12).

    Sentence rows each with a bar, the "Total For <Segment Name>" line, the
    note, the takeaway, or the "personas not generated" line. ``None`` renders
    nothing. All text is escaped here.
    """
    if section is None:
        return ""
    heading = '<div class="pan-line strong">Expected Joiners By Persona</div>'
    if section.unavailable_text:
        return heading + f'<div class="pan-line">{html.escape(section.unavailable_text)}</div>'
    bars = "".join(bar_html(line.text, line.bar_pct / 100.0) for line in section.lines)
    total = (
        f"{section.total_line}: about {section.total_joiners:,} of "
        f"{section.total_leads:,} likely to join"
    )
    out = heading + bars + f'<div class="pan-line strong">{html.escape(total)}</div>'
    if section.note:
        out += f'<div class="pan-line">{html.escape(section.note)}</div>'
    if section.takeaway:
        out += f'<div class="pan-line strong">{html.escape(section.takeaway)}</div>'
    return out


def decision_card_body_html(view, extra_html: str = "") -> str:
    """Render a ``CardView`` (``webapp_core.card_view``) as card body HTML.

    The single renderer used by the Results and Personas pages (Requirement
    4.12). ``extra_html`` is trusted, already escaped markup appended below
    (the persona breakdown today). Everything else is escaped here.
    """
    stats = stat_tiles_html([stat_tile_html(s.label, s.tooltip) for s in view.stats])
    drivers = ", ".join(html.escape(d) for d in view.drivers) or "None"
    exclusions = (
        ", ".join(html.escape(e) for e in view.exclusions) if view.exclusions else "None"
    )
    rows = [
        ("Action", html.escape(view.action)),
        ("Dominant Channel", html.escape(view.channel)),
        ("Message Angle", html.escape(view.angle)),
        (view.why_heading, drivers),
        (view.not_contacted_heading, exclusions),
    ]
    persona = persona_section_html(view.persona_lines)
    return stats + fields_html(rows) + persona + extra_html


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


# --- Part 8: Job button ring (F2 redesign, Requirement 7) ---

_RING_STATES = ("running", "done", "error")

# Spark placement for the Completion_Fireworks (Requirement 4.14): 4 corners,
# 2 on the top edge, 2 on the bottom edge, left and right middles.
# (x, y, outward angle in degrees)
_SPARKS = (
    ("0%", "0%", -135),
    ("100%", "0%", -45),
    ("100%", "100%", 45),
    ("0%", "100%", 135),
    ("33%", "0%", -90),
    ("67%", "0%", -90),
    ("33%", "100%", 90),
    ("67%", "100%", 90),
    ("0%", "50%", 180),
    ("100%", "50%", 0),
)
_SPARK_COLOURS = ("--pan-primary", "--pan-primary-to", "--pan-gold")


def job_ring_html(state: str, phase: float = 0.0) -> str:
    """Return the Job_Button ring markup for the F2 redesign (Requirement 7).

    ``state`` is ``"running"``, ``"done"`` or ``"error"`` (anything else raises
    ``ValueError``). ``phase`` is the ring position as a fraction of one lap
    (from ``webapp_core.job_motion.ring_phase``), clamped into ``[0, 1)``;
    a non-finite value becomes 0. Styling lives in ``styles.css`` and the slot
    wiring in ``app/p8_effects.py``.

    Markup contract (CSS and wiring depend on it exactly)::

        <div class="p8-ring p8-ring--{state}" style="--p8-phase:{phase:.4f}"
             aria-hidden="true">
          <svg class="p8-ring-svg" preserveAspectRatio="none" focusable="false">
            <rect class="p8-ring-glow" pathLength="100"/>
            <rect class="p8-ring-line" pathLength="100"/>
          </svg>
          <!-- "done" only: -->
          <span class="p8-sparks">
            <span class="p8-spark"
                  style="--x:0%;--y:0%;--a:-135deg;--i:0;--c:var(--pan-primary)"></span>
            ... 10 sparks in total ...
          </span>
        </div>

    - ``--p8-phase`` is a unitless number (not a duration) and the outer
      ``style`` is its only inline style; the rects carry no geometry
      attributes (CSS sets width, height, x, y and rx).
    - Sparks: corners (0%/100%, angles -135, -45, 45, 135), top edge at 33% and
      67% (angle -90), bottom edge at 33% and 67% (angle 90), left middle
      (angle 180), right middle (angle 0). ``--i`` is 0..9 for the stagger and
      ``--c`` cycles ``--pan-primary``, ``--pan-primary-to``, ``--pan-gold``.
    - The ring is decorative, so the whole element is ``aria-hidden``.
    """
    if state not in _RING_STATES:
        raise ValueError(f"state must be one of {_RING_STATES}, got {state!r}")
    try:
        value = float(phase)
    except (TypeError, ValueError):
        value = 0.0
    if value != value or value in (float("inf"), float("-inf")):
        value = 0.0
    # 0.9999 keeps the formatted value below 1 at 4 decimals.
    value = min(max(value, 0.0), 0.9999)
    sparks = ""
    if state == "done":
        spans = "".join(
            f'<span class="p8-spark" style="--x:{x};--y:{y};--a:{a}deg;--i:{i};'
            f'--c:var({_SPARK_COLOURS[i % len(_SPARK_COLOURS)]})"></span>'
            for i, (x, y, a) in enumerate(_SPARKS)
        )
        sparks = f'<span class="p8-sparks">{spans}</span>'
    return (
        f'<div class="p8-ring p8-ring--{state}" style="--p8-phase:{value:.4f}" '
        'aria-hidden="true">'
        '<svg class="p8-ring-svg" preserveAspectRatio="none" focusable="false">'
        '<rect class="p8-ring-glow" pathLength="100"/>'
        '<rect class="p8-ring-line" pathLength="100"/>'
        "</svg>"
        f"{sparks}"
        "</div>"
    )

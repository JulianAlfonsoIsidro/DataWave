"""Theme for the Promo Audience Manager webapp.

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

import contextvars
import dataclasses
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
    # Part 9 round 2: Help And FAQs equations (a system font; nothing bundled)
    "math": ("Cambria Math", "Cambria", "STIX Two Math", "Times New Roman", "serif"),
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
APP_TITLE = "Promo Audience Manager"

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


# --- Part 8 polish: count-up after a Job (fix 9) ---
# A section rendered inside ``counting(el)`` draws every number in its text
# as NumberFlow-style digit columns that roll from 0 to the value: each digit
# is a 0-9 strip; the ones place spins two extra cycles and the tens one, so
# it reads as counting. Words, commas, the peso sign and percent stay fixed.
# ``el`` (seconds since the Job's generation) is a negative animation delay,
# so a rerun during the roll continues it; outside the window callers pass
# None and the plain text renders. Screen readers get the final text only.
_COUNT_STATE: contextvars.ContextVar = contextvars.ContextVar("p8_count", default=None)
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


@contextmanager
def counting(el: float | None, gen: str = ""):
    """Numbers drawn inside count up (staggered in reading order) when ``el``
    is not None; with None this does nothing. ``gen`` (the generation id) goes
    into the class names, so a new generation always gets fresh elements and
    replays, while the same generation never does."""
    if el is None:
        yield
        return
    token = _COUNT_STATE.set([float(el), 0, re.sub(r"[^a-z0-9-]", "", str(gen).lower())])
    try:
        yield
    finally:
        _COUNT_STATE.reset(token)


def counting_el() -> float | None:
    """The active count-up elapsed time, or None outside :func:`counting`."""
    state = _COUNT_STATE.get()
    return None if state is None else state[0]


def _gen_class() -> str:
    state = _COUNT_STATE.get()
    return f" p8-g-{state[2]}" if state is not None and state[2] else ""


def _digit_column(ch: str, digits_right: int) -> str:
    cycles = 2 if digits_right == 0 else 1 if digits_right == 1 else 0
    strip = "".join(f"<span>{d}</span>" for _ in range(cycles + 1) for d in "0123456789")
    return (
        f'<span class="p8-cd"><span class="p8-cs{_gen_class()}" style="--d:{cycles * 10 + int(ch)}">'
        f"{strip}</span></span>"
    )


def count_up_html(text: str, el: float, start: int = 0) -> tuple[str, int]:
    """Count-up markup for ``text`` and the next stagger index.

    Text without digits comes back escaped and unchanged.
    """
    text = str(text)
    parts: list[str] = []
    n, last = start, 0
    for m in _NUMBER_RE.finditer(text):
        parts.append(html.escape(text[last:m.start()]))
        num = m.group(0)
        left = sum(c.isdigit() for c in num)
        cells = []
        for c in num:
            if c.isdigit():
                left -= 1
                cells.append(_digit_column(c, left))
            else:
                cells.append(f'<span class="p8-cc">{html.escape(c)}</span>')
        parts.append(f'<span class="p8-cnum" style="--n:{n}">{"".join(cells)}</span>')
        n += 1
        last = m.end()
    if n == start:
        return html.escape(text), n
    parts.append(html.escape(text[last:]))
    return (
        f'<span class="p8-count" style="--p8-el:{float(el):.3f}s">'
        f'<span class="p8-sr">{html.escape(text)}</span>'
        f'<span class="p8-count-vis" aria-hidden="true"><!--cv-->{"".join(parts)}<!--/cv--></span></span>',
        n,
    )


def count_text_html(text: str) -> str:
    """``text`` escaped, or as a count-up inside an active :func:`counting`."""
    state = _COUNT_STATE.get()
    if state is None:
        return html.escape(str(text))
    markup, state[1] = count_up_html(text, state[0], state[1])
    return markup


_CARD_GROUP: contextvars.ContextVar = contextvars.ContextVar("p8_card_group", default="page")


@contextmanager
def card_group(name: str):
    """Cards drawn inside stagger among themselves (one group per tab), so a
    change on a hidden tab never delays the cards on the visible one."""
    token = _CARD_GROUP.set(str(name))
    try:
        yield
    finally:
        _CARD_GROUP.reset(token)


_CV_RE = re.compile(r"<!--cv-->.*?<!--/cv-->", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _card_sig(heading: str, body_html: str) -> str:
    """Fingerprint of what a card says (count-up columns and markup ignored),
    so a rerun that only re-renders the same content never replays it."""
    import hashlib

    text = _TAG_RE.sub(" ", _CV_RE.sub("", f"{heading}\n{body_html}"))
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:16]


def swoop_attrs(heading: str, body_html: str) -> tuple[str, str]:
    """``(class, style)`` for a card that is new or changed: it fades in while
    rising, one by one in reading order (Part 8 polish). Empty otherwise."""
    try:
        import ui_effects

        sig = _card_sig(heading, body_html)
        motion = ui_effects.card_motion(heading, sig, _CARD_GROUP.get())
    except Exception:  # noqa: BLE001 - presentation only, never block a render
        motion = None
    if motion is None:
        return "", ""
    el, slot, variant = motion
    # After a Job the cards wait for the finishing loader to fade.
    start = "var(--p8-gen-start)" if counting_el() is not None else "var(--pan-dur-none)"
    # The content tag makes the class differ whenever the content does, so
    # React rewrites it (clearing the played marker) even when a new card
    # lands in the old card's place; the a/b name restarts a running entrance.
    cls = f" p8-swoop p8-swoop-{'b' if variant else 'a'} p8-c-{sig[:8]}"
    return cls, f"--i:{slot};--p8-el:{el:.3f}s;--p8-sw-start:{start}"


def text_in_attrs() -> tuple[str, str]:
    """``(class, style)`` for an important text box inside :func:`counting`:
    it fades in from the top once per generation (fix 6). Empty outside."""
    el = counting_el()
    if el is None:
        return "", ""
    return f" p8-text-in{_gen_class()}", f"--p8-el:{el:.3f}s"


def roll_number_html(cells, *, plain: str) -> str:
    """CSS number roll markup (Part 8, F5, Requirement 11).

    ``cells`` come from ``webapp_core.number_roll.plan_roll``. The plain value
    sits in a screen-reader span (so readers and AppTest find the same text as
    the static number); the drawn cells are ``aria-hidden``. A ``roll`` cell is
    a clipped 0-9 strip that slides from the previous digit to the new one.
    """
    parts = []
    for c in cells:
        ch = html.escape(c.char)
        if c.kind == "roll":
            strip = "".join(f"<span>{d}</span>" for d in "0123456789")
            parts.append(
                f'<span class="p8-d is-roll" style="--p8-from:{int(c.prev)};--p8-to:{int(c.char)}">'
                f'<span class="p8-strip">{strip}</span></span>'
            )
        elif c.kind == "enter":
            parts.append(f'<span class="p8-c is-enter">{ch}</span>')
        else:
            parts.append(f'<span class="p8-c">{ch}</span>')
    return (
        '<span class="p8-num">'
        f'<span class="p8-sr">{html.escape(plain)}</span>'
        f'<span class="p8-num-vis" aria-hidden="true">{"".join(parts)}</span>'
        "</span>"
    )


def selected_readout_html(text: str, prev: str | None = None) -> str:
    """The "Selected: <value>" line under a threshold slider (caption style).

    With a ``prev`` that differs, the changed digits roll from the old value
    to the new one (:func:`roll_number_html`); otherwise the text is static.
    """
    value_html = html.escape(str(text))
    if prev is not None:
        from webapp_core.number_roll import plan_roll

        cells = plan_roll(prev, str(text))
        if any(c.kind != "static" for c in cells):
            value_html = roll_number_html(cells, plain=str(text))
    return f'<div class="pan-selected">Selected: {value_html}</div>'


def hero_kpi_html(number: str, label: str, foot: str = "", *, prev: str | None = None) -> str:
    """Return the HTML for the hero's red-gradient KPI panel.

    Large white ``number`` over a small ``label``, with an optional ``foot``
    line. Used on the right side of the hero in place of a photo.

    Part 8 (F5): ``prev`` is the previously shown text of this number. With
    ``None`` the output is exactly the static markup; otherwise the number is
    drawn as a CSS roll from ``prev`` (all-static cells when unchanged).
    """
    foot_html = (
        f'<div class="kpi-foot">{html.escape(foot)}</div>' if foot else ""
    )
    return (
        '<div class="pan-hero-kpi">'
        f'<div class="kpi-label">{html.escape(label)}</div>'
        f'<div class="kpi-number">{_kpi_number_html(number, prev)}</div>'
        f"{foot_html}</div>"
    )


def _kpi_number_html(number: str, prev: str | None) -> str:
    """The headline number: count-up after a Job, roll on change, else static."""
    number_html = html.escape(str(number))
    if counting_el() is not None:
        # After a Job: count up from 0 (fix 9); the roll is for later changes.
        number_html = count_text_html(str(number))
    elif prev is not None:
        from webapp_core.number_roll import plan_roll

        cells = plan_roll(prev, str(number))
        # Roll markup only in the render where something changes; every other
        # render keeps the plain static markup (one-shot, Requirement 11.5).
        if any(c.kind != "static" for c in cells):
            number_html = roll_number_html(cells, plain=str(number))
    return number_html


def joiners_pair_html(forecast: float, *, full: bool = True, main_html: str | None = None) -> str:
    """Expected Joiners as a whole number with the forecast beside it.

    Part 9 round 2, Requirement 20: ``87 (Forecasted: 87.3)``, or ``87 (87.3)``
    with ``full=False`` for table cells. ``main_html`` replaces the plain
    whole number (a count-up or roll of it); the bracket is plain text and
    never adds digit columns.
    """
    from webapp_core.number_format import forecast_text, shown_joiners

    main = main_html if main_html is not None else html.escape(f"{shown_joiners(forecast):,}")
    return (
        f'<span class="pan-jp"><span class="pan-jp-main">{main}</span> '
        f'<span class="pan-jp-fc">({html.escape(forecast_text(forecast, short=not full))})</span></span>'
    )


def run_header_html(
    number: str,
    label: str,
    *,
    has_run: bool,
    prev: str | None = None,
    title: str = APP_TITLE,
    forecast: float | None = None,
    sendable_total: int | None = None,
) -> str:
    """The page header: the wordmark and, once a run exists, its one number.

    Replaces the hero (Part 9). The run's details (promo, product, threshold
    and so on) are not repeated here; before any run only the wordmark shows.
    Round 2 (Requirements 20, 21): ``number`` is the rounded whole number
    (owner follow-up: no forecast bracket in the header); with ``forecast``
    and ``sendable_total`` a muted line ``out of 1,595 sendable leads
    (12.8%)`` sits under it, with a plain hover text.
    """
    from webapp_core import number_help

    wordmark = f'<h1 class="pan-wordmark">{html.escape(title)}</h1>'
    # Round 3: before a run the slot is kept (hidden), so the header does not
    # grow when the number first appears; it holds the sub-line too.
    kpi = (
        '<div class="pan-run-kpi is-empty" aria-hidden="true">'
        f'<div class="pan-run-kpi-label">{html.escape(label)}</div>'
        '<div class="pan-run-kpi-number kpi-number">0</div>'
        '<div class="pan-run-kpi-sub">out of 0 sendable leads</div></div>'
    )
    if has_run:
        sub = ""
        if sendable_total is not None and forecast is not None:
            text = number_help.joiners_of_sendable(forecast, sendable_total)
            sub = (
                '<div class="pan-run-kpi-sub">'
                # Plain text: only the big number counts up (Requirement 20.10).
                f"{tooltip_html(text, number_help.header_help(), html.escape(text))}</div>"
            )
        kpi = (
            '<div class="pan-run-kpi">'
            f'<div class="pan-run-kpi-label">{html.escape(label)}</div>'
            f'<div class="pan-run-kpi-number"><span class="kpi-number">{_kpi_number_html(number, prev)}</span></div>'
            f"{sub}</div>"
        )
    return f'<header class="pan-shell">{wordmark}{kpi}</header>'


def _delta_text(delta: float, digits: int = 0) -> str:
    """A signed change with a direction arrow (round 3): never colour alone."""
    if abs(delta) < 0.5 * 10 ** -digits:
        return '<span class="pan-delta is-flat">No change</span>'
    up = delta > 0
    return (
        f'<span class="pan-delta {"is-up" if up else "is-down"}">'
        f'<span aria-hidden="true">{"▲" if up else "▼"}</span> '
        f'{"+" if up else "−"}{abs(delta):,.{digits}f}</span>'
    )


def whatif_segments_html(rows) -> str:
    """What-If per-segment table (round 3): each segment as run and now.

    ``rows`` are ``(segment, [(now, base_or_None, kind), ...])`` for the
    Clients, Expected Joiners and Sendable columns, ``kind`` being "count" or
    "joiners". With no baseline a cell shows only the current figure.
    Round 2 (Requirement 20.4): a joiners cell is the whole number with the
    short bracket ``87 (87.3)`` under the heading "Expected Joiners
    (Forecast)", and its change is the difference of the shown whole numbers.
    Rows arrive in the display order (Requirement 24).
    """
    from webapp_core.number_format import shown_joiners

    head = (
        '<tr><th class="pan-th">Segment</th>'
        '<th class="pan-th pan-num">Clients</th>'
        '<th class="pan-th pan-num">Expected Joiners (Forecast)</th>'
        '<th class="pan-th pan-num">Sendable</th></tr>'
    )
    body = []
    for segment, cells in rows:
        marker, seg_class = segment_marker_html(segment)
        tds = []
        for now, base, kind in cells:
            if kind == "joiners":
                v = f'<span class="pan-wis-now">{joiners_pair_html(now, full=False)}</span>'
                delta = None if base is None else shown_joiners(now) - shown_joiners(base)
            else:
                v = f'<span class="pan-wis-now">{int(now):,}</span>'
                delta = None if base is None else int(now) - int(base)
            if delta is not None:
                v += f'<span class="pan-wis-d">{_delta_text(delta)}</span>'
            tds.append(f'<td class="pan-td pan-num">{v}</td>')
        body.append(
            f'<tr><td class="pan-td pan-strong"><span class="pan-wis-seg {seg_class}">'
            f'{marker}<span>{html.escape(segment)}</span></span></td>{"".join(tds)}</tr>'
        )
    return (
        '<div class="pan-wis"><table class="pan-table" aria-label="Segments at this threshold">'
        f'{head}{"".join(body)}</table></div>'
    )


def segment_flow_html(row, *, reveal: bool = False, title: str | None = None) -> str:
    """Where one segment's clients go (Part 9 round 2, Requirement 27).

    ``row`` is a ``webapp_core.segment_flow.FlowRow`` (one segment, or the
    Total). One stacked bar: Not Contacted, Control Group and Sendable, each
    part as wide as its count, with its count and its share of the clients
    written inside when the part is wide enough. A legend under the bar
    repeats every part's count and share, so colour is never the only cue and
    a narrow part still has its figures. Nothing is recomputed: the counts
    are read from the card; the shares are count / clients.
    """
    from webapp_core.number_format import share_pct
    from webapp_core.segment_flow import reconciles

    parts = (
        ("excluded", "Not Contacted", row.not_contacted),
        ("control", "Control Group", row.control),
        ("sendable", "Sendable", row.sendable),
    )
    segs, legend = [], []
    for key, name, n in parts:
        pct = share_pct(n, row.clients) or "0.0%"
        if n > 0:
            segs.append(
                f'<span class="pan-flow-part pan-flow--{key}" style="flex-grow:{int(n)}">'
                f'<span class="pan-flow-n">{int(n):,}</span>'
                f'<span class="pan-flow-p">{pct}</span></span>'
            )
        legend.append(
            f'<span class="pan-flow-key"><i class="pan-flow-swatch pan-flow--{key}"></i>'
            f'<span class="pan-flow-key-name">{html.escape(name)}</span>'
            f'<span class="pan-flow-key-v">{int(n):,}</span>'
            f'<span class="pan-flow-key-p">({pct})</span></span>'
        )
    name = title or row.segment
    marker, seg_class = segment_marker_html(row.segment)
    label = (
        f"{name}: {row.not_contacted:,} not contacted, {row.control:,} control group, "
        f"{row.sendable:,} sendable, of {row.clients:,} clients"
    )
    note = ""
    if not reconciles(row):
        note = '<div class="pan-flow-note">These figures do not add up for this run.</div>'
    reveal_cls = " is-revealing" if reveal else ""
    return (
        f'<section class="pan-flow{reveal_cls}" aria-label="Where this segment\'s clients go">'
        f'<div class="pan-flow-head"><span class="pan-flow-title {seg_class}">{marker}'
        f"<span>{html.escape(name)}</span></span>"
        f'<span class="pan-flow-total"><strong>{row.clients:,}</strong> clients</span></div>'
        f'<div class="pan-flow-bar" role="img" aria-label="{html.escape(label, quote=True)}">'
        f'{"".join(segs)}</div>'
        f'<div class="pan-flow-legend">{"".join(legend)}</div>{note}</section>'
    )


def whatif_change_html(
    label: str,
    number: str,
    now_label: str,
    *,
    base_number: str | None = None,
    base_label: str | None = None,
    prev: str | None = None,
    forecast: float | None = None,
    base_forecast: float | None = None,
) -> str:
    """What-If headline (Part 9): the number as run, at this threshold, and
    the change, as plain figures. With no baseline, or at the run's own
    threshold, only the current figure shows. Round 2 (Requirement 20): the
    figures are whole numbers with the forecast in brackets, and the change
    is the difference of the two whole numbers shown.
    """
    from webapp_core.number_format import forecast_text

    def fc(value: float | None) -> str:
        if value is None:
            return ""
        return f' <span class="pan-jp-fc">({html.escape(forecast_text(value))})</span>'
    def fig(k: str, v_html: str, cls: str = "", *, key_below: bool = False) -> str:
        key = f'<span class="pan-wi-k">{html.escape(k)}</span>'
        val = f'<span class="pan-wi-v">{v_html}</span>'
        return f'<div class="pan-wi-fig{cls}">{val + key if key_below else key + val}</div>'

    now_html = _kpi_number_html(number, prev) + fc(forecast)
    if base_number is None or base_label is None or base_label == now_label:
        # One figure: the number leads and the threshold is one muted line
        # under it (the slider already shows the amount).
        suffix = " (as run)" if base_label == now_label and base_label is not None else ""
        figs = fig(f"At {now_label}{suffix}", now_html, " is-now", key_below=True)
    else:
        try:
            delta = float(str(number).replace(",", "")) - float(str(base_number).replace(",", ""))
            delta_text = _delta_text(delta)
        except ValueError:
            delta_text = ""
        figs = fig(f"As Run, At {base_label}", html.escape(str(base_number)) + fc(base_forecast))
        figs += fig(f"At {now_label}", now_html, " is-now")
        if delta_text:
            figs += fig("Change", delta_text, " is-delta")
    return (
        '<section class="pan-wi" aria-label="Expected joiners at this threshold">'
        f'<div class="pan-wi-title">{html.escape(label)}</div>'
        f'<div class="pan-wi-figs">{figs}</div></section>'
    )


def thinking_html(text: str = "Thinking") -> str:
    """The Ask Assistant waiting line: text and three pulsing dots (Part 9)."""
    return (
        f'<div class="pan-thinking" role="status">{html.escape(text)}'
        '<span class="pan-thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span>'
        "</div>"
    )


def nav_state_html(*, has_run: bool, has_personas: bool) -> str:
    """A hidden marker the stepper CSS reads to show each step's state."""
    classes = ["pan-nav-state", "has-run" if has_run else "no-run"]
    if has_personas:
        classes.append("has-personas")
    return f'<div class="{" ".join(classes)}" aria-hidden="true"></div>'


def hero_text_html(title: str, subtitle: str) -> str:
    """Return the HTML for the hero's left column: big title + one-line sub."""
    return (
        '<div class="pan-hero-text">'
        f'<div class="pan-hero-title">{html.escape(title)}</div>'
        f'<div class="pan-hero-sub">{html.escape(subtitle)}</div>'
        "</div>"
    )


# --- metric_panel kept as a thin compatibility wrapper over the KPI panel ---
def metric_panel(number: str, caption: str, *, prev: str | None = None) -> None:
    """Render the headline KPI as the red-gradient hero panel.

    Retained for callers that show the standalone headline number (e.g. the
    WHAT-IF tab). Renders the same red-gradient KPI block used in the hero.
    ``prev`` turns on the Part 8 number roll (see :func:`hero_kpi_html`).
    """
    st_markdown(hero_kpi_html(number, caption, prev=prev))


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


REVEAL_MAX_INDEX = 5  # items after the sixth start with the sixth (Req 17.4)


def card(
    heading: str,
    body_html: str,
    *,
    reveal_index: int | None = None,
    xfade: bool | str = False,
    recommended: bool = False,
) -> None:
    """Render a surface card: marker (for segments), heading, divider, body.

    Part 8: ``reveal_index`` (0-based) adds the one-shot Results_Reveal rise
    with its stagger slot capped at :data:`REVEAL_MAX_INDEX` (F8); ``xfade``
    ("a" or "b", alternating per group change so back-to-back changes each
    replay) adds the one-shot Group_Change_Crossfade. With neither, the markup
    is unchanged.
    """
    marker, seg_class = segment_marker_html(heading)
    extra, style = "", ""
    el = counting_el()
    if reveal_index is not None:
        extra = f" p8-reveal{_gen_class()}"
        slot = min(max(int(reveal_index), 0), REVEAL_MAX_INDEX)
        style = f' style="--i:{slot}"' if el is None else f' style="--i:{slot};--p8-el:{el:.3f}s"'
    elif xfade:
        variant = xfade if xfade in ("a", "b") else "a"
        extra = f" p8-xfade p8-xfade-{variant}"
    else:
        extra, sw_style = swoop_attrs(heading, body_html)
        style = f' style="{sw_style}"' if sw_style else ""
    tag = act_first_tag_html() if recommended else ""
    # Round 3: "NEW-001 · Ready Toppers" keeps its text, but the promo id is
    # set small and muted so the segment name leads.
    pre, sep, rest = heading.partition(" · ")
    if sep and rest:
        title_html = (
            f'<span><span class="pan-card-pre">{html.escape(pre)} ·</span> '
            f"{html.escape(rest)}</span>"
        )
    else:
        title_html = f"<span>{html.escape(heading)}</span>"
    st_markdown(
        f'<div class="pan-card {seg_class}{extra}"{style}>'
        f'<div class="pan-card-heading">{marker}{title_html}{tag}</div>'
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
    text_cls, text_style = swoop_attrs(title, body_html)
    style = f' style="{text_style}"' if text_style else ""
    st_markdown(
        f'<div class="pan-tile {kind} {seg_class}{text_cls}"{style}>'
        f'<div class="pan-tile-title">{marker}{html.escape(title)}</div>'
        f"{body_html}</div>"
    )


# --- Part 9: the Results grid as one labelled 2x2 (score by capacity) ---
GRID_AXIS_LABELS = {
    "score high": "High Score",
    "score low": "Low Score",
    "capacity low": "Low Capacity",
    "capacity high": "High Capacity",
}
ACT_FIRST = "Act first"


def act_first_tag_html() -> str:
    """The small tag that marks the recommended segment (Part 9)."""
    return f'<span class="pan-act">{ACT_FIRST}</span>'


def tile_html(title: str, body_html: str, *, recommended: bool = False) -> str:
    """One grid tile: a flat surface, its segment marker, and the numbers.

    Every tile looks the same except the recommended one, which gets a
    primary edge and the "Act first" tag (Part 9). Colour lives only in the
    marker, which also differs by shape.
    """
    marker, seg_class = segment_marker_html(title)
    text_cls, text_style = swoop_attrs(title, body_html)
    style = f' style="{text_style}"' if text_style else ""
    rec_cls = " is-recommended" if recommended else ""
    tag = act_first_tag_html() if recommended else ""
    return (
        f'<div class="pan-tile {seg_class}{rec_cls}{text_cls}"{style}>'
        f'<div class="pan-tile-title">{marker}<span>{html.escape(title)}</span>{tag}</div>'
        f"{body_html}</div>"
    )


def results_grid_html(rows, recommended: set[str] | frozenset[str] = frozenset()) -> str:
    """The 2x2 Results grid with its axes labelled (Part 9).

    ``rows`` is ``[(row_label, [(col_label, segment, body_html), ...]), ...]``
    in display order (top row first); labels are keys of
    :data:`GRID_AXIS_LABELS`. Column labels come from the first row.
    """
    if not rows:
        return ""
    head = '<div class="pan-grid-corner" aria-hidden="true"></div>' + "".join(
        f'<div class="pan-grid-col">{html.escape(GRID_AXIS_LABELS.get(c, c))}</div>'
        for c, _seg, _body in rows[0][1]
    )
    body = ""
    for row_label, cols in rows:
        body += (
            '<div class="pan-grid-row">'
            f"<span>{html.escape(GRID_AXIS_LABELS.get(row_label, row_label))}</span></div>"
        )
        for _col, segment, tile_body in cols:
            body += tile_html(segment, tile_body, recommended=segment in recommended)
    return (
        '<div class="pan-grid" role="group" aria-label="Results grid: score by capacity">'
        f"{head}{body}</div>"
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
    text_cls, text_style = text_in_attrs()
    style = f' style="{text_style}"' if text_style else ""
    return (
        f'<div class="pan-banner{_kind_class("pan-banner", kind)}{text_cls}"{style} role="status">'
        f"{html.escape(text)}</div>"
    )


_ABOUT_RE = re.compile(r"^(About) (\d[\d,]*(?:\.\d+)?) (.+)$")


def _stat_parts(label: str) -> tuple[str, str] | None:
    """Split a stat label into (key, value) for the label-over-number layout.

    "Likely Range: 75 To 99" -> ("Likely Range", "75 To 99"); "About 87 Likely
    To Join" -> ("Likely To Join", "About 87"). The words are unchanged.
    """
    m = _ABOUT_RE.match(label)
    if m:
        return m.group(3), f"{m.group(1)} {m.group(2)}"
    key, sep, value = label.partition(": ")
    if sep and key and value:
        return key, value
    return None


def _stat_inner_html(label: str) -> str:
    parts = _stat_parts(label)
    if parts is None:
        return count_text_html(label)
    key, value = parts
    if value.startswith("About "):
        value_html = '<span class="pan-stat-pre">About</span> ' + count_text_html(value[6:])
    else:
        value_html = count_text_html(value)
    return (
        f'<span class="pan-stat-k">{html.escape(key)}</span>'
        f'<span class="pan-stat-v">{value_html}</span>'
    )


def tooltip_html(label: str, tip: str, display_html: str | None = None) -> str:
    """Return ``label`` with one hover/focus tooltip (the styled one only).

    No native ``title``: it drew a second box. The tip text is the focusable
    span's accessible description, so keyboard and screen-reader users still
    get it. Numbers in ``label`` count up inside :func:`counting`.
    """
    return (
        f'<span class="pan-tip" tabindex="0" aria-label="{html.escape(label + ". " + tip, quote=True)}">'
        f"{count_text_html(label) if display_html is None else display_html}"
        f'<span class="pan-tip-text" aria-hidden="true">{html.escape(tip)}</span></span>'
    )


def stat_tile_html(label: str, tip: str = "") -> str:
    """Return one stat tile; the tooltip is attached when ``tip`` is given."""
    display = _stat_inner_html(label)
    inner = tooltip_html(label, tip, display) if tip else display
    kv = " pan-stat--kv" if _stat_parts(label) else ""
    return f'<div class="pan-stat{kv}">{inner}</div>'


def stat_tiles_html(tiles: list[str]) -> str:
    """Wrap already-built stat tiles in a wrapping row."""
    return f'<div class="pan-stats">{"".join(tiles)}</div>'


def unavailable_line_html(label: str) -> str:
    """A bar row with no bar (round 3): Unavailable must not read as 0."""
    return (
        '<div class="pan-bar is-unavailable">'
        f'<span class="pan-bar-label">{html.escape(label)}</span></div>'
    )


def fields_row_html(rows: list[tuple[str, str]]) -> str:
    """Label/value pairs in one wrapping row (round 3, Past Promos facts)."""
    return f'<div class="pan-fields-row">{fields_html(rows)}</div>'


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
    ]
    # Part 9: the reasons and the exclusions sit behind one disclosure, so
    # the card leads with what to do (action, channel, angle).
    details = (
        '<details class="pan-details"><summary>Targeting Details</summary>'
        + fields_html([(view.why_heading, drivers), (view.not_contacted_heading, exclusions)])
        + "</details>"
    )
    persona = persona_section_html(view.persona_lines)
    return stats + fields_html(rows) + details + persona + extra_html


def decision_card_split_body_html(view, extra_html: str = "") -> str:
    """A full-width card body in two columns (Part 9): what to do on the left
    (stats, action, channel, angle, details), who joins on the right (the
    persona breakdown). Used when one card has the whole section to itself.
    """
    persona = persona_section_html(view.persona_lines)
    if not persona:
        return decision_card_body_html(view, extra_html)
    plain = dataclasses.replace(view, persona_lines=None)
    return (
        '<div class="pan-card-split">'
        f'<div class="pan-card-split-main">{decision_card_body_html(plain, extra_html)}</div>'
        f'<div class="pan-card-split-side">{persona}</div>'
        "</div>"
    )


# --- loading: shown only on a real wait ---

_LOADER_SUBTEXT = {
    "suggest": "Comparing how distinct 2 to 6 personas would be.",
    "analysis": "This can take a moment.",
    "rescore": "Updating the results for the new threshold.",
    "personas": "This can take a moment for larger audiences.",
}


# "Suggest a number" motif: 20 small red and gold dots whooshing round little
# orbits with cartoon speed lines. (orbit centre x, radius, lap factor, phase,
# direction) per dot; the finish reads the same table, so the server-side
# fallback start positions match the running loader.
_SG_DOTS = tuple(
    (cx, r, f, ph, d)
    for cx, r, f, ph, d in (
        (-78, 16, 0.72, 0.05, 1), (-62, 30, 0.95, 0.40, -1), (-44, 20, 0.80, 0.71, 1),
        (-30, 36, 1.10, 0.18, -1), (-14, 14, 0.68, 0.55, 1), (0, 26, 0.88, 0.90, -1),
        (12, 40, 1.15, 0.33, 1), (28, 18, 0.76, 0.62, -1), (44, 32, 1.02, 0.08, 1),
        (60, 22, 0.84, 0.47, -1), (76, 14, 0.70, 0.83, 1), (-70, 40, 1.20, 0.27, 1),
        (-50, 12, 0.66, 0.95, -1), (-22, 24, 0.90, 0.12, 1), (6, 34, 1.06, 0.68, -1),
        (22, 12, 0.64, 0.37, 1), (38, 26, 0.92, 0.79, -1), (54, 38, 1.18, 0.22, 1),
        (70, 30, 0.98, 0.58, -1), (-4, 18, 0.78, 0.44, 1),
    )
)


def _suggest_visual() -> str:
    dots = []
    for i, (cx, r, f, ph, d) in enumerate(_SG_DOTS):
        colour = "gold" if i % 2 else "red"
        dots.append(
            f'<span class="pan-sg-orbit{" rev" if d < 0 else ""}" '
            f'style="--cx:{cx}px;--r:{r}px;--f:{f};--ph:{ph}">'
            f'<span class="pan-sg-dot {colour}"></span></span>'
        )
    return f'<div class="pan-sg" aria-hidden="true">{"".join(dots)}</div>'


def _loader_visual(kind: str) -> str:
    if kind == "suggest":
        return _suggest_visual()
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


def _trace_html(state: str, phase: float = 0.0) -> str:
    """The line that travels around the loader card (Part 8 polish, fix 4).

    ``running`` loops until the Job ends; ``done`` grows from the line's
    current position (``phase``, a fraction of one lap) to the full border,
    then the finishing overlay fades. Decorative: ``aria-hidden``.
    """
    try:
        ph = float(phase)
    except (TypeError, ValueError):
        ph = 0.0
    ph = ph % 1.0 if ph == ph and ph not in (float("inf"), float("-inf")) else 0.0
    return (
        f'<svg class="pan-trace pan-trace--{state}" style="--p8-phase:{ph:.4f}" '
        'aria-hidden="true" focusable="false" preserveAspectRatio="none">'
        '<rect class="pan-trace-line" pathLength="100"/></svg>'
    )


def loader_html(
    kind: str,
    message: str,
    *,
    slow: bool = False,
    status: str = "",
    trace: str = "running",
    phase: float = 0.0,
) -> str:
    """Return the loader overlay markup.

    ``kind`` is ``"analysis"`` / ``"rescore"`` (documents under a magnifier) or
    ``"personas"`` (boxes settling into groups). The overlay is fixed in the
    viewport, so showing it never moves the page, and the stylesheet keeps it
    invisible for a short delay (longer when ``slow``) so a fast or cached run
    never flashes it. There is no progress bar: the wait length is unknown.

    ``status`` is the live stage line (the former toast wording), announced
    politely; :meth:`LoaderHandle.status` swaps it in place, so the loader's
    animations keep running. A line travels around the card (``trace``).
    """
    delay_class = " pan-loading--slow" if slow else ""
    sub = _LOADER_SUBTEXT.get(kind, "")
    sub_html = f'<div class="pan-loading-sub">{html.escape(sub)}</div>' if sub else ""
    return (
        f'<div class="pan-loading{delay_class}" aria-busy="true">'
        '<div class="pan-loading-card">'
        f"{_trace_html(trace, phase)}"
        f"{_loader_visual(kind)}"
        f'<div class="pan-loading-msg">{html.escape(message)}</div>'
        f"{sub_html}"
        '<div class="pan-loading-status" role="status" aria-live="polite">'
        f"{html.escape(status)}</div>"
        '<div class="pan-skel" aria-hidden="true"><span></span><span></span><span></span></div>'
        "</div></div>"
    )


class LoaderHandle:
    """Handle yielded by :func:`loading`.

    ``keep()`` leaves the overlay up: on a successful Job the overlay stays in
    place through ``st.rerun()``, so there is never a frame without an
    overlay; the completion render then draws the finishing overlay above it,
    which fades out (design section l, Requirement 22.16).

    ``status(text)`` updates the live stage line. The markup keeps the same
    structure, so Streamlit patches only the text and every loader animation
    (motif, skeleton, trace) keeps running.
    """

    def __init__(self, slot, kind: str = "", message: str = "", slow: bool = False) -> None:
        self.slot = slot
        self.kept = False
        self._kind, self._message, self._slow = kind, message, slow

    def keep(self) -> None:
        self.kept = True

    def status(self, text: str) -> None:
        self.slot.markdown(
            loader_html(self._kind, self._message, slow=self._slow, status=text),
            unsafe_allow_html=True,
        )


@contextmanager
def loading(kind: str, message: str, *, slow: bool = False, status: str = "", slot=None):
    """Show the loader while the ``with`` body runs, then remove it.

    Drop-in replacement for ``st.spinner``: it only wraps the existing call and
    changes no computation or caching. Yields a :class:`LoaderHandle`; a body
    that calls ``handle.keep()`` and ends without an exception leaves the
    overlay in place (cleared by the next run). Any exception clears it.
    ``status`` is the first live stage line.

    Part 9: ``slot`` is an ``st.empty()`` the page draws on every render (the
    loader only fills it), so starting a job adds no element to the page and
    nothing after it shifts. Without one a new slot is made here, as before.
    """
    import streamlit as st

    if slot is None:
        slot = st.empty()
    slot.markdown(loader_html(kind, message, slow=slow, status=status), unsafe_allow_html=True)
    handle = LoaderHandle(slot, kind, message, slow)
    try:
        yield handle
    except BaseException:
        slot.empty()
        raise
    else:
        if not handle.kept:
            slot.empty()


# --- Part 8: finishing overlay (F3, design section l) ---

LOADER_MESSAGES = {
    "suggest": "Finding a good number of personas...",
    "rescore": "Rescoring at the new threshold...",
    "analysis": "Scoring and segmenting your audience...",
    "personas": "Grouping leads into personas...",
}


# Finishing stories (Part 8 polish). Both run on --pan-dur-finish, exactly as
# long as the trace takes to fill the border, so the fireworks, the end of the
# story and the headline land together. The overlay is drawn over the still
# running loader; app/static/page_lock.js copies the live positions (trace,
# document strip, magnifier, tiles) into the start frame, so nothing jumps.
# The values computed here are only the fallback when that script is absent.
FINISH_HEADLINES = {"analysis": "Promo Analyzed", "personas": "Personas Built",
                    "suggest": "Number Suggested", "rescore": "Promo Rescored"}
_DOC_PITCH = 84.0     # .pan-docs: --doc-w 56px + --doc-gap 28px
_DOC_LAP_S = 1.6      # pan-docs-slide duration (styles.css section 5)
_DOC_SETTLE = 21.5    # px the strip glides while it stops (speed-matched)
_LENS_X = 112.0       # lens centre: left 50% of the 224px strip
_TILE_BASE = {k: (28 * (i % 4), 28 * (i // 4)) for i, k in enumerate("abcdefgh")}
_TILE_GOLD = ("a", "c", "e", "f")
_TILE_RED = ("b", "d", "g", "h")
_SLOTS_RED = ((3, 2), (27, 2), (3, 26), (27, 26))
_SLOTS_GOLD = ((57, 2), (81, 2), (57, 26), (81, 26))
_BLOB = {"red": (15, 14), "gold": (69, 14)}
# Firework particles around the card: (x, y, outward angle in degrees).
_FIREWORKS = (
    ("0%", "0%", -135), ("100%", "0%", -45), ("100%", "100%", 45), ("0%", "100%", 135),
    ("25%", "0%", -100), ("50%", "0%", -90), ("75%", "0%", -80),
    ("25%", "100%", 100), ("50%", "100%", 90), ("75%", "100%", 80),
    ("0%", "33%", 190), ("0%", "67%", 170), ("100%", "33%", -10), ("100%", "67%", 10),
)
# Owner request: red and gold only.
_FIREWORK_COLOURS = ("--pan-primary", "--pan-gold")
# The fireworks fill the whole ending: three waves back to back, the first
# starting with the ending and the last landing as it ends (styles.css
# section 17). Each wave turns the burst a little so they do not overlap.
_FIREWORK_WAVES = 3
_FIREWORK_WAVE_TURN = 14   # degrees between waves


def _finish_analysis(elapsed: float) -> str:
    """Magnifier story: the strip glides to a stop, the lens slides onto the
    nearest document and zooms in, the others dim, a check draws in the lens."""
    phase = (max(0.0, float(elapsed)) % _DOC_LAP_S) / _DOC_LAP_S
    x0 = -_DOC_PITCH * phase
    x1 = x0 - _DOC_SETTLE
    target = round((_DOC_PITCH - 28 - x1 + (_LENS_X - _DOC_PITCH)) / _DOC_PITCH)
    dx = target * _DOC_PITCH + 28 + x1 - _LENS_X
    docs = "".join(
        f'<span class="pan-doc{" is-target" if i == target else ""}"></span>' for i in range(5)
    )
    return (
        f'<div class="pan-docs is-story" aria-hidden="true" style="--x0:{x0:.1f}px;'
        f'--x1:{x1:.1f}px;--lens-dx:{dx:.1f}px">'
        f'<div class="pan-docs-viewport"><div class="pan-docs-track">{docs}</div></div>'
        '<span class="pan-mag"><svg class="pan-fin-check" viewBox="0 0 32 32" focusable="false">'
        '<path d="M8 16.5 L14 22.5 L24.5 10.5" pathLength="1"/></svg></span></div>'
    )


def _finish_personas() -> str:
    """Tile story: each square hops to a wrong spot, then to its colour, the
    colours smash into one red and one gold blob, and both jump and squish."""
    tiles = []
    for group, keys, slots, other in (
        ("red", _TILE_RED, _SLOTS_RED, _SLOTS_GOLD),
        ("gold", _TILE_GOLD, _SLOTS_GOLD, _SLOTS_RED),
    ):
        for i, k in enumerate(keys):
            bx, by = _TILE_BASE[k]
            (fx, fy), (mx, my), (gx, gy) = slots[i], other[i], _BLOB[group]
            tiles.append(
                f'<span class="pan-pz-tile pan-pz-{k}{" gold" if group == "gold" else ""}" '
                f'style="--x0:0px;--y0:0px;--s0:1;--xm:{mx - bx}px;--ym:{my - by}px;'
                f'--xf:{fx - bx}px;--yf:{fy - by}px;--xb:{gx - bx}px;--yb:{gy - by}px"></span>'
            )
    return f'<div class="pan-pz is-story" aria-hidden="true">{"".join(tiles)}</div>'


def _finish_suggest(elapsed: float) -> str:
    """Dot story: the 20 dots leave their orbits, find their colour, gather,
    then squish together like soft clay into one red and one gold blob (an
    SVG goo filter fuses them as they touch)."""
    import math

    lap = 1.4  # --pan-dur-ring-lap; fallback start only (the page script corrects it)
    parts = []
    counts = {"red": 0, "gold": 0}
    for i, (cx, r, f, ph, d) in enumerate(_SG_DOTS):
        colour = "gold" if i % 2 else "red"
        turn = (ph + max(0.0, float(elapsed)) / (lap * f)) % 1.0
        ang = 2 * math.pi * turn * (1 if d > 0 else -1)
        x0, y0 = cx + r * math.cos(ang), r * math.sin(ang)
        n = counts[colour]
        counts[colour] += 1
        bx = -46 if colour == "red" else 46
        sa = 2 * math.pi * n / 10
        # Tight gathering ring: the colour reads as one mass, never a donut.
        sx, sy = bx + 3 * math.cos(sa), 3 * math.sin(sa)
        parts.append(
            f'<span class="pan-sg-fdot {colour}" style="--x0:{x0:.1f}px;--y0:{y0:.1f}px;'
            f'--xs:{sx:.1f}px;--ys:{sy:.1f}px;--xb:{bx}px;--yb:0px;--i:{i}"></span>'
        )
    goo = (
        '<svg class="pan-sg-defs" aria-hidden="true" focusable="false"><filter id="pan-goo">'
        '<feGaussianBlur in="SourceGraphic" stdDeviation="3.2" result="b"/>'
        '<feColorMatrix in="b" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 20 -8"/>'
        "</filter></svg>"
    )
    return f'{goo}<div class="pan-sg is-story" aria-hidden="true">{"".join(parts)}</div>'


def _fireworks_html() -> str:
    parts = []
    for w in range(_FIREWORK_WAVES):
        for i, (x, y, a) in enumerate(_FIREWORKS):
            # Alternate red and gold, and swap the pattern each wave.
            c = _FIREWORK_COLOURS[(i + w) % len(_FIREWORK_COLOURS)]
            turn = a + (w - 1) * _FIREWORK_WAVE_TURN
            style = f"--x:{x};--y:{y};--a:{turn}deg;--i:{i};--w:{w};--c:var({c})"
            parts.append(f'<span class="pan-fin-spark" style="{style}"></span>')
            parts.append(f'<span class="pan-fin-dot" style="{style}"></span>')
    return f'<span class="pan-fin-sparks" aria-hidden="true">{"".join(parts)}</span>'


def finishing_overlay_html(
    kind: str, phase: float = 0.0, elapsed: float = 0.0, headline: str | None = None,
    uid: int = 0,
) -> str:
    """The loader's finish (Requirement 22.16, Part 8 polish).

    Same scrim and card as :func:`loader_html`, visible at once. The trace
    grows from where the running line was (``phase``, a fraction of one lap)
    around the whole border while the story plays (``elapsed`` is the seconds
    the Job ran, the fallback start of the document strip); when the border
    is full, fireworks burst, the headline ("Promo Analyzed" or "Personas
    Built") has replaced the loading text, and the overlay then fades and lets
    clicks through. It never locks the page (``is-finishing``).
    """
    message = LOADER_MESSAGES.get(kind, "")
    sub = _LOADER_SUBTEXT.get(kind, "")
    sub_html = f'<div class="pan-loading-sub">{html.escape(sub)}</div>' if sub else ""
    if kind == "personas":
        story = _finish_personas()
    elif kind == "suggest":
        story = _finish_suggest(elapsed)
    else:
        story = _finish_analysis(elapsed)
    headline = headline or FINISH_HEADLINES.get(kind, "")
    # Successive endings alternate the outer element (div / section): React
    # then always builds a new element. Reusing the previous ending's element
    # (only its class changes) kept its finished animations, so a second ending
    # in a session never played. "is-held" starts the story frozen until the
    # page script sees the browser free (page_lock.js), so a busy rerun
    # cannot use the ending up unseen.
    tag = "section" if int(uid) % 2 else "div"
    return (
        f'<{tag} class="pan-loading is-finishing is-held pan-fin--{html.escape(kind)}" aria-hidden="true">'
        '<div class="pan-loading-card">'
        f"{_trace_html('done', phase)}"
        f"{_fireworks_html()}"
        f"{story}"
        # The text block keeps the loader's height; the headline is centred
        # in it as the loading text fades out, so the card never resizes.
        '<div class="pan-loading-textblock">'
        f'<div class="pan-loading-msg">{html.escape(message)}</div>'
        f"{sub_html}"
        '<div class="pan-loading-status"></div>'
        '<div class="pan-skel"><span></span><span></span><span></span></div>'
        f'<div class="pan-loading-done">{html.escape(headline)}</div>'
        f"</div></div></{tag}>"
    )


# --- Part 8: toasts and completion stories (F3, Requirements 8, 9) ---

def _story_analysis() -> str:
    """Magnifier story: docs slide in, the lens zooms, lines fade, check draws."""
    def doc(x: int, cls: str) -> str:
        lines = "".join(
            f'<rect x="{x + 4}" y="{y}" width="{w}" height="2" rx="1"/>'
            for y, w in ((21, 14), (26, 12), (31, 14), (36, 9))
        )
        return (
            f'<g class="p8-s-doc {cls}"><rect class="p8-s-paper" x="{x}" y="15" '
            f'width="22" height="30" rx="3"/><g class="p8-s-lines">{lines}</g></g>'
        )

    return (
        '<svg class="p8-story p8-story--analysis" viewBox="0 0 96 64" aria-hidden="true" '
        'focusable="false">'
        f'<g class="p8-s-docs">{doc(6, "p8-s-l")}{doc(37, "p8-s-c")}{doc(68, "p8-s-r")}</g>'
        '<g class="p8-s-lens">'
        '<circle cx="48" cy="30" r="13"/>'
        '<line x1="57.5" y1="39.5" x2="65" y2="47"/>'
        '<path class="p8-s-check" d="M42 30.5 L46.5 35 L54.5 26" pathLength="1"/>'
        "</g></svg>"
    )


# Persona squares: tiles a-h in the loader's 2 x 4 grid and colours (gold for
# a, c, e, f), sliding into a red 2 x 2 cluster (left) and a gold one (right).
_SQ_GRID = {k: (14 + 16 * (i % 4), 18 + 16 * (i // 4)) for i, k in enumerate("abcdefgh")}
_SQ_FINAL = {
    "b": (24, 22), "d": (34, 22), "g": (24, 32), "h": (34, 32),
    "a": (52, 22), "c": (62, 22), "e": (52, 32), "f": (62, 32),
}
# One last shuffle: each tile starts on a neighbour's grid cell.
_SQ_SHUFFLE = {"a": "b", "b": "a", "c": "d", "d": "c", "e": "f", "f": "e", "g": "h", "h": "g"}


def _story_personas(uid: str) -> str:
    """Squares story: last shuffle, slide into two clusters, gooey merge."""
    fid = f"p8-goo-{uid}"

    def tile(k: str) -> str:
        fx, fy = _SQ_FINAL[k]
        gx, gy = _SQ_GRID[k]
        sx, sy = _SQ_GRID[_SQ_SHUFFLE[k]]
        return (
            f'<rect class="p8-s-tile" x="{fx}" y="{fy}" width="10" height="10" rx="2" '
            f'style="--gx:{gx - fx}px;--gy:{gy - fy}px;--sx:{sx - fx}px;--sy:{sy - fy}px"/>'
        )

    red = "".join(tile(k) for k in "bdgh")
    gold = "".join(tile(k) for k in "acef")
    return (
        '<svg class="p8-story p8-story--personas" viewBox="0 0 96 64" aria-hidden="true" '
        'focusable="false">'
        f'<defs><filter id="{fid}" x="-20%" y="-20%" width="140%" height="140%">'
        '<feGaussianBlur in="SourceGraphic" stdDeviation="3" result="b"/>'
        '<feColorMatrix in="b" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 18 -7"/>'
        "</filter></defs>"
        f'<g class="p8-s-red" filter="url(#{fid})">{red}</g>'
        f'<g class="p8-s-gold" filter="url(#{fid})">{gold}</g>'
        "</svg>"
    )


def completion_story_html(job: str, uid: str = "0") -> str:
    """The Completion_Story for ``job`` ("analysis" or "personas")."""
    return _story_personas(uid) if job == "personas" else _story_analysis()


def toast_stack_html(views) -> str:
    """The bottom-right Toast_Stack for a sequence of ``ToastView`` (Req 8).

    Each toast carries ``--p8-el`` (seconds since it appeared; negative while
    a completion toast waits for its entry), so a rerun continues every
    animation where it was instead of replaying it (Requirement 5.7). Text is
    real text from the first frame; the story art is ``aria-hidden``.
    """
    items = []
    for v in views:
        t = v.toast
        uid = re.sub(r"[^a-z0-9]", "", str(t.id).lower()) or "0"
        # Each toast gets its own custom element tag. React keeps an element
        # when the tag at a position is unchanged and only patches attributes,
        # which would let a new toast inherit the previous toast's finished
        # animation clock; a distinct tag per toast makes it a new element.
        tag = f"p8-toast-{uid}"
        evict = " is-evicting" if v.evicting else ""
        art = (
            completion_story_html(t.job, uid)
            if t.kind == "done"
            else '<span class="p8-toast-dot" aria-hidden="true"></span>'
        )
        # (React writes "class" on a custom element as a literal "classname"
        # attribute, so the tag is a bare wrapper; CSS gives it
        # display: contents.)
        items.append(
            f'<{tag}><div class="p8-toast-pos" style="--p8-slot:{int(v.slot)}">'
            f'<div class="p8-toast p8-toast--{t.kind} p8-toast--{t.job}{evict}" '
            f'role="status" aria-live="polite" style="--p8-el:{v.elapsed_s:.3f}s">'
            f'{art}<div class="p8-toast-text">{html.escape(t.text)}</div>'
            f"</div></div></{tag}>"
        )
    return f'<div class="p8-toasts">{"".join(items)}</div>'


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
    wiring in ``app/ui_effects.py``.

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



# --- Part 9 round 3: AI notices, tags, chips, token lines, the wait line ---
# Spec part9-layout-fixes, Requirements 32 to 36 and 39. Fixed words live here
# so every section says the same thing.

AI_NOTICE_BEDROCK = (
    "AI-generated. It can be wrong or incomplete. Check it against your campaign "
    "before you use it. Do not rely on it alone."
)
AI_NOTICE_PREDICTION = (
    "These figures are forecasts from a prediction model. They are estimates, not "
    "promises. Use them to compare options, not as a guarantee."
)
AI_DOES_NOT = (
    "The AI never produces or changes a number: scoring is the prediction model, "
    "and built-in rules take over when the AI is not used."
)
WAIT_LABELS = ("Mining", "Crafting")
# (column + |row - 1|) for the nine pixels, row by row: a chevron that runs
# left to right (multiplied by --pan-pixel-step in CSS).
_PIXEL_STEPS = tuple((i % 3) + abs(i // 3 - 1) for i in range(9))


def ai_chip_html(text: str, *, icon: bool = False, kind: str = "neutral", logo: str = "") -> str:
    """A small chip (mode, model, token counts).

    ``icon`` adds the Bedrock mark (drawn in the chip's text colour);
    ``logo="claude"`` adds the Claude mark in its own colour.
    """
    cls = "pan-ai-chip" + (" has-icon" if icon else "") + (f" is-{kind}" if kind != "neutral" else "")
    mark = f'<i class="pan-ai-logo is-{html.escape(logo)}" aria-hidden="true"></i>' if logo else ""
    return f'<span class="{cls}">{mark}{html.escape(text)}</span>'


_PROVIDERS = {"anthropic": "Anthropic", "amazon": "Amazon", "meta": "Meta",
              "mistral": "Mistral", "cohere": "Cohere", "ai21": "AI21"}
_REGION_PREFIXES = ("global", "us", "eu", "apac", "ap", "ca", "jp", "au")


def model_display(model_id: str) -> tuple[str, str]:
    """``("Anthropic", "Claude Sonnet 5.5")`` from a Bedrock model id.

    Drops the region prefix ("global.", "us."), the version suffix (":0",
    "-v1") and a date stamp; joins number parts with a dot and capitalises the
    words. An id it cannot read comes back as ``("", model_id)``.
    """
    raw = str(model_id or "").strip()
    parts = raw.split(".")
    if len(parts) > 2 and parts[0].lower() in _REGION_PREFIXES:
        parts = parts[1:]
    if len(parts) < 2:
        return "", raw
    provider = _PROVIDERS.get(parts[0].lower(), parts[0].title())
    name = ".".join(parts[1:]).split(":")[0]
    words: list[str] = []
    for tok in name.split("-"):
        if not tok or re.fullmatch(r"v\d+", tok) or re.fullmatch(r"\d{8}", tok):
            continue
        if tok.isdigit() and words and re.fullmatch(r"\d+(\.\d+)*", words[-1]):
            words[-1] += "." + tok
        else:
            words.append(tok if tok.isdigit() else tok[:1].upper() + tok[1:])
    return provider, " ".join(words) or raw


def ai_tag_html(text: str = "AI-generated") -> str:
    """The small tag on every Bedrock output (or "Built-in rules" on a fallback)."""
    cls = "pan-ai-tag" + (" is-builtin" if text != "AI-generated" else "")
    return f'<span class="{cls}">{html.escape(text)}</span>'


def ai_notice_html(
    kind: str, does: str = "", *, powered: bool | None = None,
    model: str = "", demo: bool = False,
) -> str:
    """One section notice: "bedrock" or "prediction" kind, fixed words.

    The Bedrock kind carries the "Powered by Amazon Bedrock" chip and a line
    on what the AI does and does not do (Requirements 32.6, 39.1).
    """
    bedrock = kind == "bedrock"
    words = AI_NOTICE_BEDROCK if bedrock else AI_NOTICE_PREDICTION
    chip = (
        ai_chip_html("Powered by Amazon Bedrock", icon=True, kind="bedrock")
        if (bedrock if powered is None else powered) else ""
    )
    if chip and model:
        # The model sits in its own neutral chip beside "Powered by", in plain
        # words ("Model from Anthropic: Claude Sonnet 5.5"), with the
        # provider's mark when there is one.
        provider, name = model_display(model)
        text = f"Model from {provider}: {name}" if provider else f"Model: {name}"
        chip += ai_chip_html(text, logo="claude" if provider == "Anthropic" else "", kind="model")
    if chip and demo:
        # Keep the session honest: the built-in rules are answering.
        chip += ai_chip_html("Demo Mode", kind="demo")
    extra = ""
    if does:
        extra = f'<div class="pan-ai-notice-does">{html.escape(does)}</div>'
    label = "AI notice" if bedrock else "Forecast notice"
    return (
        f'<div class="pan-ai-notice is-{"bedrock" if bedrock else "prediction"}" role="note" aria-label="{label}">'
        f'<div class="pan-ai-notice-text">{html.escape(words)}</div>{extra}'
        f'{f"<div class=pan-ai-notice-chips>{chip}</div>" if chip else ""}</div>'
    )


def token_line_html(text: str, *, estimate: bool = False) -> str:
    """The token line under an AI output (numbers only)."""
    cls = "pan-token-line" + (" is-estimate" if estimate else "")
    return f'<div class="{cls}">{html.escape(text)}</div>'


def ai_meta_html(tag: str, mode_chip: str, token_text: str) -> str:
    """One row under an AI output: tag, mode chip and token line."""
    return (
        f'<div class="pan-ai-meta">{ai_tag_html(tag)}{mode_chip}'
        f'<span class="pan-token-line">{html.escape(token_text)}</span></div>'
    )


def wait_line_html(estimate_text: str = "", *, start_ms: int | None = None, label: str = "Mining") -> str:
    """The Bedrock wait line: pixel loader, Mining/Crafting label, timer, estimate.

    ``ui_interactions.js`` part 6 swaps the label and ticks the timer from
    ``data-start`` (milliseconds). With Reduced_Motion the grid is still and
    dim, the label stays, and the timer still counts (Requirement 35.6).
    """
    import time as _time

    start = int(_time.time() * 1000) if start_ms is None else int(start_ms)
    pixels = "".join(f'<i style="--d:{d}"></i>' for d in _PIXEL_STEPS)
    # Both words sit in one cell (the box is as wide as the longer one, so the
    # timer never shifts); the page script slides one out and the other in.
    names = list(WAIT_LABELS) if label in WAIT_LABELS else [label, *WAIT_LABELS]
    words = "".join(
        f'<span class="pan-wait-word{" is-on" if name == label else ""}">{html.escape(name)}</span>'
        for name in names
    )
    est = f'<span class="pan-wait-sep">|</span><span class="pan-wait-est">{html.escape(estimate_text)}</span>' if estimate_text else ""
    return (
        f'<div class="pan-wait" role="status" aria-live="polite" data-start="{start}">'
        f'<span class="pan-wait-grid" aria-hidden="true">{pixels}</span>'
        f'<span class="pan-wait-label">{words}</span>'
        '<span class="pan-wait-time">0.0s</span>'
        f"{est}</div>"
    )


def user_bubble_html(text: str) -> str:
    """A question in the transcript: a bubble on the right (chat layout)."""
    return (
        '<div class="pan-chat-user" role="group" aria-label="You">'
        f'<div class="pan-chat-bubble">{html.escape(text)}</div></div>'
    )


def assistant_header_html(name: str, logo: str = "") -> str:
    """The name line above a reply: the model's mark, then its name."""
    mark = f'<i class="pan-ai-logo is-{html.escape(logo)}" aria-hidden="true"></i>' if logo else ""
    return f'<div class="pan-chat-who">{mark}<span>{html.escape(name)}</span></div>'

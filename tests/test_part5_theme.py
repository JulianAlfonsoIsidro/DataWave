"""Example/edge unit tests for the webapp Theme (restyled to the BPI website).

These cover concrete behaviors of ``app.theme`` and its siblings
``.streamlit/config.toml`` and ``app/styles.css``:

- the ``[theme]`` block of ``.streamlit/config.toml`` parses and carries the
  sampled palette colors (its ``primaryColor``/``textColor``/``backgroundColor``
  match the ``PALETTE`` dict),
- the single injected CSS block (:func:`app.theme.build_css`) is loaded from the
  one stylesheet ``app/styles.css`` and contains every sampled palette color,
  imports the Poppins web font, and hides the default Streamlit chrome,
- :func:`app.theme.nav_bar` / :func:`app.theme.header` render the
  "Promo Audience Navigator" text title with no image tag, and
- the nav items are Title Case (not uppercase).

These are concrete example tests, not Hypothesis properties. ``app`` is a
package at the repo root (not under ``src``), so the repo root is placed on
``sys.path`` below in case the test runner has not already added it.
"""

from __future__ import annotations

import sys
import tomllib
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import theme  # noqa: E402

CONFIG_PATH = REPO_ROOT / ".streamlit" / "config.toml"
STYLES_PATH = REPO_ROOT / "app" / "styles.css"


def test_config_toml_parses_and_carries_palette_colors():
    """``.streamlit/config.toml`` parses and carries the sampled base colors.

    The ``[theme]`` block's ``primaryColor``, ``textColor``, and
    ``backgroundColor`` equal the palette's primary-red, dark-charcoal, and
    white hexes so the native Streamlit widgets match the stylesheet.
    """
    raw = CONFIG_PATH.read_text(encoding="utf-8")
    parsed = tomllib.loads(raw)

    theme_block = parsed["theme"]
    assert theme_block["primaryColor"].upper() == theme.PALETTE["PRIMARY_RED"].upper()
    assert theme_block["textColor"].upper() == theme.PALETTE["TEXT_DARK"].upper()
    assert (
        theme_block["backgroundColor"].upper()
        == theme.PALETTE["PANEL_WHITE"].upper()
    )


def test_single_stylesheet_exists_and_build_css_loads_it():
    """``build_css`` wraps the one ``app/styles.css`` file in a style tag."""
    assert STYLES_PATH.exists(), "the single stylesheet app/styles.css must exist"
    css = theme.build_css()
    assert css.strip().startswith("<style>")
    assert css.strip().endswith("</style>")
    # It is the styles.css content, not an inline block.
    assert "Promo Audience Navigator - BPI website style" in css


def test_build_css_contains_every_palette_color():
    """The injected CSS block contains all sampled palette colors."""
    css = theme.build_css()
    for key, hex_value in theme.PALETTE.items():
        assert hex_value.upper() in css.upper(), f"CSS missing {key} ({hex_value})"


def test_build_css_imports_poppins_and_hides_streamlit_chrome():
    """The stylesheet imports Poppins and hides the default Streamlit chrome."""
    css = theme.build_css()
    assert "Poppins" in css
    assert "fonts.googleapis.com" in css
    # Default header/menu/footer/sidebar hidden.
    assert 'data-testid="stHeader"' in css
    assert "#MainMenu" in css
    assert "footer" in css
    assert 'data-testid="stSidebar"' in css


def test_build_css_uses_red_gradient():
    """Buttons and hero use a red gradient from deep to bright red."""
    css = theme.build_css()
    assert "linear-gradient" in css
    assert theme.PALETTE["PRIMARY_RED"].upper() in css.upper()
    assert theme.PALETTE["RED_BRIGHT"].upper() in css.upper()


def _capture_single_markdown(monkeypatch, render, **kwargs) -> str:
    """Call a theme render helper with a fake ``streamlit`` and return the HTML."""
    captured: list[str] = []
    fake_st = types.SimpleNamespace(
        markdown=lambda html, **kw: captured.append(html)
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    render(**kwargs)
    assert len(captured) == 1, "helper should emit exactly one markdown block"
    return captured[0]


def test_nav_bar_renders_text_brand_with_no_image(monkeypatch):
    """``nav_bar`` renders the text title brand and emits no image tag."""
    html = _capture_single_markdown(monkeypatch, theme.nav_bar)
    assert "Promo Audience Navigator" in html
    assert theme.APP_TITLE == "Promo Audience Navigator"
    assert "<img" not in html.lower()


def test_header_alias_renders_text_title_with_no_image(monkeypatch):
    """The backwards-compatible ``header`` renders the title, no image."""
    html = _capture_single_markdown(monkeypatch, theme.header)
    assert "Promo Audience Navigator" in html
    assert "<img" not in html.lower()


def test_nav_items_are_title_case_not_uppercase():
    """Nav items are Title Case (e.g. "New Promo"), not uppercase."""
    assert theme.NAV_ITEMS == ["New Promo", "Results", "Past Promos"]
    for item in theme.NAV_ITEMS:
        assert item != item.upper(), f"{item!r} should be Title Case, not uppercase"


def test_header_escapes_custom_title_and_stays_image_free(monkeypatch):
    """A custom title is rendered (HTML-escaped) and still carries no image."""
    html = _capture_single_markdown(
        monkeypatch, theme.nav_bar, title="A & B <promo>"
    )
    assert "A &amp; B &lt;promo&gt;" in html
    assert "<img" not in html.lower()

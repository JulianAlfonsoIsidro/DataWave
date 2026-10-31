"""Example/edge unit tests for the webapp Theme (Requirements 2.1, 2.2).

These cover three concrete behaviors of ``app.theme`` and its sibling
``.streamlit/config.toml``:

- the ``[theme]`` block of ``.streamlit/config.toml`` parses and carries the
  sampled palette colors -- its ``primaryColor``/``textColor`` match the
  ``PALETTE`` dict, and the gold accent hex (recorded as a comment in the file)
  is present in the raw config text (Requirement 2.1),
- the single injected CSS block (:func:`app.theme.build_css`) contains every
  sampled palette color (Requirement 2.1), and
- :func:`app.theme.header` renders the "Promo Audience Navigator" text title
  with no image tag (Requirement 2.2).

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


def test_config_toml_parses_and_carries_palette_colors():
    """``.streamlit/config.toml`` parses and carries the sampled colors.

    The ``[theme]`` block's ``primaryColor`` and ``textColor`` equal the
    palette's primary-red and dark-text hexes, and the gold accent hex appears
    in the raw file (it is recorded there as a comment). (Requirement 2.1)
    """
    raw = CONFIG_PATH.read_text(encoding="utf-8")
    parsed = tomllib.loads(raw)

    theme_block = parsed["theme"]
    # Hex colors are compared case-insensitively.
    assert theme_block["primaryColor"].upper() == theme.PALETTE["PRIMARY_RED"].upper()
    assert theme_block["textColor"].upper() == theme.PALETTE["TEXT_DARK"].upper()
    assert (
        theme_block["backgroundColor"].upper()
        == theme.PALETTE["PANEL_WHITE"].upper()
    )

    # The gold accent is carried in config.toml as a comment, so assert it is
    # present in the raw file text (Requirement 2.1 keeps the two in sync).
    assert theme.PALETTE["ACCENT_GOLD"].upper() in raw.upper()


def test_build_css_contains_every_palette_color():
    """The injected CSS block contains all four sampled palette colors.

    (Requirement 2.1 -- the single CSS block is defined from the palette.)
    """
    css = theme.build_css()
    for key, hex_value in theme.PALETTE.items():
        assert hex_value in css, f"CSS missing {key} ({hex_value})"


def test_build_css_contains_primary_and_accent_colors():
    """The injected CSS carries the primary red and gold accent explicitly."""
    css = theme.build_css()
    assert theme.PALETTE["PRIMARY_RED"] in css
    assert theme.PALETTE["ACCENT_GOLD"] in css


def _capture_header_html(monkeypatch, **header_kwargs) -> str:
    """Call :func:`app.theme.header` with a fake ``streamlit`` and return HTML.

    ``app.theme`` imports ``streamlit`` lazily inside each helper, so inserting
    a stand-in module into ``sys.modules`` lets us capture the HTML passed to
    ``st.markdown`` without a running Streamlit server.
    """
    captured: list[str] = []
    fake_st = types.SimpleNamespace(
        markdown=lambda html, **kwargs: captured.append(html)
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    theme.header(**header_kwargs)

    assert len(captured) == 1, "header() should emit exactly one markdown block"
    return captured[0]


def test_header_renders_text_title_with_no_image(monkeypatch):
    """``header()`` renders the title text and emits no image tag.

    The title is text only -- no logo image (Requirement 2.2).
    """
    html = _capture_header_html(monkeypatch)

    assert "Promo Audience Navigator" in html
    assert theme.APP_TITLE == "Promo Audience Navigator"
    # Text title only: no image element in any casing.
    assert "<img" not in html.lower()


def test_header_escapes_custom_title_and_stays_image_free(monkeypatch):
    """A custom title is rendered (HTML-escaped) and still carries no image."""
    html = _capture_header_html(monkeypatch, title="A & B <promo>")

    assert "A &amp; B &lt;promo&gt;" in html
    assert "<img" not in html.lower()

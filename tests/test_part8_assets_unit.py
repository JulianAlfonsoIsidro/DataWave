"""Static asset, sprite, header and reveal-markup checks (Part 8).

Covers tasks 2.2, 7.5, 8.6 and 9.9 (example tests).
Validates: Requirements 6.6, 6.9, 13.14, 16.3, 16.4, 16.8, 16.12, 17.4, 17.8, 19.4, 19.5
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import theme  # noqa: E402
from webapp_core.group_picker_items import UNKNOWN_ART, VALUE_ART, YES_NO_ART  # noqa: E402

PICKER = ROOT / "app" / "static" / "group_picker"
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _symbol_ids() -> set[str]:
    return set(re.findall(r'<symbol id="([^"]+)"', (PICKER / "illustrations.svg").read_text(encoding="utf-8")))


def test_sprite_covers_every_category_value_and_yes_no_icon():
    ids = _symbol_ids()
    for column, values in VALUE_ART.items():
        for value, art in values.items():
            assert art in ids, f"{column}={value} has no sprite {art}"
    assert set(YES_NO_ART.values()) <= ids
    assert len(set(YES_NO_ART.values())) == 8
    assert {"yn-check", "yn-cross", UNKNOWN_ART} <= ids


def test_sprite_has_no_hex_and_no_dollar_sign():
    text = (PICKER / "illustrations.svg").read_text(encoding="utf-8")
    assert not _HEX.findall(text)
    assert "$" not in text
    assert "linearGradient" not in text and "<image" not in text


def test_region_svg_has_four_areas_licence_and_size_limit():
    svg = (PICKER / "ph_regions.svg").read_text(encoding="utf-8")
    assert re.findall(r'data-area="([^"]+)"', svg) == ["NCR", "Luzon", "Visayas", "Mindanao"]
    assert 'class="bubble"' in svg and 'class="leader"' in svg
    assert (PICKER / "ph_regions.svg").stat().st_size <= 150 * 1024
    assert not _HEX.findall(svg)
    assert "https://" not in svg and "http://" not in svg.replace("http://www.w3.org/2000/svg", "")
    licence = (PICKER / "LICENSE-ph-regions.txt").read_text(encoding="utf-8")
    assert "v1.1.1" in licence and "MIT" in licence and "NAMRIA, PSA via OCHA" in licence


def test_header_lines_removed_from_main_but_kept_in_theme():
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*theme\.(utility_bar|nav_bar)\(", main, re.M)  # no call lines
    assert theme.APP_TITLE == "Promo Audience Manager"
    assert callable(theme.nav_bar) and callable(theme.header)


def _card_html(monkeypatch, **kwargs) -> str:
    captured: list[str] = []
    monkeypatch.setattr(theme, "st_markdown", captured.append)
    theme.card("Persona A", "<p>body</p>", **kwargs)
    return captured[0]


def test_card_reveal_markup(monkeypatch):
    plain = _card_html(monkeypatch)
    assert "p8-" not in plain and _card_html(monkeypatch, reveal_index=None) == plain
    assert 'class="pan-card  p8-reveal" style="--i:2"' in _card_html(monkeypatch, reveal_index=2)
    assert "--i:5" in _card_html(monkeypatch, reveal_index=9)  # capped at the sixth item
    assert "p8-xfade-b" in _card_html(monkeypatch, xfade="b")

"""Token reader, palette mirror and no-literals scan (Part 8).

Feature: part8-new-ui-features, Property 10: The iframe palette equals the stylesheet
Validates: Requirements 2.5, 3.3, 3.5-3.10, 4.2, 12.2, 19.3, 22.1
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import theme  # noqa: E402

STYLES = ROOT / "app" / "styles.css"
STATIC = ROOT / "app" / "static"

_names = st.lists(st.from_regex(r"--t-[a-z]{1,6}", fullmatch=True), min_size=1, max_size=6, unique=True)
_plain = st.from_regex(r"[0-9]{1,3}(px|ms)", fullmatch=True)


@settings(max_examples=100, deadline=None)
@given(names=_names, data=st.data())
def test_property_10_reader_matches_block(tmp_path_factory, names, data):
    """Feature: part8-new-ui-features, Property 10: The iframe palette equals the stylesheet

    **Validates: Requirements 3.5, 3.6, 3.10**
    """
    expected: dict[str, tuple[str, str]] = {}
    lines = []
    for i, name in enumerate(names):
        kind = data.draw(st.sampled_from(["plain", "pair", "ref"]) if i else st.sampled_from(["plain", "pair"]))
        if kind == "plain":
            v = data.draw(_plain)
            lines.append(f"{name}: {v};")
            expected[name] = (v, v)
        elif kind == "pair":
            a, b = data.draw(_plain), data.draw(_plain)
            lines.append(f"{name}: light-dark({a}, {b});")
            expected[name] = (a, b)
        else:
            target = names[data.draw(st.integers(0, i - 1))]
            lines.append(f"{name}: var({target});")
            expected[name] = expected[target]
    css = "/* 1. DESIGN TOKENS */\n:root {\n" + "\n".join(lines) + "\n}\n.x { color: red; }\n"
    path = tmp_path_factory.mktemp("tok") / "styles.css"
    path.write_text(css, encoding="utf-8")
    assert theme.read_tokens(path) == expected


def test_iframe_palette_equals_stylesheet_and_unknown_raises():
    tokens = theme.read_tokens()
    pal = theme.iframe_palette(theme.PICKER_TOKENS)
    for name in theme.PICKER_TOKENS:
        assert (pal["light"][name], pal["dark"][name]) == tokens[name]
    with pytest.raises(theme.TokenError, match="--pan-no-such-token"):
        theme.token_pair("--pan-no-such-token")


def test_palette_mirror_names_the_differing_entry():
    tokens = theme.read_tokens()
    for key, name in theme.PALETTE_TOKENS.items():
        assert theme.PALETTE[key].lower() == tokens[name][0].lower(), f"PALETTE[{key!r}] != {name}"


# --- no-literals scan -------------------------------------------------------

_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_FUNC_COLOUR = re.compile(r"\b(rgba?|hsla?)\(")
_DURATION = re.compile(r"(?<![\w.#-])\d*\.?\d+(ms|s)\b")


def _part8_css() -> str:
    css = STYLES.read_text(encoding="utf-8")
    start = css.index("8. PART 8 SHARED MOTION")
    return re.sub(r"/\*.*?\*/", "", css[start:], flags=re.S)


def _static_files() -> list[Path]:
    files = [STATIC / "p8_page_lock.js"]
    files += [p for p in (STATIC / "group_picker").glob("*") if p.suffix in {".css", ".js", ".html", ".svg"}]
    return files


def test_part8_css_has_no_literal_colours_or_durations():
    css = _part8_css()
    assert not _HEX.findall(css)
    assert not _FUNC_COLOUR.findall(css)
    assert not [m.group(0) for m in _DURATION.finditer(css)]
    # linear timing only on the approved running-ring loop (Requirement 4.2)
    linear_rules = re.findall(r"[^{}]*\{[^{}]*\blinear\b(?!-)[^{}]*\}", css)
    assert all("p8-ring-travel" in r for r in linear_rules)


def test_static_component_files_are_clean():
    for path in _static_files():
        text = re.sub(r"/\*.*?\*/|<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
        if path.name == "picker.js":
            # the theme luminance helper parses colours; it holds none
            text = text.replace("[0-9a-f]", "")
        assert not _HEX.findall(text), path.name
        assert not _FUNC_COLOUR.findall(text), path.name
        assert "http://" not in text.replace("http://www.w3.org/2000/svg", ""), path.name
        assert "https://" not in text, path.name
        assert "$" not in text or path.suffix == ".js", path.name


def test_no_streamlit_import_under_webapp_core():
    for path in (ROOT / "src" / "webapp_core").glob("*.py"):
        assert not re.search(r"^\s*(import|from)\s+streamlit", path.read_text(encoding="utf-8"), re.M), path.name


def test_card_and_kpi_markup_unchanged_without_part8_flags():
    import streamlit as st  # noqa: F401  (theme.card renders through st.markdown)

    assert theme.hero_kpi_html("204", "Expected Joiners", prev=None) == theme.hero_kpi_html("204", "Expected Joiners")
    assert "p8-" not in theme.hero_kpi_html("204", "Expected Joiners", prev="204")
    rolled = theme.hero_kpi_html("214", "Expected Joiners", prev="204")
    assert 'class="p8-sr">214<' in rolled and "is-roll" in rolled


def test_toast_markup_has_real_text_and_status_role():
    from webapp_core.toast_queue import Toast, plan_view

    views = plan_view([Toast("t1", "personas", "done", "Personas ready", 10.0, 0.6)], 10.0)
    html = theme.toast_stack_html(views)
    assert 'role="status"' in html and 'aria-live="polite"' in html
    assert ">Personas ready<" in html and 'aria-hidden="true"' in html
    assert not _HEX.findall(html)

"""Bottom padding of the main block clears the fixed "?" button (audit item 1.10)."""
from __future__ import annotations

import re
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import theme  # noqa: E402

_CSS = ROOT / "app" / "styles.css"


def _padding_bottom() -> str:
    text = _CSS.read_text(encoding="utf-8")
    rule = re.search(r"(?m)^\.block-container\s*\{([^}]*)\}", text)
    assert rule, ".block-container rule not found"
    decl = re.search(r"padding-bottom:\s*([^;]+);", rule.group(1))
    assert decl, "padding-bottom missing"
    return decl.group(1).strip()


def _px(name: str, mode: int) -> float:
    return float(theme.read_tokens()[name][mode].removesuffix("px"))


def test_padding_bottom_references_both_tokens():
    value = _padding_bottom()
    assert "--pan-space-5" in value
    assert "--pan-control-h" in value
    assert "#" not in value


def test_padding_bottom_resolved_covers_help_button():
    value = _padding_bottom()
    for mode in (0, 1):
        total = sum(
            _px(name, mode) for name in re.findall(r"var\((--[\w-]+)\)", value)
        )
        assert total >= _px("--pan-space-5", mode) + _px("--pan-control-h", mode)
        assert total == 88

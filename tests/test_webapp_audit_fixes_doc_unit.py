"""Doc check for webapp-audit-fixes item 1.4 (Requirement 2.4)."""
from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "ai-validation-plan.md"


def test_validation_plan_does_not_mention_removed_view() -> None:
    assert "Who Is Being Targeted" not in DOC.read_text(encoding="utf-8")

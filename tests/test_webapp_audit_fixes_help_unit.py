"""Help text describes the real download flow (webapp-audit-fixes item 1.2)."""
from __future__ import annotations

from webapp_core import help_content


def _text(entry) -> str:
    return " ".join(str(p) for p in (entry.question, entry.answer, entry.where))


def _entries():
    return {e.id: e for e in help_content.ENTRIES}


def test_no_entry_mentions_removed_button():
    """**Validates: Requirements 2.2**"""
    for e in help_content.ENTRIES:
        t = _text(e)
        assert "Download Recommended Leads" not in t, e.id
        assert "line under the button" not in t, e.id


def test_markup_pairs_balanced():
    """**Validates: Requirements 3.4**"""
    for e in help_content.ENTRIES:
        t = _text(e)
        assert t.count("[[") == t.count("]]"), e.id


def test_rewritten_entries_describe_real_flow():
    """**Validates: Requirements 2.2**"""
    by_id = _entries()
    for entry_id in ("recommended", "act_first"):
        t = _text(by_id[entry_id])
        for phrase in ("Download Leads", "Choose Leads To Download", "Check Before You Download"):
            assert phrase in t, (entry_id, phrase)
    assert "I Checked These Figures" in _text(by_id["act_first"])

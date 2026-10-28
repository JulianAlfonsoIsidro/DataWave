"""Example/edge-case unit tests for ``part1_optin.leads.Lead_Loader``.

These are concrete-example tests (not Hypothesis) covering the ordered halt
gates and labeling behavior of the Lead_Loader against Requirements
1.1, 1.5, 1.6, 1.7, and 1.8.

Each test writes a small fixture CSV to a pytest ``tmp_path`` and points a
:class:`~part1_optin.config.Config` at it via ``promo_leads_path``. No fixture
or path references a ``*_answer_key*`` file (Requirement 2.14).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from part1_optin.config import Config
from part1_optin.leads import Lead_Loader

# The canonical Promo_Leads_File header in column order:
# promo_id, client_id, control_group, channel_sent, joined, join_date.
HEADER = "promo_id,client_id,control_group,channel_sent,joined,join_date"


def _write_leads(tmp_path: Path, name: str, lines: list[str]) -> Path:
    """Write ``lines`` (newline-joined) to ``tmp_path/name`` and return it."""
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _loader_for(path: Path) -> Lead_Loader:
    """Build a Lead_Loader whose Config points at ``path`` (Requirement 1.1)."""
    return Lead_Loader(Config(promo_leads_path=path))


def test_reads_configured_path_and_labels_valid_frame(tmp_path: Path) -> None:
    """Reads the configured default path and labels a small valid frame.

    Happy path: a small CSV of treated P001/P002/P003 leads with valid 0/1
    ``joined`` values is read from the configured ``promo_leads_path`` and each
    surviving row gets a ``Join_Label`` equal to its ``joined`` value
    (Requirements 1.1, 1.5).
    """
    rows = [
        HEADER,
        "P001,C0001,0,Email,1,2026-07-10",
        "P002,C0002,0,SMS,0,",
        "P003,C0003,0,Push,1,2026-09-20",
    ]
    path = _write_leads(tmp_path, "promo_leads.csv", rows)

    leads = _loader_for(path).load()

    # Every valid treated lead survives.
    assert len(leads) == 3
    # Join_Label mirrors the joined column exactly (Requirement 1.5).
    assert leads["Join_Label"].tolist() == [1, 0, 1]
    # Join_Label is an integer label, not a float/object.
    assert leads["Join_Label"].dtype.kind == "i"
    # The original lead columns are preserved alongside the new label.
    assert {"promo_id", "client_id", "control_group", "joined"}.issubset(
        leads.columns
    )


def test_missing_file_raises_filenotfound_naming_path(tmp_path: Path) -> None:
    """A non-existent Promo_Leads_File raises FileNotFoundError (1.7).

    The run must halt before any downstream work, and the error must name the
    missing path so the operator can locate it.
    """
    missing = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError) as excinfo:
        _loader_for(missing).load()

    # The error names the missing path (Requirement 1.7).
    assert str(missing) in str(excinfo.value)


def test_zero_treated_leads_raises_valueerror(tmp_path: Path) -> None:
    """Zero treated leads after filtering raises a no-treated-leads error (1.8).

    The fixture has only control rows (``control_group == 1``) and
    out-of-set promos, so filtering leaves an empty population. The loader must
    raise ValueError and produce no output.
    """
    rows = [
        HEADER,
        # control_group == 1: a control row, excluded (Requirement 1.2).
        "P001,C0001,1,Email,1,2026-07-10",
        # promo_id not in {P001,P002,P003}: excluded (Requirement 1.3).
        "P999,C0002,0,SMS,0,",
    ]
    path = _write_leads(tmp_path, "promo_leads.csv", rows)

    with pytest.raises(ValueError) as excinfo:
        _loader_for(path).load()

    # The message indicates that no treated leads were found (Requirement 1.8).
    assert "no treated leads" in str(excinfo.value).lower()


def test_row_with_invalid_joined_is_excluded(tmp_path: Path) -> None:
    """A row with a missing or non-0/1 ``joined`` value is excluded (1.6).

    Three treated P001 leads are provided: one with a valid ``joined`` of 1,
    one with a blank (missing) ``joined``, and one with a ``joined`` of 2 that
    is outside {0, 1}. Only the valid row survives.
    """
    rows = [
        HEADER,
        "P001,C0001,0,Email,1,2026-07-10",  # valid -> kept
        "P001,C0002,0,SMS,,",               # missing joined -> excluded
        "P001,C0003,0,Push,2,2026-09-20",   # joined == 2 -> excluded
    ]
    path = _write_leads(tmp_path, "promo_leads.csv", rows)

    leads = _loader_for(path).load()

    # Only the valid-0/1 lead remains (Requirement 1.6).
    assert len(leads) == 1
    assert leads["client_id"].tolist() == ["C0001"]
    assert leads["Join_Label"].tolist() == [1]

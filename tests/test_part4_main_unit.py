"""Example unit tests for the Part4_Cards Reporter and error propagation.

Targeted (non-Hypothesis) tests for :mod:`part4_cards.main`, covering the
Reporter's three outputs and the loader-error halt-without-output guarantee:

- ``outputs/cards.json`` is a JSON list with exactly one Card per (promo,
  segment) Cell (Requirement 6.2).
- Each per-Cell lead CSV is named ``<promo_id>_<segment_slug>.csv`` where the
  slug is the segment lowercased with every run of one or more non-alphanumeric
  characters collapsed to a single underscore (Requirement 6.3).
- Each per-Cell CSV has header ``client_id,best_channel,p_join,control``, one
  row per Sendable_Lead only, with ``control`` always 0 -- no Control or
  Excluded Leads (Requirement 6.4).
- The printed summary has one line per Card carrying the seven fields
  ``promo_id``, ``segment``, ``n_clients``, ``sendable_count``,
  ``expected_joiners``, ``expected_value``, ``action`` (Requirement 6.5).
- A loader error (one input pointed at a non-existent path, the rest valid)
  propagates out of :func:`main` before any output is produced: no ``outputs/``
  directory is created, no file is written, and nothing is printed
  (Requirement 6.6).

A small but complete set of the seven inputs is built in ``tmp_path`` with two
distinct promos, chosen so the Cells exercise exclusions (NDB, over-contacted,
unreachable), a control holdout, and a Cell with zero Sendable_Leads.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from part4_cards.main import _segment_slug, main

# Canonical headers for each of the seven inputs.
SEGMENTS_HEADER = (
    "promo_id,client_id,p_join,capacity_php,segment,top_driver_1,top_driver_2,top_driver_3"
)
SEGMENT_SUMMARY_HEADER = "promo_id,segment,n_clients"
NDB_HEADER = "client_id,flag_type,flag_date"
CONTACT_HISTORY_HEADER = "client_id,contact_date,campaign_id,channel"
CHANNEL_COSTS_HEADER = "channel,cost_php_per_message,source"
CUSTOMER_DNA_HEADER = "client_id,digital_app_user,email_valid,mobile_valid,segment"
PROMO_HISTORY_HEADER = "promo_id,mechanic,channels"

# The seven summary fields printed per Card, in order (Requirement 6.5).
_SUMMARY_FIELDS = 7
# The per-Cell lead CSV columns (Requirement 6.4).
_LEADS_COLUMNS = ["client_id", "best_channel", "p_join", "control"]


def _write(tmp_path: Path, name: str, lines: list[str]) -> Path:
    """Write ``lines`` (newline-joined) to ``tmp_path/name`` and return it."""
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _valid_inputs(tmp_path: Path) -> dict[str, Path]:
    """Write a small valid set of the seven inputs and return their paths.

    Two distinct promos (P001, P002). The Leads are chosen so that across the
    Cells there is at least one of every exclusion reason (ndb, over_contacted,
    no reachable channel), at least one Sendable_Lead, and at least one Cell
    with zero Sendable_Leads -- exercising the Reporter's handling of each.
    """
    segments = _write(
        tmp_path,
        "segments.csv",
        [
            SEGMENTS_HEADER,
            # P001 / Ready Toppers: C0001 sendable (In-app), C0009 NDB-excluded.
            "P001,C0001,0.80,8000,Ready Toppers,payroll,shopping,bills",
            "P001,C0009,0.50,8000,Ready Toppers,bills,payroll,shopping",
            # P001 / Willing but Stretched: C0002 sendable (Email).
            "P001,C0002,0.40,2000,Willing but Stretched,bills,payroll,shopping",
            # P002 / Untapped Wealth: C0003 over-contacted-excluded.
            "P002,C0003,0.60,5000,Untapped Wealth,shopping,bills,payroll",
            # P002 / Not Now: C0004 unreachable (no allowed+reachable channel).
            "P002,C0004,0.30,1000,Not Now,payroll,bills,shopping",
        ],
    )
    segment_summary = _write(
        tmp_path,
        "segment_summary.csv",
        [
            SEGMENT_SUMMARY_HEADER,
            "P001,Ready Toppers,2",
            "P001,Willing but Stretched,1",
            "P002,Untapped Wealth,1",
            "P002,Not Now,1",
        ],
    )
    ndb = _write(
        tmp_path,
        "ndb.csv",
        [
            NDB_HEADER,
            # C0009 is on the do-not-contact list -> excluded "ndb".
            "C0009,manual,2026-01-01",
        ],
    )
    contact_history = _write(
        tmp_path,
        "contact_history.csv",
        [
            CONTACT_HISTORY_HEADER,
            # C0003: 4 events in one month -> avg 4 > 3 -> over_contacted.
            "C0003,2026-06-01,CMP1,Email",
            "C0003,2026-06-08,CMP2,Email",
            "C0003,2026-06-15,CMP3,SMS",
            "C0003,2026-06-22,CMP4,SMS",
            # C0001: one event, avg 1 -> not over-contacted.
            "C0001,2026-07-15,CMP5,Email",
        ],
    )
    channel_costs = _write(
        tmp_path,
        "channel_costs.csv",
        [
            CHANNEL_COSTS_HEADER,
            "In-app,1.17,ops",
            "Email,0.053,ops",
            "SMS,0.264,ops",
        ],
    )
    customer_dna = _write(
        tmp_path,
        "customer_dna.csv",
        [
            CUSTOMER_DNA_HEADER,
            # C0001 reachable In-app; C0002 reachable Email only.
            "C0001,1,1,0,A",
            "C0002,0,1,1,B",
            "C0009,1,1,1,C",
            "C0003,1,1,1,D",
            # C0004 reachable only by SMS, but P002 allows only "In-app, Email"
            # -> no allowed+reachable channel -> excluded "no reachable channel".
            "C0004,0,0,1,E",
        ],
    )
    promo_history = _write(
        tmp_path,
        "promo_history.csv",
        [
            PROMO_HISTORY_HEADER,
            "P001,TOP_UP,\"Email, In-app\"",
            "P002,NEW_ACCOUNT,\"Email, In-app\"",
        ],
    )
    return {
        "segments": segments,
        "segment_summary": segment_summary,
        "ndb": ndb,
        "contact_history": contact_history,
        "channel_costs": channel_costs,
        "customer_dna": customer_dna,
        "promo_history": promo_history,
    }


def _argv(paths: dict[str, Path], tmp_path: Path) -> list[str]:
    """Build a main() argv pointing at ``paths`` with outputs under tmp_path."""
    return [
        "--segments", str(paths["segments"]),
        "--segment-summary", str(paths["segment_summary"]),
        "--ndb", str(paths["ndb"]),
        "--contact-history", str(paths["contact_history"]),
        "--channel-costs", str(paths["channel_costs"]),
        "--customer-dna", str(paths["customer_dna"]),
        "--promo-history", str(paths["promo_history"]),
        "--cards-out", str(tmp_path / "outputs" / "cards.json"),
        "--leads-out-dir", str(tmp_path / "outputs" / "leads"),
    ]


# The four (promo, segment) Cells present in the valid inputs, with the
# expected per-Cell lead filename (Requirement 6.3) and sendable client_ids.
_EXPECTED_CELLS = {
    ("P001", "Ready Toppers"): ("P001_ready_toppers.csv", {"C0001"}),
    ("P001", "Willing but Stretched"): ("P001_willing_but_stretched.csv", {"C0002"}),
    ("P002", "Untapped Wealth"): ("P002_untapped_wealth.csv", set()),
    ("P002", "Not Now"): ("P002_not_now.csv", set()),
}


# --- Requirement 6.3: segment slug rule (lowercase, non-alnum runs -> _) ------


@pytest.mark.parametrize(
    ("segment", "expected"),
    [
        ("Ready Toppers", "ready_toppers"),
        ("Willing but Stretched", "willing_but_stretched"),
        ("Untapped Wealth", "untapped_wealth"),
        ("Not Now", "not_now"),
        # Runs of non-alphanumeric characters collapse to a single underscore.
        ("A  B", "a_b"),
        ("Foo-Bar / Baz", "foo_bar_baz"),
    ],
)
def test_segment_slug_rule(segment: str, expected: str) -> None:
    """The slug lowercases and collapses non-alphanumeric runs (Requirement 6.3)."""
    assert _segment_slug(segment) == expected


# --- Requirements 6.2, 6.3, 6.4, 6.5: outputs + printed summary ---------------


def test_main_writes_cards_leads_and_prints_summary(tmp_path: Path, capsys) -> None:
    """main writes cards.json, per-Cell lead CSVs, and prints the summary.

    - ``cards.json`` is a JSON list with exactly one Card per Cell -- four Cells
      for two promos here (Requirement 6.2).
    - Each Cell has a lead file named ``<promo_id>_<segment_slug>.csv`` using
      the slug rule (Requirement 6.3).
    - Each lead CSV has the four columns ``client_id,best_channel,p_join,control``,
      one row per Sendable_Lead only, ``control`` always 0, with no Control or
      Excluded Leads written (Requirement 6.4).
    - The summary prints one line per Card with the seven fields in order
      (Requirement 6.5).

    _Requirements: 6.2, 6.3, 6.4, 6.5_
    """
    paths = _valid_inputs(tmp_path)
    cards_out = tmp_path / "outputs" / "cards.json"
    leads_dir = tmp_path / "outputs" / "leads"

    exit_code = main(_argv(paths, tmp_path))
    assert exit_code == 0

    # --- Requirement 6.2: cards.json is a JSON list, one Card per Cell. -------
    assert cards_out.exists()
    cards = json.loads(cards_out.read_text(encoding="utf-8"))
    assert isinstance(cards, list)
    assert len(cards) == len(_EXPECTED_CELLS)

    cells = {(card["promo_id"], card["segment"]) for card in cards}
    assert cells == set(_EXPECTED_CELLS)
    # Exactly one Card per Cell (no duplicates).
    assert len(cells) == len(cards)

    # --- Requirement 6.3: per-Cell lead files named by the slug rule. --------
    expected_files = {name for name, _ in _EXPECTED_CELLS.values()}
    actual_files = {p.name for p in leads_dir.iterdir()}
    assert actual_files == expected_files

    # --- Requirement 6.4: each CSV is sendable-only, control always 0. -------
    cards_by_cell = {(c["promo_id"], c["segment"]): c for c in cards}
    for (promo_id, segment), (filename, sendable_ids) in _EXPECTED_CELLS.items():
        path = leads_dir / filename
        assert path.exists(), f"missing lead file for {promo_id}/{segment}"

        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            rows = list(reader)

        # Header is exactly the four required columns in order.
        assert rows[0] == _LEADS_COLUMNS
        data_rows = rows[1:]

        # One row per Sendable_Lead, and only sendable client_ids appear.
        written_ids = {r[0] for r in data_rows}
        assert written_ids == sendable_ids
        # The row count matches the Card's sendable_count (no control/excluded).
        card = cards_by_cell[(promo_id, segment)]
        assert len(data_rows) == card["sendable_count"]

        # control is 0 for every written row (Requirement 6.4).
        for r in data_rows:
            assert r[3] == "0"

    # The NDB, over-contacted, and unreachable Leads never appear in any CSV.
    all_written_ids: set[str] = set()
    for filename, _ in _EXPECTED_CELLS.values():
        with (leads_dir / filename).open(newline="", encoding="utf-8") as handle:
            all_written_ids.update(r[0] for r in list(csv.reader(handle))[1:])
    assert all_written_ids == {"C0001", "C0002"}
    for excluded_id in ("C0009", "C0003", "C0004"):
        assert excluded_id not in all_written_ids

    # --- Requirement 6.5: one summary line per Card, seven fields each. ------
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line != ""]
    assert len(lines) == len(cards)

    printed_cells: set[tuple[str, str]] = set()
    for line in lines:
        fields = line.split("\t")
        assert len(fields) == _SUMMARY_FIELDS, (
            f"expected {_SUMMARY_FIELDS} fields, got {len(fields)}: {line!r}"
        )
        promo_id, segment = fields[0], fields[1]
        printed_cells.add((promo_id, segment))
        # The matching Card's n_clients, sendable_count, and action are printed
        # in positions 2, 3, and 6 (Requirement 6.5).
        card = cards_by_cell[(promo_id, segment)]
        assert fields[2] == str(card["n_clients"])
        assert fields[3] == str(card["sendable_count"])
        assert fields[6] == card["action"]
    # Every Card contributed exactly one printed line.
    assert printed_cells == set(_EXPECTED_CELLS)


# --- Requirement 6.6: loader error -> no output dir/file, nothing printed -----


def test_main_loader_error_creates_no_output_and_prints_nothing(
    tmp_path: Path, capsys
) -> None:
    """A loader error halts main before any output or print (Requirement 6.6).

    Pointing ``--segments`` at a non-existent file (the other six inputs valid)
    makes ``loader.load`` raise ``FileNotFoundError`` before the Lead_Classifier
    runs. ``main`` does not catch it, so it propagates out: the ``outputs/``
    directory is never created, no file is written, and nothing is printed. The
    output dir does not exist before the call and still does not exist after.

    _Requirements: 6.6_
    """
    paths = _valid_inputs(tmp_path)
    # Clobber segments with a path that does not exist so the loader halts first.
    missing_segments = tmp_path / "does_not_exist_segments.csv"
    paths["segments"].unlink()
    paths["segments"] = missing_segments
    assert not missing_segments.exists()

    outputs_dir = tmp_path / "outputs"
    cards_out = outputs_dir / "cards.json"
    leads_dir = outputs_dir / "leads"

    # Snapshot: the output dir does not exist before the call.
    assert not outputs_dir.exists()

    with pytest.raises(FileNotFoundError) as excinfo:
        main(_argv(paths, tmp_path))

    # The error names the missing segments path (loader halt-without-output).
    assert str(missing_segments) in str(excinfo.value)

    # Nothing printed to stdout: no summary (Requirement 6.6).
    captured = capsys.readouterr()
    assert captured.out == ""

    # The output dir still does not exist, and neither output was created.
    assert not outputs_dir.exists()
    assert not cards_out.exists()
    assert not leads_dir.exists()

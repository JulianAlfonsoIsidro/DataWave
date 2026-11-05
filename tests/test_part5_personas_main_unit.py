"""Unit tests for the Persona_Pipeline CLI entry point (``part5_personas.main``).

Covers exactly the four behaviors task 11.2 names, all via ``main(argv)`` with
path overrides onto a temporary ``outputs``-shaped fixture so no real artifact is
touched:

- **Success exit code + output written** (Requirement 9.6): a valid run over a
  small in-memory-sized fixture returns ``0`` and writes the full
  Persona_Labeled_Leads to ``--labeled-leads-out``.
- **Missing-artifact halt** (Requirement 9.5): when a required upstream
  ``outputs/`` artifact (the Part 2 features CSV or the per-cell ``leads/``
  directory) is absent, ``main`` returns a non-zero code, prints a stderr message
  naming the missing artifact, and writes nothing.
- **Output-last write safety** (Requirement 9.8): when a stage fails mid-run (an
  answer-key input triggers the join guard, a too-low Match_Rate triggers the
  join halt, or the clustering stage raises), ``main`` returns non-zero and leaves
  the output path untouched -- no partial file is written.
- **Failing-step naming** (Requirement 9.7): a mid-run failure's stderr message
  names the failing step (``join``), so an operator can locate the fault.

The fixtures are deliberately tiny and deterministic. The "success" fixture uses
enough clients to clear the default ``min_group_size`` (30) so the ``all`` run
actually clusters; k-prototypes on ~45 rows with three attributes is fast. Relies
on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from part5_personas.main import main

# --- fixture sizing ---------------------------------------------------------
# Above the default Config.min_group_size (30) so the level-``all`` group clusters.
_N_CLIENTS = 45


def _client_ids(n: int = _N_CLIENTS) -> list[str]:
    return [f"C{i:04d}" for i in range(n)]


def _write_customer_dna(path: Path, ids: list[str]) -> None:
    """A customer_dna frame: client_id + a categorical segment + two columns."""
    segments = ["Mass", "Mid-Market", "Affluent-Preferred"]
    frame = pd.DataFrame(
        {
            "client_id": ids,
            "segment": [segments[i % len(segments)] for i in range(len(ids))],
            "age": [25 + (i % 40) for i in range(len(ids))],
            "tenure_years": [float(i % 12) for i in range(len(ids))],
        }
    )
    frame.to_csv(path, index=False)


def _write_product_ownership(path: Path, ids: list[str]) -> None:
    """A long-format product_ownership frame covering every client."""
    rows = []
    products = ["deposit", "investment", "card"]
    for i, cid in enumerate(ids):
        # Each client owns at least one product so every client matches.
        rows.append({"client_id": cid, "product_type": products[i % len(products)]})
        if i % 2 == 0:
            rows.append({"client_id": cid, "product_type": "deposit"})
    pd.DataFrame(rows, columns=["client_id", "product_type"]).to_csv(path, index=False)


def _write_features_part2(path: Path, ids: list[str]) -> None:
    """A features_part2 frame covering every client with two numeric features."""
    frame = pd.DataFrame(
        {
            "client_id": ids,
            "out_other_bank": [float((i * 7) % 11) for i in range(len(ids))],
            "inflow_share": [float((i % 5)) / 4.0 for i in range(len(ids))],
        }
    )
    frame.to_csv(path, index=False)


def _write_leads_dir(leads_dir: Path, ids: list[str]) -> None:
    """Two per-cell Part 4 leads files covering a slice of the clients."""
    leads_dir.mkdir(parents=True, exist_ok=True)
    half = len(ids) // 2
    cell_a = pd.DataFrame(
        {
            "client_id": ids[:half],
            "best_channel": ["Email"] * half,
            "p_join": [0.3] * half,
            "control": [0] * half,
        }
    )
    cell_b = pd.DataFrame(
        {
            "client_id": ids[half:],
            "best_channel": ["SMS"] * (len(ids) - half),
            "p_join": [0.4] * (len(ids) - half),
            "control": [0] * (len(ids) - half),
        }
    )
    cell_a.to_csv(leads_dir / "P001_ready_toppers.csv", index=False)
    cell_b.to_csv(leads_dir / "P001_not_now.csv", index=False)


def _build_fixture(root: Path) -> dict[str, Path]:
    """Create a complete, valid fixture tree under ``root`` and return its paths."""
    ids = _client_ids()
    data_dir = root / "data"
    outputs_dir = root / "outputs"
    leads_dir = outputs_dir / "leads"
    data_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    customer_dna = data_dir / "customer_dna.csv"
    product_ownership = data_dir / "product_ownership.csv"
    features_part2 = outputs_dir / "features_part2.csv"
    out_path = outputs_dir / "persona_labeled_leads.csv"

    _write_customer_dna(customer_dna, ids)
    _write_product_ownership(product_ownership, ids)
    _write_features_part2(features_part2, ids)
    _write_leads_dir(leads_dir, ids)

    return {
        "customer_dna": customer_dna,
        "product_ownership": product_ownership,
        "features_part2": features_part2,
        "leads_dir": leads_dir,
        "out_path": out_path,
    }


def _argv(fx: dict[str, Path], out_path: Path | None = None) -> list[str]:
    """Build the main() argv from a fixture, defaulting the output to fx['out_path']."""
    return [
        "--customer-dna", str(fx["customer_dna"]),
        "--product-ownership", str(fx["product_ownership"]),
        "--features-part2", str(fx["features_part2"]),
        "--leads-dir", str(fx["leads_dir"]),
        "--labeled-leads-out", str(out_path or fx["out_path"]),
    ]


# --------------------------------------------------------------------------- #
# 1. Success: exit 0 and the output is written (Requirement 9.6)              #
# --------------------------------------------------------------------------- #
def test_main_success_returns_zero_and_writes_output(tmp_path: Path):
    """A valid run returns 0 and writes the labeled-leads CSV (Requirement 9.6)."""
    fx = _build_fixture(tmp_path)
    out_path = fx["out_path"]
    assert not out_path.exists()

    rc = main(_argv(fx))

    assert rc == 0
    assert out_path.exists()
    written = pd.read_csv(out_path)
    # One row per Part 4 lead (the union of the two cells == all clients here).
    assert len(written) == _N_CLIENTS
    assert "persona_label" in written.columns
    assert "group" in written.columns


# --------------------------------------------------------------------------- #
# 2. Missing-artifact halt (Requirement 9.5)                                  #
# --------------------------------------------------------------------------- #
def test_main_halts_when_features_artifact_missing(tmp_path: Path, capsys):
    """A missing features_part2 artifact halts non-zero, naming it, writing nothing."""
    fx = _build_fixture(tmp_path)
    fx["features_part2"].unlink()  # remove the required artifact
    out_path = fx["out_path"]

    rc = main(_argv(fx))

    assert rc != 0
    assert not out_path.exists()
    err = capsys.readouterr().err
    assert "missing-artifact" in err
    assert "features_part2" in err


def test_main_halts_when_leads_dir_missing(tmp_path: Path, capsys):
    """A missing per-cell leads directory halts non-zero, naming it, writing nothing."""
    fx = _build_fixture(tmp_path)
    missing_leads = tmp_path / "outputs" / "no_such_leads_dir"
    out_path = fx["out_path"]

    argv = [
        "--customer-dna", str(fx["customer_dna"]),
        "--product-ownership", str(fx["product_ownership"]),
        "--features-part2", str(fx["features_part2"]),
        "--leads-dir", str(missing_leads),
        "--labeled-leads-out", str(out_path),
    ]
    rc = main(argv)

    assert rc != 0
    assert not out_path.exists()
    err = capsys.readouterr().err
    assert "missing-artifact" in err
    assert "leads" in err


# --------------------------------------------------------------------------- #
# 3. Output-last write safety on a mid-run failure (Requirements 9.7, 9.8)    #
# --------------------------------------------------------------------------- #
def test_main_answer_key_input_halts_before_writing(tmp_path: Path, capsys):
    """An answer-key input fails the join guard; no output file is written (Req 9.8).

    The required artifacts all exist (so the missing-artifact gate passes), but the
    customer-DNA path carries the forbidden ``_answer_key`` marker, so the join
    stage raises after the gate and before any write -- exactly the mid-run failure
    output-last must survive. The output path must remain absent (Requirement 9.8)
    and the stderr message must name the failing ``join`` step (Requirement 9.7).
    """
    fx = _build_fixture(tmp_path)
    # Copy customer_dna to an answer-key-named path so the join guard trips, while
    # the real artifacts the missing-artifact gate checks still exist.
    forbidden = tmp_path / "data" / "customer_dna_answer_key.csv"
    forbidden.write_bytes(fx["customer_dna"].read_bytes())
    out_path = fx["out_path"]

    argv = [
        "--customer-dna", str(forbidden),
        "--product-ownership", str(fx["product_ownership"]),
        "--features-part2", str(fx["features_part2"]),
        "--leads-dir", str(fx["leads_dir"]),
        "--labeled-leads-out", str(out_path),
    ]
    rc = main(argv)

    assert rc != 0
    assert not out_path.exists()  # output-last: nothing written on a mid-run halt
    err = capsys.readouterr().err
    assert "[join]" in err


def test_main_low_match_rate_halts_before_writing(tmp_path: Path, capsys):
    """A too-low Match_Rate fails the join stage; no output is written (Req 9.8).

    The features_part2 artifact exists (clearing the missing-artifact gate) but
    matches none of the customer_dna clients, so its Match_Rate is 0 and the join
    stage halts. The output path must remain absent and the failing step named.
    """
    fx = _build_fixture(tmp_path)
    # Overwrite features with rows whose client_ids match no customer -> rate 0.
    pd.DataFrame(
        {
            "client_id": [f"Z{i:04d}" for i in range(_N_CLIENTS)],
            "out_other_bank": [0.0] * _N_CLIENTS,
            "inflow_share": [0.0] * _N_CLIENTS,
        }
    ).to_csv(fx["features_part2"], index=False)
    out_path = fx["out_path"]

    rc = main(_argv(fx))

    assert rc != 0
    assert not out_path.exists()
    err = capsys.readouterr().err
    assert "[join]" in err


def test_main_does_not_overwrite_existing_output_on_failure(tmp_path: Path):
    """A mid-run failure leaves a pre-existing output file byte-for-byte unchanged.

    Writes a sentinel file at the output path first, then runs a job that fails in
    the join stage (answer-key input). Output-last means the sentinel must be
    untouched -- the failing run neither truncates nor rewrites it (Requirement 9.8).
    """
    fx = _build_fixture(tmp_path)
    out_path = fx["out_path"]
    sentinel = b"PRE-EXISTING OUTPUT - MUST NOT BE TOUCHED\n"
    out_path.write_bytes(sentinel)

    forbidden = tmp_path / "data" / "customer_dna_answer_key.csv"
    forbidden.write_bytes(fx["customer_dna"].read_bytes())
    argv = [
        "--customer-dna", str(forbidden),
        "--product-ownership", str(fx["product_ownership"]),
        "--features-part2", str(fx["features_part2"]),
        "--leads-dir", str(fx["leads_dir"]),
        "--labeled-leads-out", str(out_path),
    ]
    rc = main(argv)

    assert rc != 0
    assert out_path.read_bytes() == sentinel


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

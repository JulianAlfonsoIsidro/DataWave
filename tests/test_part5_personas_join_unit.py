"""Example-based unit tests for the Persona_Pipeline join assembler.

Covers the public API of ``part5_personas.join`` with small, deterministic,
in-memory frames (the companion property-based tests live elsewhere). The
cases exercise:

- one-hot pivot correctness, dedup, and deterministic alphabetical column
  order (Requirement 1.2);
- absent-ownership clients getting every ``owns_`` flag imputed to ``0`` with
  exactly one joined row per ``customer_dna`` client (Requirement 1.4);
- per-source Match_Rate values, both via ``build_joined_attributes`` and the
  ``match_rate`` helper, including the empty-base degenerate case
  (Requirement 1.6);
- the Answer_Key_File rejection message (Requirement 1.10);
- the low-Match_Rate halt message naming the offending source and its rate
  (Requirement 1.8).

Relies on ``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd
import pytest

from part5_personas.config import Config
from part5_personas.join import (
    assert_no_answer_key,
    build_joined_attributes,
    match_rate,
    pivot_product_ownership,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _write_sources(
    tmp_path: Path,
    customer_dna: pd.DataFrame,
    product_ownership: pd.DataFrame,
    features_part2: pd.DataFrame,
    **cfg_overrides,
) -> Config:
    """Write the three CSV sources under ``tmp_path`` and build a Config."""
    dna_path = tmp_path / "customer_dna.csv"
    po_path = tmp_path / "product_ownership.csv"
    feat_path = tmp_path / "features_part2.csv"

    customer_dna.to_csv(dna_path, index=False)
    product_ownership.to_csv(po_path, index=False)
    features_part2.to_csv(feat_path, index=False)

    return dataclasses.replace(
        Config(),
        customer_dna_path=dna_path,
        product_ownership_path=po_path,
        features_part2_path=feat_path,
        labeled_leads_out_path=tmp_path / "out.csv",
        **cfg_overrides,
    )


# --------------------------------------------------------------------------- #
# 1. pivot one-hot correctness (Requirement 1.2)                              #
# --------------------------------------------------------------------------- #
def test_pivot_one_hot_correctness_and_dedup():
    """Pivot yields one row per client, 0/1 int flags, dedup, sorted cols."""
    product_ownership = pd.DataFrame(
        {
            # C1 owns Deposit twice (dedup -> one flag) and a Loan.
            # C2 owns only a Card. C3 owns a Deposit.
            "client_id": ["C1", "C1", "C1", "C2", "C3"],
            "product_type": ["Deposit", "Deposit", "Loan", "Card", "Deposit"],
        }
    )

    pivoted = pivot_product_ownership(product_ownership)

    # One row per distinct client_id.
    assert list(pivoted["client_id"]) == ["C1", "C2", "C3"]
    assert len(pivoted) == 3

    # Flag columns are owns_<type>, alphabetically sorted and deterministic.
    flag_cols = [c for c in pivoted.columns if c != "client_id"]
    assert flag_cols == ["owns_Card", "owns_Deposit", "owns_Loan"]
    assert list(pivoted.columns) == ["client_id", "owns_Card", "owns_Deposit", "owns_Loan"]

    indexed = pivoted.set_index("client_id")

    # Values are exactly 0/1 integers.
    for col in flag_cols:
        assert set(indexed[col].unique()) <= {0, 1}
        assert pd.api.types.is_integer_dtype(indexed[col])

    # C1: two Deposit rows still collapse to flag 1 (dedup), plus Loan.
    assert indexed.loc["C1", "owns_Deposit"] == 1
    assert indexed.loc["C1", "owns_Loan"] == 1
    assert indexed.loc["C1", "owns_Card"] == 0

    # C2 owns only Card.
    assert indexed.loc["C2", "owns_Card"] == 1
    assert indexed.loc["C2", "owns_Deposit"] == 0
    assert indexed.loc["C2", "owns_Loan"] == 0

    # C3 owns only Deposit.
    assert indexed.loc["C3", "owns_Deposit"] == 1
    assert indexed.loc["C3", "owns_Card"] == 0


def test_pivot_empty_input_yields_client_id_only():
    """An empty ownership frame yields a frame carrying only client_id."""
    empty = pd.DataFrame({"client_id": pd.Series(dtype=object), "product_type": pd.Series(dtype=object)})

    pivoted = pivot_product_ownership(empty)

    assert list(pivoted.columns) == ["client_id"]
    assert len(pivoted) == 0


# --------------------------------------------------------------------------- #
# 2. absent-product clients get flags 0 + one row per client (Req 1.4)        #
# --------------------------------------------------------------------------- #
def test_absent_product_clients_get_zero_flags(tmp_path):
    """Clients absent from product_ownership get every owns_ flag == 0."""
    customer_dna = pd.DataFrame({"client_id": ["C1", "C2", "C3"], "segment": ["A", "B", "C"]})
    # Only C1 and C2 own products; C3 is absent from ownership entirely.
    product_ownership = pd.DataFrame(
        {
            "client_id": ["C1", "C2"],
            "product_type": ["Deposit", "Loan"],
        }
    )
    # Features cover all three clients so feature match rate is 1.0.
    features_part2 = pd.DataFrame({"client_id": ["C1", "C2", "C3"], "feat_x": [0.1, 0.2, 0.3]})

    cfg = _write_sources(tmp_path, customer_dna, product_ownership, features_part2)
    joined, _report = build_joined_attributes(cfg)

    # Exactly one joined row per customer_dna client_id.
    assert len(joined) == 3
    assert list(joined["client_id"]) == ["C1", "C2", "C3"]

    flag_cols = [c for c in joined.columns if c.startswith("owns_")]
    assert flag_cols  # at least one ownership flag exists

    indexed = joined.set_index("client_id")

    # C3 absent from ownership -> every flag imputed to 0.
    for col in flag_cols:
        assert indexed.loc["C3", col] == 0

    # Owners carry their expected flags.
    assert indexed.loc["C1", "owns_Deposit"] == 1
    assert indexed.loc["C2", "owns_Loan"] == 1


# --------------------------------------------------------------------------- #
# 3. Match_Rate values (Requirement 1.6)                                      #
# --------------------------------------------------------------------------- #
def test_match_rate_helper_simple_fractions():
    """match_rate returns the de-duplicated base coverage fraction."""
    base = pd.Series(["C1", "C2", "C3", "C4"])
    # Only C1 and C3 present in the source -> 2 of 4 -> 0.5.
    source = pd.DataFrame({"client_id": ["C1", "C3"]})
    assert match_rate(base, source) == 0.5

    # Full coverage -> 1.0; duplicate base ids do not change the fraction.
    base_dup = pd.Series(["C1", "C1", "C2"])
    full = pd.DataFrame({"client_id": ["C1", "C2"]})
    assert match_rate(base_dup, full) == 1.0


def test_match_rate_empty_base_is_zero():
    """An empty base returns 0.0 rather than dividing by zero."""
    empty_base = pd.Series([], dtype=object)
    source = pd.DataFrame({"client_id": ["C1"]})
    assert match_rate(empty_base, source) == 0.0


def test_build_joined_reports_expected_match_rates(tmp_path):
    """build_joined_attributes reports per-source Match_Rate fractions."""
    customer_dna = pd.DataFrame({"client_id": ["C1", "C2", "C3", "C4"]})
    # Ownership covers 2 of 4 -> 0.5.
    product_ownership = pd.DataFrame(
        {"client_id": ["C1", "C2"], "product_type": ["Deposit", "Loan"]}
    )
    # Features cover 3 of 4 -> 0.75.
    features_part2 = pd.DataFrame({"client_id": ["C1", "C2", "C3"], "feat_x": [1.0, 2.0, 3.0]})

    # Floor low enough that 0.5 does not halt the run.
    cfg = _write_sources(
        tmp_path, customer_dna, product_ownership, features_part2, min_match_rate=0.25
    )
    _joined, report = build_joined_attributes(cfg)

    assert report["customer_dna"] == 1.0
    assert report["product_ownership"] == 0.5
    assert report["features_part2"] == 0.75


# --------------------------------------------------------------------------- #
# 4. answer-key rejection message (Requirement 1.10)                          #
# --------------------------------------------------------------------------- #
def test_assert_no_answer_key_rejects_offending_path():
    """assert_no_answer_key raises naming the offending answer-key file."""
    with pytest.raises(ValueError, match=r"_answer_key_clients\.csv"):
        assert_no_answer_key([Path("data/_answer_key_clients.csv")])


def test_assert_no_answer_key_allows_clean_paths():
    """A clean list of paths does not raise."""
    assert_no_answer_key([Path("data/customer_dna.csv"), Path("outputs/features_part2.csv")])


def test_build_joined_rejects_answer_key_path(tmp_path):
    """build_joined_attributes halts when a cfg path carries the marker."""
    customer_dna = pd.DataFrame({"client_id": ["C1"]})
    product_ownership = pd.DataFrame({"client_id": ["C1"], "product_type": ["Deposit"]})
    features_part2 = pd.DataFrame({"client_id": ["C1"], "feat_x": [1.0]})

    cfg = _write_sources(tmp_path, customer_dna, product_ownership, features_part2)
    # Point one input at a forbidden answer-key path.
    cfg = dataclasses.replace(
        cfg, product_ownership_path=tmp_path / "_answer_key_promos.csv"
    )

    with pytest.raises(ValueError, match="_answer_key"):
        build_joined_attributes(cfg)


# --------------------------------------------------------------------------- #
# 5. low-match-rate halt message (Requirement 1.8)                            #
# --------------------------------------------------------------------------- #
def test_build_joined_halts_on_zero_match_rate(tmp_path):
    """A source matching no base client halts, naming source and rate."""
    customer_dna = pd.DataFrame({"client_id": ["C1", "C2", "C3"]})
    product_ownership = pd.DataFrame(
        {"client_id": ["C1", "C2", "C3"], "product_type": ["Deposit", "Loan", "Card"]}
    )
    # features_part2 covers none of the customer_dna clients -> rate 0.0.
    features_part2 = pd.DataFrame({"client_id": ["Z9"], "feat_x": [1.0]})

    cfg = _write_sources(tmp_path, customer_dna, product_ownership, features_part2)

    with pytest.raises(ValueError, match=r"features_part2.*0\.0000"):
        build_joined_attributes(cfg)


def test_build_joined_halts_below_raised_floor(tmp_path):
    """A source below a raised min_match_rate halts, naming source + rate."""
    customer_dna = pd.DataFrame({"client_id": ["C1", "C2", "C3", "C4"]})
    product_ownership = pd.DataFrame(
        {"client_id": ["C1", "C2", "C3", "C4"], "product_type": ["Deposit"] * 4}
    )
    # Features cover 2 of 4 -> 0.5, which is below a 0.9 floor.
    features_part2 = pd.DataFrame({"client_id": ["C1", "C2"], "feat_x": [1.0, 2.0]})

    cfg = _write_sources(
        tmp_path, customer_dna, product_ownership, features_part2, min_match_rate=0.9
    )

    with pytest.raises(ValueError, match=r"features_part2.*0\.5000"):
        build_joined_attributes(cfg)

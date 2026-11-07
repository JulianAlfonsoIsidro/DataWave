"""Unit tests for the single-type selection helpers (task 14.9, Req 6.2, 6.11, 6.12).

Plain pytest, no Streamlit.
"""

from __future__ import annotations

import pytest

from app.persona_page import (
    SELECTION_CATEGORICAL,
    SELECTION_MIXED,
    SELECTION_NONE,
    SELECTION_NUMERIC,
    clustering_kind_caption,
    effective_clustering_attributes,
    selection_kind,
    single_type_warning,
    validation_error,
)

KINDS = {"a": "numeric", "b": "numeric", "c": "categorical", "d": "categorical"}

NUMERIC_WARNING = (
    "Only numeric attributes selected. Personas will be based on those alone. "
    "Adding a categorical attribute (such as region or a product owned) "
    "gives richer personas."
)
CATEGORICAL_WARNING = (
    "Only categorical attributes selected. Personas will be based on those alone. "
    "Adding a numeric attribute (such as years with the bank or spend) gives richer personas."
)


def test_selection_kind_basic():
    assert selection_kind(["a", "b"], KINDS) == SELECTION_NUMERIC
    assert selection_kind(["c", "d"], KINDS) == SELECTION_CATEGORICAL
    assert selection_kind(["a", "c"], KINDS) == SELECTION_MIXED
    assert selection_kind([], KINDS) == SELECTION_NONE


def test_selection_kind_ignores_unknown_columns():
    assert selection_kind(["a", "zzz"], KINDS) == SELECTION_NUMERIC
    assert selection_kind(["zzz"], KINDS) == SELECTION_NONE
    assert selection_kind(["a", "c", "zzz"], KINDS) == SELECTION_MIXED
    assert selection_kind(["a"], {}) == SELECTION_NONE


def test_effective_clustering_attributes():
    attrs = ["segment", "a", "c"]
    assert effective_clustering_attributes("all", attrs, "segment") == attrs
    assert effective_clustering_attributes("business-segment", attrs, "segment") == ["a", "c"]
    assert effective_clustering_attributes("campaign", attrs, "segment") == ["a", "c"]
    only = effective_clustering_attributes("business-segment", ["segment"], "segment")
    assert only == []
    assert selection_kind(only, KINDS) == SELECTION_NONE


def test_single_type_warning_texts():
    assert single_type_warning(SELECTION_NUMERIC) == NUMERIC_WARNING
    assert single_type_warning(SELECTION_CATEGORICAL) == CATEGORICAL_WARNING
    assert single_type_warning(SELECTION_MIXED) is None
    assert single_type_warning(SELECTION_NONE) is None
    for text in (NUMERIC_WARNING, CATEGORICAL_WARNING):
        assert "k-prototypes" not in text.lower()
        assert "better" not in text.lower()


def test_clustering_kind_caption():
    assert clustering_kind_caption(SELECTION_NUMERIC) == "Clustered on numeric attributes only"
    assert (
        clustering_kind_caption(SELECTION_CATEGORICAL)
        == "Clustered on categorical attributes only"
    )
    assert clustering_kind_caption(SELECTION_MIXED) is None
    assert clustering_kind_caption(SELECTION_NONE) is None
    assert clustering_kind_caption(None) is None


def test_empty_selection_keeps_validation_error():
    assert validation_error(0, 3, "all") == "Pick at least one attribute to build personas."


@pytest.fixture(scope="module")
def real_kinds() -> dict[str, str]:
    from part5_personas.config import Config
    from part5_personas.join import build_joined_attributes
    from part5_personas.preprocess import classify_types

    joined = build_joined_attributes(Config())[0]
    cols = [c for c in joined.columns if c != "client_id"]
    numeric, categorical = classify_types(joined, cols)
    kinds = {c: "numeric" for c in numeric}
    kinds.update({c: "categorical" for c in categorical})
    return kinds


@pytest.mark.parametrize(
    "selected, expected",
    [
        (["total_out", "inflow_share_payroll"], SELECTION_NUMERIC),
        (["age_band", "region"], SELECTION_CATEGORICAL),
        (["digital_app_user", "frugal_flag"], SELECTION_CATEGORICAL),
        (["owns_Deposit", "owns_Loan"], SELECTION_CATEGORICAL),
        (["tenure_years", "owns_Deposit"], SELECTION_MIXED),
        (["age_band", "total_out"], SELECTION_MIXED),
        # NOTE: age_band is a TEXT column in the real data, so "age + owns_Deposit"
        # is categorical-only here, not mixed.
        (["age_band", "owns_Deposit"], SELECTION_CATEGORICAL),
    ],
)
def test_real_data_selection_kinds(real_kinds, selected, expected):
    assert selection_kind(selected, real_kinds) == expected

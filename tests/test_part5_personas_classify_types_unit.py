"""Unit tests for binary-flag type classification (Requirements 1.3, 2.2, 2.3, 2.13).

A column is categorical when it is an ``owns_*`` flag, a known flag name, boolean
dtype, or an integer column whose non-missing values are all within {0, 1}; every
other int/float column stays numeric (floats are never reclassified by value).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from part5_personas.cluster import select_model_kind
from part5_personas.preprocess import classify_types, impute, preprocess


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "age_band": ["18-24", "25-34", "35-44", "25-34", "18-24", "35-44"],
            "owns_Deposit": [1, 0, 1, 1, 0, 0],
            "digital_app_user": [1, 0, 1, 0, 1, 0],
            "frugal_flag": [0, 0, 1, 0, 1, 1],
            "email_valid": [1, 1, 0, 1, 1, 0],
            "mobile_valid": [1, 0, 0, 1, 1, 1],
            "bool_col": [True, False, True, True, False, False],
            "float_flag": [1.0, 0.0, np.nan, 1.0, 0.0, 1.0],
            "n_products": [0, 1, 2, 3, 4, 5],
            "ratio": [0.1, 0.5, 0.25, 0.9, 0.0, 0.7],
            "total_out": [100.0, 2500.5, 30.0, 999.0, 1.0, 40000.0],
            "tri": [0, 1, 2, 0, 1, 2],
            "all_zero": [0, 0, 0, 0, 0, 0],
            "all_one": [1, 1, 1, 1, 1, 1],
            "all_nan": [np.nan] * 6,
        }
    )


@pytest.mark.parametrize(
    "col",
    ["owns_Deposit", "digital_app_user", "frugal_flag", "email_valid", "mobile_valid"],
)
def test_named_flag_columns_are_categorical(col):
    num, cat = classify_types(_frame(), [col])
    assert cat == [col] and num == []


def test_boolean_dtype_is_categorical():
    assert classify_types(_frame(), ["bool_col"]) == ([], ["bool_col"])


def test_float_zero_one_with_nan_stays_numeric():
    # Task 4.5: floats are never reclassified from their values (only owns_*, the
    # four known names, bool and integer 0/1 dtypes are flags).
    assert classify_types(_frame(), ["float_flag"]) == (["float_flag"], [])


@pytest.mark.parametrize("col", ["n_products", "ratio", "total_out", "tri"])
def test_other_numeric_columns_stay_numeric(col):
    assert classify_types(_frame(), [col]) == ([col], [])


def test_owns_prefix_is_categorical_even_if_not_binary():
    df = pd.DataFrame({"owns_X": [0, 1, 2, 3]})
    assert classify_types(df, ["owns_X"]) == ([], ["owns_X"])


def test_constant_zero_or_one_column_is_a_flag():
    """Behavior: a constant column holding only {0} or only {1} counts as a flag."""
    assert classify_types(_frame(), ["all_zero", "all_one"]) == ([], ["all_zero", "all_one"])


def test_all_nan_float_keeps_dtype_answer_and_impute_rejects():
    num, cat = classify_types(_frame(), ["all_nan"])
    assert (num, cat) == (["all_nan"], [])
    with pytest.raises(ValueError, match="all_nan"):
        impute(_frame()[["all_nan"]], num, cat)


def test_override_wins_both_ways():
    num, cat = classify_types(
        _frame(),
        ["digital_app_user", "n_products"],
        {"digital_app_user": "numeric", "n_products": "categorical"},
    )
    assert num == ["digital_app_user"] and cat == ["n_products"]


def test_order_preserved():
    sel = ["total_out", "digital_app_user", "age_band", "ratio", "owns_Deposit"]
    num, cat = classify_types(_frame(), sel)
    assert num == ["total_out", "ratio"]
    assert cat == ["digital_app_user", "age_band", "owns_Deposit"]


def test_preprocess_cat_indices_and_flag_not_standardized():
    sel = ["age_band", "owns_Deposit", "total_out"]
    out, idx = preprocess(_frame(), sel)
    assert idx == [0, 1]
    assert out["owns_Deposit"].tolist() == [1, 0, 1, 1, 0, 0]
    assert abs(out["total_out"].mean()) < 1e-9  # numeric still z-scored


def test_selection_cat_indices_with_and_without_flag():
    _, with_flag = preprocess(_frame(), ["age_band", "owns_Deposit"])
    _, without = preprocess(_frame(), ["age_band", "total_out"])
    assert with_flag == [0, 1]
    assert without == [0]


@pytest.mark.parametrize(
    "sel,kind",
    [
        (["digital_app_user", "frugal_flag"], "kmodes"),
        (["total_out", "ratio"], "kmeans"),
        # age_band + owns_Deposit are both categorical now -> kmodes (not mixed).
        (["age_band", "owns_Deposit"], "kmodes"),
        (["age_band", "owns_Deposit", "total_out"], "kprototypes"),
    ],
)
def test_select_model_kind_from_real_classification(sel, kind):
    _, idx = preprocess(_frame(), sel)
    assert select_model_kind(idx, len(sel)) == kind

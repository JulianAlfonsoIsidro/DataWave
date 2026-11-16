"""Unit tests for the narrowed binary-flag rule (task 4.5; Requirements 1.3, 2.2, 2.3).

A column is categorical when it is named ``owns_*``, is one of the four known flag
names, is boolean, or is an INTEGER column holding only {0, 1}. Float columns are
never reclassified from their values (documented limit: an unnamed float 0/1 column
stays numeric).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from part5_personas.config import Config
from part5_personas.join import build_joined_attributes
from part5_personas.naming import RuleBasedNamer
from part5_personas.preprocess import (
    classify_types,
    impute,
    preprocess,
)
from part5_personas.profile import _top_categories_for, build_profiles

KNOWN = ["digital_app_user", "frugal_flag", "email_valid", "mobile_valid"]


@pytest.fixture(scope="module")
def joined() -> pd.DataFrame:
    return build_joined_attributes(Config())[0]


# (1) real data -------------------------------------------------------------
def test_real_data_inflow_shares_are_numeric(joined):
    cols = [c for c in joined.columns if c.startswith("inflow_share_")]
    assert cols
    num, cat = classify_types(joined, cols)
    assert cat == [] and num == cols


def test_real_data_other_float_shares_stay_numeric(joined):
    cols = [c for c in joined.columns if c.startswith("spend_share_")]
    if "ext_outflow_ratio" in joined.columns:
        cols.append("ext_outflow_ratio")
    assert cols
    num, cat = classify_types(joined, cols)
    assert cat == [] and num == cols


def test_real_data_flags_are_categorical(joined):
    cols = [c for c in joined.columns if c.startswith("owns_")] + KNOWN
    assert len([c for c in cols if c.startswith("owns_")]) == 5
    num, cat = classify_types(joined, cols)
    assert num == [] and cat == cols


def test_known_flag_constant():
    from part5_personas.preprocess import KNOWN_FLAG_COLUMNS

    assert KNOWN_FLAG_COLUMNS == tuple(KNOWN)


# (2),(5) unnamed float 0/1 stays numeric ------------------------------------
@pytest.mark.parametrize("vals", [[0.0, 1.0, 1.0, 0.0], [0.0, 1.0, np.nan, 1.0]])
def test_unnamed_float_zero_one_stays_numeric(vals):
    df = pd.DataFrame({"some_share": vals})
    assert classify_types(df, ["some_share"]) == (["some_share"], [])


# (3) int / bool 0-1 -> categorical ------------------------------------------
def test_unnamed_int_and_bool_zero_one_are_categorical():
    df = pd.DataFrame(
        {"promo_opt_in": [0, 1, 1, 0], "b": [True, False, True, True], "n": [0, 1, 2, 3]}
    )
    assert classify_types(df, ["promo_opt_in", "b", "n"]) == (["n"], ["promo_opt_in", "b"])


# (4) known names / owns_ prefix as float with NaN ---------------------------
@pytest.mark.parametrize("col", KNOWN + ["owns_X"])
def test_named_flags_categorical_even_as_float_with_nan(col):
    df = pd.DataFrame({col: [1.0, 0.0, np.nan, 1.0]})
    assert classify_types(df, [col]) == ([], [col])


# (6) overrides win both ways -------------------------------------------------
def test_overrides_win_both_ways():
    df = pd.DataFrame(
        {"digital_app_user": [1, 0, 1], "n": [0, 1, 2], "promo_opt_in": [0, 1, 0]}
    )
    num, cat = classify_types(
        df,
        ["digital_app_user", "n", "promo_opt_in"],
        {"digital_app_user": "numeric", "n": "categorical"},
    )
    assert num == ["digital_app_user"] and cat == ["n", "promo_opt_in"]
    df2 = pd.DataFrame({"some_share": [0.0, 1.0, 1.0]})
    assert classify_types(df2, ["some_share"], {"some_share": "categorical"}) == (
        [],
        ["some_share"],
    )


# (7) all-NaN float -----------------------------------------------------------
def test_all_nan_float_numeric_and_impute_rejects():
    df = pd.DataFrame({"all_nan": [np.nan] * 4})
    num, cat = classify_types(df, ["all_nan"])
    assert (num, cat) == (["all_nan"], [])
    with pytest.raises(ValueError, match="all_nan"):
        impute(df, num, cat)
    with pytest.raises(ValueError, match="all_nan"):
        preprocess(df, ["all_nan"])


# (8) float-stored flag category keys -----------------------------------------
def test_top_categories_integral_floats_render_as_integers():
    col = pd.Series([1.0, 1.0, 0.0, 1.0])
    assert _top_categories_for(col) == [("1", 3), ("0", 1)]


def test_top_categories_non_integral_float_and_strings_unchanged():
    assert _top_categories_for(pd.Series([0.5, 0.5, 1.0])) == [("0.5", 2), ("1", 1)]
    assert _top_categories_for(pd.Series(["a", "b", "a"])) == [("a", 2), ("b", 1)]


def test_float_stored_flag_profiles_with_integer_keys_and_namer_channel():
    # digital_app_user stored as float because of a NaN; imputed to its mode (1.0).
    raw = pd.DataFrame(
        {
            "digital_app_user": [1.0, 1.0, np.nan, 1.0, 1.0, 0.0],
            "total_out": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        }
    )
    num, cat = classify_types(raw, list(raw.columns))
    assert cat == ["digital_app_user"]
    imputed = impute(raw, num, cat)
    profiles = build_profiles(imputed, np.zeros(len(imputed), dtype=int), num, cat)
    keys = [c for c, _ in profiles[0].top_categories["digital_app_user"]]
    assert keys == ["1", "0"]
    naming = RuleBasedNamer().name(profiles[0], set())
    assert any("In-app" in a for a in naming["actions"])

"""Pure-function tests for the Personas split controls (spec part6 task 14.17).

Covers ``split_columns``, ``split_columns_caption``, ``filter_picker_for_split``,
``split_exclusion_caption`` and the page level options (Requirements 3.4, 3.5,
3.8, 3.22, 3.23).
"""

from __future__ import annotations

import pandas as pd

from app import persona_page as pp
from part5_personas.preprocess import classify_types


def _joined() -> pd.DataFrame:
    n = 40
    return pd.DataFrame(
        {
            "client_id": [f"C{i}" for i in range(n)],
            "age_band": ["18-24", "25-34", "35-44", "45+"] * 10,
            "digital_app_user": [0, 1] * 20,
            "owns_Deposit": [1] * n,
            "all_missing_cat": [None] * n,
            "total_out": [float(i) * 1.5 for i in range(n)],
            "wide_cat": [f"v{i % 13}" for i in range(n)],
            "twelve_cat": [f"w{i % 12}" for i in range(n)],
        }
    )


def _kinds(frame: pd.DataFrame) -> dict[str, str]:
    cols = [c for c in frame.columns if c != "client_id"]
    numeric, categorical = classify_types(frame, cols)
    out = {c: "numeric" for c in numeric}
    out.update({c: "categorical" for c in categorical})
    return out


def test_split_columns_offers_and_excludes_with_reasons():
    frame = _joined()
    kinds = _kinds(frame)
    # Force kinds so the test does not depend on classify_types heuristics.
    kinds.update(
        {
            "age_band": "categorical",
            "digital_app_user": "categorical",
            "owns_Deposit": "categorical",
            "all_missing_cat": "categorical",
            "wide_cat": "categorical",
            "twelve_cat": "categorical",
            "total_out": "numeric",
        }
    )
    offered, left_out = pp.split_columns(frame, kinds)
    assert "age_band" in offered and "digital_app_user" in offered
    assert "twelve_cat" in offered  # 12 distinct values is kept
    assert "wide_cat" not in offered  # 13 distinct values
    assert "owns_Deposit" not in offered
    assert "total_out" not in offered and "client_id" not in offered
    assert left_out["owns_Deposit"] == "same for every client"
    assert left_out["wide_cat"] == "more than 12 values"
    assert left_out["all_missing_cat"] == "no values"
    assert "total_out" not in left_out and "client_id" not in left_out


def test_split_columns_max_values_param():
    frame = _joined()
    kinds = {c: "categorical" for c in frame.columns if c != "client_id"}
    offered, left_out = pp.split_columns(frame, kinds, max_values=3)
    assert "age_band" not in offered
    assert left_out["age_band"] == "more than 3 values"


def test_split_columns_caption():
    cap = pp.split_columns_caption({"owns_Deposit": "same for every client"})
    assert cap == (
        "Only category and yes/no columns with 2 to 12 values can split leads. "
        "Not offered: Owns Deposit account (same for every client)."
    )
    assert "Not offered" not in pp.split_columns_caption({})


def test_filter_picker_for_split_removes_options_and_defaults():
    grouped = {"Demographics": ["age_band", "region"], "Lifestyle": ["digital_app_user"]}
    defaults = ["age_band", "digital_app_user"]
    g, d = pp.filter_picker_for_split(grouped, defaults, ["age_band"])
    assert g == {"Demographics": ["region"], "Lifestyle": ["digital_app_user"]}
    assert d == ["digital_app_user"]
    g2, d2 = pp.filter_picker_for_split(grouped, defaults, [])
    assert g2 == grouped and d2 == defaults
    assert grouped["Demographics"] == ["age_band", "region"]  # input not mutated


def test_filter_picker_drops_emptied_group():
    g, _d = pp.filter_picker_for_split({"Lifestyle": ["digital_app_user"]}, [], ["digital_app_user"])
    assert g == {}


def test_split_exclusion_caption():
    assert pp.split_exclusion_caption([]) is None
    assert pp.split_exclusion_caption(["age_band"]) == (
        "Age band is used for the split, so it isn't offered here "
        "(it's the same for everyone in a group)."
    )
    plural = pp.split_exclusion_caption(["age_band", "region"])
    assert plural is not None
    assert "Age band and Region are used for the split" in plural
    assert "aren't offered here" in plural


def test_page_level_options_exclude_business_segment():
    assert pp.PAGE_LEVEL_LABEL_ORDER == ["All leads", "By campaign"]
    assert pp.level_value_to_label("business-segment") == "By customer segment"

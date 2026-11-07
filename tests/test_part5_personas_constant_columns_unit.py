"""Unit tests for hiding constant columns from the Attribute_Picker (task 14.14).

Covers Requirements 3.1, 3.13, 3.21: a column with a single distinct value across
the Joined_Attribute_Set cannot distinguish personas, so it is omitted from the
picker and from the default set. Tests the Streamlit-free helpers in
``app/persona_page.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.persona_page import (
    DEFAULT_ATTRIBUTE_SET,
    constant_columns,
    default_attribute_set,
    group_attributes_by_theme,
    visible_attribute_columns,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "client_id": ["C1", "C2", "C3"],
            "owns_Deposit": [1, 1, 1],
            "age_band": ["25-34", "35-44", "25-34"],
            "total_out": [1.0, np.nan, 3.0],
            "only_one_with_nan": [5.0, np.nan, 5.0],
            "all_nan": [np.nan, np.nan, np.nan],
        }
    )


def test_constant_columns_detected() -> None:
    assert "owns_Deposit" in constant_columns(_frame())


def test_nan_is_ignored_when_counting_distinct_values() -> None:
    cols = constant_columns(_frame())
    assert "only_one_with_nan" in cols  # {5.0} + NaN -> still constant
    assert "total_out" not in cols  # {1.0, 3.0} + NaN -> varies


def test_varying_columns_kept() -> None:
    cols = constant_columns(_frame())
    assert "age_band" not in cols
    assert "total_out" not in cols


def test_all_nan_column_is_hidden() -> None:
    assert "all_nan" in constant_columns(_frame())


def test_client_id_untouched() -> None:
    frame = _frame().assign(client_id="C1")  # constant id
    assert "client_id" not in constant_columns(frame)
    # Passed through unchanged; stripping it stays group_attributes_by_theme's job.
    assert "client_id" in visible_attribute_columns(list(frame.columns), frame)
    assert "client_id" not in group_attributes_by_theme(list(frame.columns))


def test_visible_columns_drop_hidden_and_keep_order() -> None:
    frame = _frame()
    visible = visible_attribute_columns(list(frame.columns), frame)
    assert visible == ["client_id", "age_band", "total_out"]


def test_default_set_drops_hidden_columns() -> None:
    hidden = {"age_band", "owns_Deposit"}
    result = default_attribute_set(hidden)
    assert "age_band" not in result
    assert result == [c for c in DEFAULT_ATTRIBUTE_SET if c != "age_band"]
    assert default_attribute_set(set()) == DEFAULT_ATTRIBUTE_SET


def test_grouped_picker_omits_constant_column() -> None:
    frame = _frame()
    grouped = group_attributes_by_theme(visible_attribute_columns(list(frame.columns), frame))
    flat = [c for cols in grouped.values() for c in cols]
    assert "owns_Deposit" not in flat
    assert "age_band" in flat

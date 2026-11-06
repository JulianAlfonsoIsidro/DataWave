"""Unit tests for restricting the business-segment grouping field (task 9.3).

Requirements 3.5, 3.6, 3.7, 3.20: the only Business_Segment_Field is
``customer_dna.segment``; the Part 3 Segment_Label is assigned per client and per
promo, so it cannot group customers.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.persona_page import (
    business_segment_field_for_level,
    business_segment_field_options,
)
from part5_personas import grouping
from part5_personas.grouping import (
    BUSINESS_SEGMENT_FIELD,
    BUSINESS_SEGMENT_FIELD_OPTIONS,
    LEVEL_BUSINESS_SEGMENT,
    InvalidSegmentFieldError,
    build_persona_sets,
)

PAGE_SOURCE = Path(__file__).resolve().parents[1] / "app" / "persona_page.py"


def _frame(with_segment: bool = True) -> pd.DataFrame:
    # Groups of 2 leads are below min_group_size, so no clustering runs (fast).
    data = {
        "client_id": [f"C{i}" for i in range(6)],
        "num1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "other": ["a", "a", "b", "b", "c", "c"],
    }
    if with_segment:
        data["segment"] = ["Mass", "Mass", "Mid-Market", "Mid-Market", "Mass", "Mid-Market"]
    return pd.DataFrame(data)


def _build(frame: pd.DataFrame, field):
    return build_persona_sets(
        frame,
        level=LEVEL_BUSINESS_SEGMENT,
        clustering_attributes=["num1"],
        business_segment_field=field,
    )


def test_constants_and_page_functions():
    assert BUSINESS_SEGMENT_FIELD == "segment"
    assert BUSINESS_SEGMENT_FIELD_OPTIONS == ("segment",)
    options = business_segment_field_options()
    assert options == ["segment"]
    assert "segment_label" not in options
    assert len(options) == 1
    assert business_segment_field_for_level("business-segment") == "segment"
    assert business_segment_field_for_level("all") is None
    assert business_segment_field_for_level("campaign") is None


def test_segment_label_raises_actionable_error():
    with pytest.raises(InvalidSegmentFieldError) as info:
        _build(_frame(with_segment=False), "segment_label")
    err = info.value
    assert isinstance(err, ValueError)
    msg = str(err)
    assert "'segment_label'" in msg
    assert "'segment'" in msg
    assert "per client" in msg and "promo" in msg
    assert "is not a column of the joined attribute set (Requirement 3.5)" not in msg


def test_none_field_lists_valid_option():
    with pytest.raises(InvalidSegmentFieldError) as info:
        _build(_frame(), None)
    assert "'segment'" in str(info.value)


def test_bogus_field_names_itself_and_valid_option():
    with pytest.raises(InvalidSegmentFieldError) as info:
        _build(_frame(), "region_typo")
    msg = str(info.value)
    assert "'region_typo'" in msg and "'segment'" in msg


def test_valid_segment_one_set_per_value():
    sets = _build(_frame(), "segment")
    assert [s.group_key for s in sets] == ["Mass", "Mid-Market"]


def test_other_existing_column_still_accepted():
    sets = _build(_frame(), "other")
    assert [s.group_key for s in sets] == ["a", "b", "c"]


def test_all_null_field_error_unchanged():
    frame = _frame()
    frame["segment"] = None
    with pytest.raises(ValueError, match="'segment'") as info:
        _build(frame, "segment")
    assert not isinstance(info.value, InvalidSegmentFieldError)


def test_page_source_no_longer_offers_part3_label():
    text = PAGE_SOURCE.read_text(encoding="utf-8")
    assert 'options=["Customer segment (customer_dna)", "Part 3 segment label"]' not in text
    assert "persona_segment_field" not in text
    assert "Part 3 segment label" not in text


def test_run_personas_segment_label_rejected_on_real_data():
    from webapp_core.personas import PersonaRunSpec, run_personas

    spec = PersonaRunSpec(
        level="business-segment",
        clustering_attributes=["age_band", "total_out"],
        k=3,
        business_segment_field="segment_label",
    )
    with pytest.raises(InvalidSegmentFieldError):
        run_personas(spec)

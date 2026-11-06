"""Unit tests for the Persona page group-selector pure helpers.

Covers (Requirements 3.16-3.19, 6.10) the Streamlit-free helpers in
``app/persona_page.py``: ``group_options`` / ``default_group``,
``scope_result_to_group``, ``scope_export_frame``, ``group_download_filename``,
``group_download_caption``, ``group_lead_counts`` and ``too_small_message``, plus
the per-group Persona_Mix computed via ``webapp_core.personas.persona_mix_by_cell``.

Fixtures are tiny, hand-built synthetic objects (no clustering). Relies on
``tests/conftest.py`` for ``src`` on ``sys.path``.
"""

from __future__ import annotations

import copy
import re

import pandas as pd
import pytest

from app.persona_page import (
    ALL_GROUPS_LABEL,
    default_group,
    group_download_caption,
    group_download_filename,
    group_lead_counts,
    group_options,
    scope_export_frame,
    scope_result_to_group,
    too_small_message,
)
from part5_personas.export import GROUP_COLUMN, PERSONA_LABEL_COLUMN
from part5_personas.grouping import Persona, PersonaSet
from part5_personas.profile import PersonaProfile
from webapp_core.personas import PersonaRunResult, persona_mix_by_cell

GROUPS = ["18-24", "25-34", "55+"]
TOO_SMALL = "55+"


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
def _persona(name: str, label: int) -> Persona:
    profile = PersonaProfile(
        cluster_label=label,
        size=2,
        pct_of_leads=50.0,
        numeric_mean={"income": 1.0},
        numeric_median={"income": 1.0},
        top_categories={"city": [("X", 2)]},
        distinguishing=["income"],
    )
    return Persona(name=name, description=f"{name} desc", actions=["a", "b"], profile=profile)


def _set(key: str, names: list[str], too_small: bool = False) -> PersonaSet:
    personas = [] if too_small else [_persona(n, i) for i, n in enumerate(names)]
    return PersonaSet(
        group_key=key,
        personas=personas,
        k_used=0 if too_small else len(names),
        elbow_costs={} if too_small else {2: 1.0},
        too_small=too_small,
    )


def _make_result() -> PersonaRunResult:
    rows = [
        # (client_id, group, persona_label, promo_id, segment_slug)
        ("c1", "18-24", "A", "P001", "ready_toppers"),
        ("c2", "18-24", "A", "P001", "ready_toppers"),
        ("c3", "18-24", "A", "P001", "ready_toppers"),
        ("c4", "18-24", "B", "P001", "ready_toppers"),
        ("c5", "25-34", "B", "P001", "ready_toppers"),
        ("c6", "25-34", "B", "P001", "ready_toppers"),
        ("c7", "25-34", "B", "P001", "ready_toppers"),
        ("c8", "25-34", "C", "P001", "ready_toppers"),
        ("c9", "25-34", "C", "P002", "not_now"),
    ]
    labels = pd.DataFrame(
        rows,
        columns=["client_id", GROUP_COLUMN, PERSONA_LABEL_COLUMN, "promo_id", "segment_slug"],
    )
    joined = pd.DataFrame(
        {
            "client_id": [r[0] for r in rows] + ["c10"],
            "age_band": [r[1] for r in rows] + ["55+"],
            "income": range(10),
        }
    )
    return PersonaRunResult(
        persona_sets=[
            _set("18-24", ["A", "B"]),
            _set("25-34", ["B", "C"]),
            _set(TOO_SMALL, [], too_small=True),
        ],
        labels=labels,
        joined_attributes=joined,
    )


@pytest.fixture
def result() -> PersonaRunResult:
    return _make_result()


def _label_map(df: pd.DataFrame) -> dict[str, str]:
    return dict(zip(df["client_id"], df[PERSONA_LABEL_COLUMN]))


# --------------------------------------------------------------------------- #
# 1. group_options / default_group                                             #
# --------------------------------------------------------------------------- #
def test_group_options_lists_all_groups_in_order_all_groups_last(result):
    assert group_options(result) == GROUPS + [ALL_GROUPS_LABEL]


def test_group_options_includes_too_small_group(result):
    assert TOO_SMALL in group_options(result)


def test_group_options_empty_for_zero_or_one_set(result):
    zero = PersonaRunResult([], result.labels, result.joined_attributes)
    one = PersonaRunResult([_set("", ["A"])], result.labels, result.joined_attributes)
    assert group_options(zero) == []
    assert group_options(one) == []


def test_default_group_is_first_group(result):
    assert default_group(group_options(result)) == "18-24"


# --------------------------------------------------------------------------- #
# 2. scope_result_to_group                                                     #
# --------------------------------------------------------------------------- #
def test_scope_to_one_group_keeps_only_that_set_and_rows(result):
    scoped = scope_result_to_group(result, "25-34")
    assert [ps.group_key for ps in scoped.persona_sets] == ["25-34"]
    assert set(scoped.labels[GROUP_COLUMN]) == {"25-34"}
    assert len(scoped.labels) == 5
    assert list(scoped.labels.index) == list(range(5))  # index reset
    pd.testing.assert_frame_equal(scoped.joined_attributes, result.joined_attributes)


@pytest.mark.parametrize("selected", [ALL_GROUPS_LABEL, None])
def test_all_groups_or_none_returns_same_object(result, selected):
    assert scope_result_to_group(result, selected) is result


def test_scoping_does_not_mutate_input(result):
    sets_before = copy.deepcopy(result.persona_sets)
    labels_before = result.labels.copy(deep=True)
    joined_before = result.joined_attributes.copy(deep=True)
    for sel in GROUPS + [ALL_GROUPS_LABEL, None]:
        scope_result_to_group(result, sel)
    assert result.persona_sets == sets_before
    pd.testing.assert_frame_equal(result.labels, labels_before)
    pd.testing.assert_frame_equal(result.joined_attributes, joined_before)


def test_scoping_too_small_group_yields_flagged_empty_set(result):
    scoped = scope_result_to_group(result, TOO_SMALL)
    assert len(scoped.persona_sets) == 1
    ps = scoped.persona_sets[0]
    assert ps.group_key == TOO_SMALL
    assert ps.too_small is True
    assert ps.personas == []
    assert scoped.labels.empty


# --------------------------------------------------------------------------- #
# 3. assignments unchanged                                                     #
# --------------------------------------------------------------------------- #
def test_scoped_labels_equal_unscoped_labels_per_client(result):
    full = _label_map(result.labels)
    for g in GROUPS:
        scoped = scope_result_to_group(result, g)
        for cid, lab in _label_map(scoped.labels).items():
            assert full[cid] == lab


def test_union_of_scoped_labels_equals_full_labels(result):
    parts = [scope_result_to_group(result, g).labels for g in GROUPS]
    union = pd.concat(parts, ignore_index=True)
    assert len(union) == len(result.labels)
    assert _label_map(union) == _label_map(result.labels)


def test_sequential_group_selection_never_changes_original(result):
    before = result.labels.copy(deep=True)
    for g in ["25-34", "18-24", TOO_SMALL, "25-34", ALL_GROUPS_LABEL]:
        scope_result_to_group(result, g)
        pd.testing.assert_frame_equal(result.labels, before)
    assert [ps.group_key for ps in result.persona_sets] == GROUPS


# --------------------------------------------------------------------------- #
# 4. mix scoping                                                               #
# --------------------------------------------------------------------------- #
def test_mix_from_scoped_labels_reflects_only_that_group(result):
    cards = [{"promo_id": "P001", "segment": "Ready Toppers"}]
    key = ("P001", "Ready Toppers")

    full_mix = persona_mix_by_cell(result.labels, cards)[key]
    g1 = persona_mix_by_cell(scope_result_to_group(result, "18-24").labels, cards)[key]
    g2 = persona_mix_by_cell(scope_result_to_group(result, "25-34").labels, cards)[key]

    assert g1.available and g2.available and full_mix.available
    assert g1.shares == {"A": 75.0, "B": 25.0}
    assert g2.shares == {"B": 75.0, "C": 25.0}
    assert g1.shares != full_mix.shares
    for mix in (g1, g2, full_mix):
        assert sum(mix.shares.values()) == pytest.approx(100.0)


def test_card_with_no_leads_in_group_is_unavailable(result):
    cards = [{"promo_id": "P002", "segment": "Not Now"}]
    key = ("P002", "Not Now")
    assert persona_mix_by_cell(result.labels, cards)[key].available is True
    in_group = persona_mix_by_cell(scope_result_to_group(result, "25-34").labels, cards)[key]
    assert in_group.available is True
    other = persona_mix_by_cell(scope_result_to_group(result, "18-24").labels, cards)[key]
    assert other.available is False
    assert other.shares == {}


# --------------------------------------------------------------------------- #
# 5. downloads                                                                 #
# --------------------------------------------------------------------------- #
def test_scope_export_frame_keeps_only_selected_group_rows(result):
    out = scope_export_frame(result.labels, "18-24")
    assert set(out[GROUP_COLUMN]) == {"18-24"}
    assert len(out) == 4
    assert list(out.index) == list(range(4))


def test_scope_export_frame_unchanged_for_all_groups_or_no_group_column(result):
    assert scope_export_frame(result.labels, ALL_GROUPS_LABEL) is result.labels
    assert scope_export_frame(result.labels, None) is result.labels
    no_group = result.labels.drop(columns=[GROUP_COLUMN])
    assert scope_export_frame(no_group, "18-24") is no_group


def test_scope_export_frame_too_small_group_is_empty(result):
    assert scope_export_frame(result.labels, TOO_SMALL).empty


def test_download_filename_slug_rule():
    assert group_download_filename("campaign_leads", "Mid-Market") == "campaign_leads_mid-market.csv"
    assert group_download_filename("campaign_leads", "18-24") == "campaign_leads_18-24.csv"
    assert group_download_filename("campaign_leads", "55+") == "campaign_leads_55.csv"
    assert group_download_filename("campaign_leads", "Big Spenders / VIP") == "campaign_leads_big-spenders-vip.csv"
    assert group_download_filename("campaign_leads", "") == "campaign_leads_group.csv"


def test_download_filename_all_groups():
    assert group_download_filename("campaign_leads", ALL_GROUPS_LABEL) == "campaign_leads.csv"
    assert group_download_filename("campaign_leads", None) == "campaign_leads.csv"


def test_download_caption_for_group_states_group_and_count():
    cap = group_download_caption("18-24", 1234)
    assert "18-24" in cap
    assert "1,234" in cap


def test_download_caption_for_all_groups_mentions_all_groups():
    cap = group_download_caption(ALL_GROUPS_LABEL, 9)
    assert "all groups" in cap.lower()
    assert "9" in cap


def test_download_caption_zero_rows_says_nothing_to_export_too_small():
    cap = group_download_caption(TOO_SMALL, 0)
    assert "no personas to export" in cap
    assert "too small" in cap
    assert TOO_SMALL in cap


# --------------------------------------------------------------------------- #
# 6. group_lead_counts / too_small_message                                     #
# --------------------------------------------------------------------------- #
def test_group_lead_counts_single_column():
    df = pd.DataFrame({"a": ["x", "x", "y"]})
    assert group_lead_counts(df, ["a"]) == {"x": 2, "y": 1}


def test_group_lead_counts_multi_column_uses_pipe_keys_and_sums_to_non_null_rows():
    df = pd.DataFrame(
        {
            "a": ["x", "x", "y", "y", None, "x"],
            "b": ["p", "p", "q", "p", "q", None],
        }
    )
    counts = group_lead_counts(df, ["a", "b"])
    assert counts == {"x | p": 2, "y | q": 1, "y | p": 1}
    assert sum(counts.values()) == len(df.dropna(subset=["a", "b"]))


def test_group_lead_counts_empty_without_columns():
    assert group_lead_counts(pd.DataFrame({"a": [1, 2]}), []) == {}


def test_too_small_message_with_count_includes_number():
    msg = too_small_message("Tiny", 12)
    assert "12" in msg
    assert "Tiny" in msg


def test_too_small_message_without_count_has_no_digits_and_guides_user():
    msg = too_small_message("Tiny", None)
    assert not re.search(r"\d", msg)
    assert "Pick a larger segment" in msg

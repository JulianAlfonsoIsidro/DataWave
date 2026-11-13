"""Part 9 round 3: the AI features (spec part9-layout-fixes, Requirements 29 to 40).

Answer layout (Hypothesis), masking and the privacy guard, token usage,
renaming personas without moving a cluster, the run summary's privacy, the
fairness shares and the number check.
"""

from __future__ import annotations

import json
import re
import types

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ai import assistant, bedrock
from ai.answer_format import (
    MAX_WORDS,
    format_answer,
    unsupported_numbers,
    word_count,
)
from ai.mocks import mock_assistant_answer
from ai.privacy import mask_pii, masked_note
from part5_personas.grouping import Persona, PersonaSet
from webapp_core import ai_usage, fairness
from webapp_core.personas import PersonaRunResult, naming_source, rename_personas
from webapp_core.run_summary import run_summary

ENV = {k: "x" for k in bedrock.REQUIRED_ENV}

# --- answer layout (Requirement 29) ------------------------------------------

word = st.text(alphabet="abcdefghij", min_size=1, max_size=8)
sentence = st.lists(word, min_size=1, max_size=14).map(lambda ws: " ".join(ws).capitalize() + ".")
bullets = st.lists(sentence, min_size=0, max_size=12)


def _reply(lead, items, style):
    marks = {"dash": "- ", "star": "* ", "num": "1. "}
    body = "\n".join(marks[style] + b for b in items)
    return lead + ("\n\n" + body if body else "")


@settings(deadline=None, max_examples=150)
@given(sentence, bullets, st.sampled_from(["dash", "star", "num"]))
def test_format_answer_caps_words_by_whole_bullets_and_is_idempotent(lead, items, style):
    text = _reply(lead, items, style)
    out = format_answer(text)
    assert word_count(out) <= MAX_WORDS
    assert format_answer(out) == out                       # idempotent
    kept = [ln[2:] for ln in out.split("\n") if ln.startswith("- ")]
    for b in kept:                                         # never cuts a bullet
        assert b in items
    assert kept == items[: len(kept)]                      # keeps order, stops at the cap
    if len(kept) >= 2:
        assert "\n- " in out                               # line breaks survive


@settings(deadline=None, max_examples=60)
@given(st.text(min_size=0, max_size=600))
def test_format_answer_never_crashes_and_leaves_no_underscores(text):
    out = format_answer(text + " p_join min_adb some_code")
    assert "_" not in out
    assert word_count(out) <= MAX_WORDS


def test_format_answer_turns_prose_tables_and_headings_into_the_layout():
    raw = "## Summary\nThe offer is clear. It targets Mass clients. Channels are SMS and email.\n| a | b |\n|---|---|\n| 1 | 2 |"
    out = format_answer(raw)
    lines = out.split("\n")
    assert lines[0] == "Summary"
    assert "#" not in out and "|" not in out
    assert "- The offer is clear." in out


def test_demo_and_bedrock_text_share_one_layout():
    form = {"product_type": "Savings", "reward": "Bonus interest", "threshold_value": 530000,
            "channels": ["SMS"], "eligible_segments": ["Mass"], "min_adb": 0}
    demo = format_answer(mock_assistant_answer("Summarize This Campaign", form, {}, []))
    bedrock_like = format_answer("Here is the campaign.\n\n* Product: Savings.\n* Reward: Bonus interest.\n* Channels: SMS.")
    for out in (demo, bedrock_like):
        lead, _, body = out.partition("\n\n")
        assert lead and not lead.startswith("- ")
        assert all(ln.startswith("- ") for ln in body.split("\n") if ln.strip())


def test_drafts_are_quoted_with_channel_and_character_count():
    form = {"product_type": "Savings", "reward": "Bonus interest", "threshold_value": 530000}
    for q, channel in (("Draft An SMS For This Offer", "SMS"), ("Draft an email", "Email"),
                       ("Write an in-app message", "In-app")):
        out = format_answer(mock_assistant_answer(q, form, {}, []))
        cap = re.search(rf"- {channel} draft, (\d+) characters:", out)
        assert cap, out
        quote = next(ln for ln in out.split("\n") if ln.startswith("> "))[2:]
        assert len(quote) == int(cap.group(1))


def test_missing_answer_lists_one_bullet_per_gap():
    gaps = ["No control group stated", "Needs Input: timeline"]
    out = format_answer(mock_assistant_answer("What's missing?", {}, {}, gaps))
    assert out.count("\n- ") == 2 and "control group" in out and "timeline" in out


# --- the assistant sees the run (Requirement 30) -----------------------------

def _run():
    cards = [
        {"segment": "Ready Toppers", "n_clients": 347, "excluded_by_reason": {"freq": 34},
         "control_count": 31, "sendable_count": 282, "expected_joiners": 87.3,
         "action": "Prioritize", "dominant_channel": "In-app", "message_angle": "Top up now"},
        {"segment": "Not Now", "n_clients": 947, "excluded_by_reason": {"dnb": 151},
         "control_count": 79, "sendable_count": 717, "expected_joiners": 38.8,
         "action": "Include", "dominant_channel": "In-app", "message_angle": "Stay with us"},
    ]
    return types.SimpleNamespace(cards=cards, sendable_by_segment={})


def test_run_summary_is_aggregate_and_passes_the_privacy_guard():
    summary = run_summary(_run(), threshold_label="₱530,000", impact={"messages_saved": 175})
    bedrock.assert_private(summary)                     # raises if not aggregate
    text = json.dumps(summary)
    assert "client_id" not in text and not re.search(r"\bC\d{5,}\b", text)
    assert summary["act_first_segments"] == ["Ready Toppers"]
    assert summary["totals"]["sendable"] == 999


def test_results_questions_use_the_run_and_one_client_questions_are_refused(tmp_path):
    g = assistant.CampaignGrounding(form={}, tags={}, context={}, document_text="",
                                    run=run_summary(_run(), threshold_label="₱530,000"))
    res = assistant.answer("Which segment should I act on first?", g, env={}, log_path=tmp_path / "l")
    assert res.mode == "Demo" and "Ready Toppers" in res.text and "282" in res.text
    assert "run_summary" in res.fields_sent
    assert assistant.route("What is the score of client 1042?") == "model_results"
    none = assistant.CampaignGrounding(form={}, tags={}, context={}, document_text="")
    res2 = assistant.answer("Which segment is best?", none, env={}, log_path=tmp_path / "l")
    assert "Run Analysis" in res2.text


# --- number check (Requirement 37.5) -----------------------------------------

def test_unsupported_numbers_flags_invented_figures_only():
    payload = {"run_summary": {"sendable": 282, "expected_joiners": 87.3}}
    text = "About 87 of 282 leads may join. Expect 3,400 extra sign-ups.\n- SMS draft, 94 characters:"
    assert unsupported_numbers(text, payload) == ["3400"]


# --- masking and the privacy guard (Requirements 37.2, 40.2) ------------------

emails = st.from_regex(r"[a-z]{3,8}\.[a-z]{2,6}@[a-z]{3,8}\.(com|ph)", fullmatch=True)
amounts = st.integers(1_000, 9_999_999).map(lambda n: f"PHP {n:,}")


@settings(deadline=None, max_examples=80)
@given(emails, amounts, st.integers(10**9, 10**15))
def test_mask_pii_masks_contacts_and_ids_but_keeps_amounts(email, amount, long_number):
    text = f"Contact {email} or 0917 123 4567. Account {long_number}. Top up {amount}."
    res = mask_pii(text)
    assert email not in res.text and str(long_number) not in res.text
    assert "0917 123 4567" not in res.text
    assert amount in res.text
    assert res.counts["email"] == 1 and res.counts["phone"] == 1 and res.counts["number"] >= 1
    bedrock.assert_private({"document_text": res.text})   # masked text is allowed


def test_masked_note_and_guard_still_block_client_ids():
    assert masked_note(mask_pii("no details here")).startswith("No phone numbers")
    with pytest.raises(bedrock.PayloadRejected):
        bedrock.assert_private({"document_text": "Client C100245 joined"})


# --- token usage (Requirement 33) ---------------------------------------------

class _Client:
    def __init__(self, text, usage):
        self.text, self.usage, self.kwargs = text, usage, None

    def converse(self, **kwargs):
        self.kwargs = kwargs
        return {"output": {"message": {"content": [{"text": self.text}]}}, "usage": self.usage}


def test_converse_reads_usage_and_sends_max_tokens():
    client = _Client("Hello.", {"inputTokens": 412, "outputTokens": 96, "totalTokens": 508})
    res = bedrock.converse("sys", {"q": "x"}, client=client, env=ENV, max_tokens=400)
    assert res.mode == "Bedrock"
    assert (res.usage.input_tokens, res.usage.output_tokens, res.usage.total_tokens) == (412, 96, 508)
    assert client.kwargs["inferenceConfig"] == {"maxTokens": 400}
    bad = bedrock.converse("sys", {"q": "x"}, client=_Client("not json", {"inputTokens": 5, "outputTokens": 2}),
                           env=ENV, expect_json=True)
    assert bad.mode == "Demo" and bad.usage.total_tokens == 7   # spent tokens still counted


def test_usage_records_line_totals_and_cap():
    rec = ai_usage.record_from(ai_usage.FEATURE_ASSISTANT, "Bedrock",
                               bedrock.Usage(412, 96, 508), 1.2)
    assert ai_usage.usage_line(rec) == "Input 412 | Output 96 | Total 508 tokens"
    demo = ai_usage.record_from(ai_usage.FEATURE_ASSISTANT, "Demo", None, 0, "no_credentials")
    assert "0 tokens" in ai_usage.usage_line(demo)
    totals = {t.feature: t for t in ai_usage.session_totals([rec, demo])}
    assert totals[ai_usage.FEATURE_ASSISTANT].bedrock_calls == 1
    assert totals[ai_usage.FEATURE_ASSISTANT].reasons == ("no AI service credentials are set",)
    assert ai_usage.cap_reached([rec], cap=500) and not ai_usage.cap_reached([rec], cap=509)
    assert ai_usage.estimate_line(640) == "Input about 640 tokens (estimated)"


# --- renaming keeps every cluster (Requirement 31.4) --------------------------

class _CountingNamer:
    def __init__(self, prefix):
        self.prefix, self.n = prefix, 0

    def name(self, profile, taken):
        self.n += 1
        return {"name": f"{self.prefix} {self.n}", "description": "D.", "actions": ["SMS: a", "Email: b"],
                "difference": "x"}


def _persona_result():
    sets = []
    rows = []
    for group in ("NCR", "Luzon"):
        personas = []
        for i in range(3):
            profile = types.SimpleNamespace(size=10 + i)
            personas.append(Persona(name=f"{group} Old {i}", description="", actions=[], profile=profile))
            rows += [{"client_id": f"{group}{i}{j}", "group": group, "persona_label": f"{group} Old {i}"}
                     for j in range(10 + i)]
        sets.append(PersonaSet(group_key=group, personas=personas, k_used=3, elbow_costs={}, too_small=False))
    sets.append(PersonaSet(group_key="Tiny", personas=[], k_used=0, elbow_costs={}, too_small=True))
    return PersonaRunResult(persona_sets=sets, labels=pd.DataFrame(rows),
                            joined_attributes=pd.DataFrame(), narration_source="Built-in")


def test_rename_personas_keeps_every_lead_and_group_size():
    before = _persona_result()
    after = rename_personas(before, _CountingNamer("New"), source="Bedrock")
    assert after.narration_source == "Bedrock"
    for old_set, new_set in zip(before.persona_sets, after.persona_sets):
        assert [p.profile for p in old_set.personas] == [p.profile for p in new_set.personas]
    old_sizes = before.labels.groupby(["group", "persona_label"]).size().sort_index().tolist()
    new_sizes = after.labels.groupby(["group", "persona_label"]).size().sort_index().tolist()
    assert sorted(old_sizes) == sorted(new_sizes)
    assert list(before.labels["client_id"]) == list(after.labels["client_id"])
    names = {p.name for s in after.persona_sets for p in s.personas}
    assert set(after.labels["persona_label"]) == names


def test_naming_source_is_accurate():
    assert naming_source([{"mode": "Bedrock"}, {"mode": "Bedrock"}]) == "Bedrock"
    assert naming_source([{"mode": "Demo"}]) == "Demo"
    assert naming_source([{"mode": "Bedrock"}, {"mode": "Demo"}]) == "Mixed"


# --- fairness and forecast caution (Requirement 38) ---------------------------

def test_group_shares_add_to_100_and_flag_large_moves():
    dna = pd.DataFrame({"client_id": [f"c{i}" for i in range(10)],
                        "region": ["NCR"] * 5 + ["Luzon"] * 5})
    shares = fairness.group_shares(dna, dna["client_id"], ["c0", "c1", "c2", "c3", "c5"], "region")
    assert round(sum(s.eligible_pct for s in shares)) == 100
    assert round(sum(s.sendable_pct for s in shares)) == 100
    ncr = next(s for s in shares if s.group == "NCR")
    assert ncr.flagged and round(ncr.gap_pts) == 30


def test_forecast_caution_only_when_far_above_history():
    assert fairness.forecast_caution(204.4, 1595, 0.0783) is None          # 12.8% vs 7.8%
    note = fairness.forecast_caution(400, 1595, 0.0783)
    assert note and "25.1%" in note and "7.8%" in note

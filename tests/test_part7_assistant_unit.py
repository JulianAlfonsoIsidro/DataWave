"""Unit tests for the campaign assistant (Requirements 3.3-3.8, 3.10-3.12).

Fake clients only: no network and no Streamlit. Logs go to ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai import assistant
from ai.assistant import (
    MAX_ANSWER_WORDS,
    MODEL_RESULTS_MESSAGE,
    OFF_TOPIC_MESSAGE,
    QUESTION_LENGTH_MESSAGE,
    SUGGESTED_QUESTIONS,
    CampaignGrounding,
    answer,
    missing_items,
    route,
    truncate_words,
    validate_question,
)

ENV = {
    "AWS_ACCESS_KEY_ID": "test-id",
    "AWS_SECRET_ACCESS_KEY": "test-secret",
    "AWS_REGION": "us-east-1",
    "BEDROCK_MODEL_ID": "test-model",
}


class FakeClient:
    """Records calls and returns a fixed Converse-shaped response."""

    def __init__(self, text: str = "Fake model answer.") -> None:
        self.text = text
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def _grounding(**overrides) -> CampaignGrounding:
    base = dict(
        form={"product_type": "Time Deposit", "channels": ["SMS"]},
        tags={},
        context={},
        document_text="",
    )
    base.update(overrides)
    return CampaignGrounding(**base)


# --- Requirement 3.6: question validation edges ---------------------------


@pytest.mark.parametrize("q", ["", " ", "   \t\n", "x" * 501])
def test_validate_question_rejects_bad_lengths(q):
    assert validate_question(q) == QUESTION_LENGTH_MESSAGE


@pytest.mark.parametrize("q", ["x", "x" * 500])
def test_validate_question_accepts_1_and_500(q):
    assert validate_question(q) is None


def test_invalid_question_makes_no_call_and_no_log(tmp_path):
    client = FakeClient()
    log = tmp_path / "log.jsonl"
    for q in ("", "   ", "x" * 501):
        with pytest.raises(ValueError):
            answer(q, _grounding(), client=client, env=ENV, log_path=log)
    assert client.calls == 0
    assert not log.exists()


# --- Requirements 3.4, 3.5: routing ---------------------------------------


def test_route_model_results_questions():
    for q in ("What is the score of client 1?", "Show me the segments", "Describe the personas"):
        assert route(q) == "model_results"


def test_route_off_topic():
    assert route("What is the weather today?") == "off_topic"


def test_route_campaign():
    assert route("Is the offer clear?") == "campaign"


def test_model_results_and_off_topic_answers_are_local_without_call(tmp_path):
    client = FakeClient()
    log = tmp_path / "log.jsonl"
    r1 = answer("Which segments are best?", _grounding(), client=client, env=ENV, log_path=log)
    r2 = answer("Tell me a joke", _grounding(), client=client, env=ENV, log_path=log)
    assert (r1.text, r1.mode) == (MODEL_RESULTS_MESSAGE, "Local")
    assert (r2.text, r2.mode) == (OFF_TOPIC_MESSAGE, "Local")
    assert "Results page" in MODEL_RESULTS_MESSAGE and "Personas page" in MODEL_RESULTS_MESSAGE
    assert client.calls == 0


# --- Requirement 3.3: missing_items ---------------------------------------


def test_missing_items_all_three_kinds():
    g = _grounding(tags={"timeline": "Needs Input", "reward": "Extracted"})
    items = missing_items(g)
    assert items == [
        "Channel listed without a budget: SMS",
        "No control group stated",
        "Needs Input: timeline",
    ]


def test_missing_items_none_when_budget_and_control_present():
    g = _grounding(
        context={"offer_details": "Budget of ₱ 500000; control group of 10%"},
    )
    assert missing_items(g) == []


def test_missing_items_no_channels_skips_budget_item():
    g = _grounding(form={"channels": []}, document_text="holdout group")
    assert missing_items(g) == []


# --- Requirement 3.8: suggested questions ---------------------------------


def test_four_suggested_questions_exact_labels():
    assert SUGGESTED_QUESTIONS == (
        "Summarize This Campaign",
        "What's Missing From This Proposal?",
        "Draft An SMS For This Offer",
        "Is The Eligibility Clear?",
    )


@pytest.mark.parametrize("label", SUGGESTED_QUESTIONS)
def test_suggested_label_is_valid_campaign_question(label):
    assert validate_question(label) is None
    assert route(label) == "campaign"


def test_suggested_label_treated_as_submitted_question(tmp_path):
    client = FakeClient("Summary text.")
    log = tmp_path / "log.jsonl"
    res = answer(SUGGESTED_QUESTIONS[0], _grounding(), client=client, env=ENV, log_path=log)
    assert res.mode == "Bedrock" and client.calls == 1
    assert json.loads(log.read_text().splitlines()[0])["question"] == SUGGESTED_QUESTIONS[0]


# --- Requirement 3.7: 150-word truncation ---------------------------------


def test_truncate_words_boundaries():
    at_limit = " ".join(["w"] * MAX_ANSWER_WORDS)
    over = " ".join(["w"] * (MAX_ANSWER_WORDS + 1))
    assert len(truncate_words(at_limit).split()) == MAX_ANSWER_WORDS
    assert len(truncate_words(over).split()) == MAX_ANSWER_WORDS


def test_long_model_answer_is_truncated(tmp_path):
    client = FakeClient(" ".join(["word"] * 400))
    res = answer("Summarize the offer", _grounding(), client=client, env=ENV, log_path=tmp_path / "l.jsonl")
    assert res.mode == "Bedrock"
    assert len(res.text.split()) == MAX_ANSWER_WORDS


# --- Requirement 3.10: log line validity ----------------------------------


def test_log_line_is_valid_json_and_creates_directory(tmp_path):
    log = tmp_path / "nested" / "scratch" / "assistant_log.jsonl"
    client = FakeClient("Hello there.")
    r1 = answer("Summarize the offer", _grounding(), client=client, env=ENV, log_path=log)
    r2 = answer("Is the eligibility clear?", _grounding(), client=client, env=ENV, log_path=log)
    assert r1.log_saved and r2.log_saved
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert set(rec) == {"question", "answer", "timestamp"}
    assert rec["question"] == "Summarize the offer"
    assert rec["answer"] == "Hello there."
    from datetime import datetime

    datetime.fromisoformat(rec["timestamp"])


def test_default_log_path_is_under_scratch():
    assert assistant.LOG_PATH.parent.name == "scratch"
    assert assistant.LOG_PATH.name == "assistant_log.jsonl"


# --- Requirement 3.11: log failure still answers --------------------------


def test_log_failure_still_returns_answer(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    log: Path = blocker / "sub" / "log.jsonl"  # parent cannot be created
    client = FakeClient("Still answered.")
    res = answer("Summarize the offer", _grounding(), client=client, env=ENV, log_path=log)
    assert res.text == "Still answered."
    assert res.log_saved is False


# --- Requirement 3.12 / 3.9: no call without credentials or invalid input --


def test_no_credentials_uses_demo_mock_without_client_call(tmp_path):
    client = FakeClient()
    res = answer("Summarize this campaign", _grounding(), client=client, env={}, log_path=tmp_path / "l.jsonl")
    assert res.mode == "Demo"
    assert client.calls == 0
    assert res.text


def test_empty_campaign_demo_answer_makes_no_call(tmp_path):
    empty = CampaignGrounding(form={}, tags={}, context={}, document_text="")
    client = FakeClient()
    res = answer("Summarize This Campaign", empty, client=client, env={}, log_path=tmp_path / "l.jsonl")
    assert client.calls == 0
    assert res.mode == "Demo"
    assert "not enough campaign detail" in res.text

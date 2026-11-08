"""Unit and property tests for the campaign assistant (Requirements 3.1-3.13)."""

from __future__ import annotations

import json

from hypothesis import given, settings, strategies as st

from ai import assistant
from ai.assistant import CampaignGrounding

GROUND = CampaignGrounding(
    form={"product_type": "Savings", "channels": ["SMS"], "reward": "Bonus interest"},
    tags={"min_adb": "Needs Input"},
    context={"timeline": "June to July"},
    document_text="Savings promo.",
)


class FailingClient:
    def converse(self, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("Bedrock must not be called")


def test_validate_question_bounds():
    assert assistant.validate_question("") is not None
    assert assistant.validate_question("   ") is not None
    assert assistant.validate_question("x" * 501) is not None
    assert assistant.validate_question("x") is None
    assert assistant.validate_question("x" * 500) is None


def test_route():
    assert assistant.route("What is the score for this segment?") == "model_results"
    assert assistant.route("What's the weather?") == "off_topic"
    for q in assistant.SUGGESTED_QUESTIONS:
        assert assistant.route(q) == "campaign"


def test_missing_items():
    items = assistant.missing_items(GROUND)
    assert any("without a budget" in i for i in items)
    assert "No control group stated" in items
    assert any("min adb" in i for i in items)


def test_answer_demo_logs_and_log_failure(tmp_path):
    log = tmp_path / "scratch" / "log.jsonl"
    res = assistant.answer("What's Missing From This Proposal?", GROUND, env={}, log_path=log)
    assert res.mode == "Demo" and res.log_saved
    row = json.loads(log.read_text().splitlines()[0])
    assert set(row) == {"question", "answer", "timestamp"}

    blocker = tmp_path / "file"
    blocker.write_text("x")
    bad = assistant.answer("Summarize This Campaign", GROUND, env={}, log_path=blocker / "l.jsonl")
    assert bad.log_saved is False and bad.text


def test_routed_answers_make_no_model_call(tmp_path):
    res = assistant.answer(
        "Show persona scores", GROUND, client=FailingClient(),
        env={k: "x" for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION", "BEDROCK_MODEL_ID")},
        log_path=tmp_path / "l.jsonl",
    )
    assert res.mode == "Local" and res.text == assistant.MODEL_RESULTS_MESSAGE


@settings(deadline=None, max_examples=50)
@given(st.text(alphabet="abc \n", max_size=1000), st.integers(0, 200))
def test_truncate_words_never_exceeds_limit(text, limit):
    assert len(assistant.truncate_words(text, limit).split()) <= limit

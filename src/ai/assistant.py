"""Campaign-only assistant (Requirements 3.1-3.7, 3.9-3.11, 3.13).

Answers questions about the current campaign proposal, grounded only on the
form fields, the uploaded document text, and the Campaign_Context. Model
scores, segments, and personas never enter the payload. Every answer goes
through the shared Bedrock client (``ai.bedrock.converse``) and falls back to
a templated Mock in Demo Mode. No Streamlit imports.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ai import bedrock
from ai.mocks import CONTEXT_KEYS, mock_assistant_answer

MAX_QUESTION_CHARS = 500
MAX_ANSWER_WORDS = 150
LOG_PATH = Path(__file__).resolve().parents[2] / "scratch" / "assistant_log.jsonl"

SUGGESTED_QUESTIONS: tuple[str, ...] = (
    "Summarize This Campaign",
    "What's Missing From This Proposal?",
    "Draft An SMS For This Offer",
    "Is The Eligibility Clear?",
)

QUESTION_LENGTH_MESSAGE = "Please enter a question of 1 to 500 characters."
MODEL_RESULTS_MESSAGE = (
    "I can't answer questions about model scores, segments, or personas. "
    "Please see the Results page or the Personas page."
)
OFF_TOPIC_MESSAGE = "I only answer questions about the current campaign proposal."

_MODEL_RE = re.compile(
    r"\bscores?\b|\bscoring\b|segment|persona|\bmodel\b|probabilit|p_join|propensity",
    re.I,
)
_CAMPAIGN_RE = re.compile(
    r"offer|mechanic|eligib|channel|timeline|copy|\bsms\b|e-?mail|in-?app|draft|"
    r"summar|missing|\bgaps?\b|clear|proposal|campaign|reward|threshold|promo|"
    r"message|messaging|compliance|budget|control|audience|objective|product|"
    r"inconsisten|qualif|adb|balance|top-?up|deposit",
    re.I,
)
_BUDGET_RE = re.compile(r"budget|cost\s+cap|spend\s+cap|₱\s?\d|php\s?\d", re.I)
_CONTROL_RE = re.compile(r"control\s+group|holdout|hold-out|control\s+cell", re.I)

SYSTEM_PROMPT = (
    "You are a campaign assistant for a retail bank. Answer only about the "
    "campaign proposal provided: offer, mechanic, eligibility, channels, "
    "timeline, messaging, copy, compliance, clarity, and gaps. Use only the "
    "provided form fields, context, and document text. Never discuss model "
    "scores, segments, or personas. When asked what is missing, list: a "
    "channel listed without a budget, no control group stated, and any field "
    "tagged Needs Input. Answer in at most 150 words, in plain text."
)


@dataclass(frozen=True)
class CampaignGrounding:
    """Everything the assistant may use. Form fields only; no model results."""

    form: Mapping[str, Any]
    tags: Mapping[str, str]
    context: Mapping[str, str]
    document_text: str


@dataclass(frozen=True)
class AssistantAnswer:
    """An answer; ``Local`` means a routed message with no model or Mock."""

    text: str
    mode: Literal["Bedrock", "Demo", "Local"]
    log_saved: bool


def validate_question(q: str) -> str | None:
    """Return an error message, or None when ``q`` is 1 to 500 characters."""
    if not isinstance(q, str) or not q.strip() or len(q) > MAX_QUESTION_CHARS:
        return QUESTION_LENGTH_MESSAGE
    return None


def route(q: str) -> Literal["model_results", "off_topic", "campaign"]:
    """Route a question. Suggested-question labels always go to campaign."""
    if q.strip() in SUGGESTED_QUESTIONS:
        return "campaign"
    if _MODEL_RE.search(q):
        return "model_results"
    if _CAMPAIGN_RE.search(q):
        return "campaign"
    return "off_topic"


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != ()


def missing_items(g: CampaignGrounding) -> list[str]:
    """Deterministic gap list (Requirement 3.3)."""
    items: list[str] = []
    searchable = " ".join(
        [g.document_text or ""] + [str(g.context.get(k) or "") for k in CONTEXT_KEYS]
    )
    channels = g.form.get("channels") or []
    if _has_value(channels) and not _BUDGET_RE.search(searchable):
        items.append("Channel listed without a budget: " + ", ".join(map(str, channels)))
    if not _CONTROL_RE.search(searchable):
        items.append("No control group stated")
    for name in sorted(k for k, v in g.tags.items() if v == "Needs Input"):
        items.append(f"Needs Input: {name.replace('_', ' ')}")
    return items


def truncate_words(text: str, limit: int = MAX_ANSWER_WORDS) -> str:
    """Keep at most ``limit`` whitespace-separated words."""
    words = text.split()
    if len(words) <= limit:
        return text.strip()
    return " ".join(words[:limit])


def _append_log(path: Path, question: str, answer_text: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "question": question,
                "answer": answer_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return True
    except Exception:
        return False


def answer(
    q: str,
    g: CampaignGrounding,
    *,
    client: Any | None = None,
    env: Mapping[str, str] | None = None,
    log_path: Path = LOG_PATH,
) -> AssistantAnswer:
    """Answer ``q`` and log it. Invalid questions raise ``ValueError``.

    Invalid questions (Requirement 3.6) make no Bedrock call and no log write;
    callers should check :func:`validate_question` first and show its message.
    """
    error = validate_question(q)
    if error is not None:
        raise ValueError(error)

    routed = route(q)
    if routed == "model_results":
        text, mode = MODEL_RESULTS_MESSAGE, "Local"
    elif routed == "off_topic":
        text, mode = OFF_TOPIC_MESSAGE, "Local"
    else:
        gaps = missing_items(g)
        payload = {
            "question": q,
            "form_fields": dict(g.form),
            "field_tags": dict(g.tags),
            "context": dict(g.context),
            "document_text": g.document_text,
            "known_gaps": gaps,
        }
        result = bedrock.converse(SYSTEM_PROMPT, payload, client=client, env=env)
        if result.mode == "Bedrock" and result.text:
            text, mode = truncate_words(result.text), "Bedrock"
        else:
            text = mock_assistant_answer(q, g.form, g.context, gaps)
            mode = "Demo"

    text = truncate_words(text)
    return AssistantAnswer(text=text, mode=mode, log_saved=_append_log(log_path, q, text))

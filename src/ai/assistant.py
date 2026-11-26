"""Campaign assistant (Requirements 3.1-3.7, 3.9-3.11, 3.13; Part 9 round 3).

Answers questions about the current campaign proposal and, once a run exists,
its results. It is grounded on the form fields, the uploaded document text,
the Campaign_Context and (Part 9 round 3, Requirement 30) the aggregate
Run_Summary: segment totals, actions, expected joiners, the Impact Summary and
persona names. It never sees per-client data, and questions about one client
are refused. Every answer goes through the shared Bedrock client
(``ai.bedrock.converse``) and falls back to a templated Mock in Demo Mode.
Both are put in one answer layout by ``ai.answer_format`` (Requirement 29).
No Streamlit imports.
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
from ai.answer_format import format_answer, unsupported_numbers
from ai.mocks import CONTEXT_KEYS, mock_assistant_answer

MAX_QUESTION_CHARS = 500
MAX_ANSWER_WORDS = 150
MAX_REPLY_TOKENS = 3000  # inferenceConfig.maxTokens; reasoning tokens count against it (was 1500; benchmark showed cut-offs)
LOG_PATH = Path(__file__).resolve().parents[2] / "scratch" / "assistant_log.jsonl"

SUGGESTED_QUESTIONS: tuple[str, ...] = (
    "Summarize This Campaign",
    "What's Missing From This Proposal?",
    "Draft An SMS For This Offer",
    "Is The Eligibility Clear?",
)

QUESTION_LENGTH_MESSAGE = "Please enter a question of 1 to 500 characters."
# Part 9 round 3 (Requirement 30.4): only questions about one client are
# refused; segments, personas and the forecast are answered from the run.
MODEL_RESULTS_MESSAGE = (
    "I work with totals, so I can't look up one client. Ask about a segment, "
    "a persona or the whole run instead, or see the Results page or the "
    "Personas page for the lead files."
)
OFF_TOPIC_MESSAGE = "I only answer questions about the current campaign proposal."

# One client: an id, "this client/customer/person", or a score "of client".
_MODEL_RE = re.compile(
    r"\bC\d{4,}\b|\bclient\s*(?:id|#|no\.?|number)?\s*\d+|"
    r"\b(?:this|that|one|a single|an individual|each)\s+(?:client|customer|person|lead)\b|"
    r"\bscore\s+(?:of|for)\s+(?:client|customer|lead)",
    re.I,
)
_RESULTS_RE = re.compile(
    r"segment|persona|result|forecast|joiner|sendable|\bleads?\b|act first|"
    r"prioriti|recommend|not contacted|impact|messages saved|cost saved|"
    r"expected|scores?\b|model",
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
    "You are a campaign assistant for a retail bank's CRM team. Answer only "
    "about the campaign proposal and the run results provided: offer, "
    "mechanic, eligibility, channels, timeline, messaging, copy, compliance, "
    "gaps, segments, personas, expected joiners and the impact figures. Use "
    "only the form fields, context, document text and run_summary given. "
    "Never invent a number: every figure must appear in the input. If "
    "run_summary is empty, say to press Run Analysis first. Never discuss a "
    "single client. When asked what is missing, list each known gap. "
    "Layout, always: one short lead sentence, a blank line, then 3 to 6 plain "
    "hyphen bullets, one idea each. For a drafted SMS, email or in-app "
    "message, put a bullet naming the channel and its character count, then "
    "the message on its own line starting with '> '. No headings, no tables, "
    "no bold, no field names with underscores. At most 150 words."
)


@dataclass(frozen=True)
class CampaignGrounding:
    """Everything the assistant may use. Form fields only; no model results."""

    form: Mapping[str, Any]
    tags: Mapping[str, str]
    context: Mapping[str, str]
    document_text: str
    run: Mapping[str, Any] | None = None   # Run_Summary (Part 9 round 3)


@dataclass(frozen=True)
class AssistantAnswer:
    """An answer; ``Local`` means a routed message with no model or Mock."""

    text: str
    mode: Literal["Bedrock", "Demo", "Local"]
    log_saved: bool
    usage: Any = None                  # ai.bedrock.Usage when Bedrock answered
    seconds: float = 0.0
    reason: str = ""                   # fallback code when not Bedrock
    flagged: tuple[str, ...] = ()      # figures not found in the payload
    fields_sent: tuple[str, ...] = ()  # payload parts sent (for "What The AI Used")


def validate_question(q: str) -> str | None:
    """Return an error message, or None when ``q`` is 1 to 500 characters."""
    if not isinstance(q, str) or not q.strip() or len(q) > MAX_QUESTION_CHARS:
        return QUESTION_LENGTH_MESSAGE
    return None


def route(q: str) -> Literal["model_results", "off_topic", "campaign"]:
    """Route a question. Suggested-question labels always go to campaign.

    ``model_results`` now means a question about one client (refused);
    questions about segments, personas and the forecast go to ``campaign``.
    """
    if q.strip() in SUGGESTED_QUESTIONS:
        return "campaign"
    if _MODEL_RE.search(q):
        return "model_results"
    if _CAMPAIGN_RE.search(q) or _RESULTS_RE.search(q):
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
    """Keep at most ``limit`` words, keeping line breaks (Part 9 round 3).

    The old version rejoined the words with single spaces, which destroyed
    the answer's line breaks; answers now go through
    :func:`ai.answer_format.format_answer`, which caps by whole bullets.
    """
    words = text.split()
    if len(words) <= limit:
        return text.strip()
    kept, count = [], 0
    for line in text.strip().split("\n"):
        n = len(line.split())
        if count + n > limit:
            room = limit - count
            if room > 0:
                kept.append(" ".join(line.split()[:room]))
            break
        kept.append(line)
        count += n
    return "\n".join(kept).strip()


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


def build_payload(q: str, g: CampaignGrounding) -> dict[str, Any]:
    """What one question sends: the form, tags, context, document, gaps and run."""
    return {
        "question": q,
        "form_fields": dict(g.form),
        "field_tags": dict(g.tags),
        "context": dict(g.context),
        "document_text": g.document_text,
        "known_gaps": missing_items(g),
        "run_summary": dict(g.run) if g.run else {},
    }


def estimated_input_tokens(q: str, g: CampaignGrounding) -> int:
    """The input estimate shown while the call runs (labelled an estimate)."""
    return bedrock.estimate_tokens(bedrock.request_text(SYSTEM_PROMPT, build_payload(q, g)))


def answer(
    q: str,
    g: CampaignGrounding,
    *,
    client: Any | None = None,
    env: Mapping[str, str] | None = None,
    log_path: Path = LOG_PATH,
    use_ai: bool = True,
    off_reason: str = "ai_off",
) -> AssistantAnswer:
    """Answer ``q`` and log it. Invalid questions raise ``ValueError``.

    Invalid questions (Requirement 3.6) make no Bedrock call and no log write;
    callers should check :func:`validate_question` first and show its message.
    ``use_ai=False`` (the "Use AI Features" switch or the session token cap)
    answers with the built-in rules and records ``off_reason``.
    """
    error = validate_question(q)
    if error is not None:
        raise ValueError(error)

    usage, seconds, reason, sent = None, 0.0, "", ()
    flagged: list[str] = []
    routed = route(q)
    if routed == "model_results":
        text, mode, reason = MODEL_RESULTS_MESSAGE, "Local", "local"
    elif routed == "off_topic":
        text, mode, reason = OFF_TOPIC_MESSAGE, "Local", "local"
    else:
        payload = build_payload(q, g)
        sent = tuple(k for k, v in payload.items() if v not in (None, "", [], {}))
        result = (
            bedrock.converse(SYSTEM_PROMPT, payload, client=client, env=env,
                             max_tokens=MAX_REPLY_TOKENS)
            if use_ai else bedrock.BedrockResult("Demo", None, None, off_reason)
        )
        usage, seconds = result.usage, result.seconds
        if result.mode == "Bedrock" and result.text:
            text, mode = format_answer(result.text), "Bedrock"
            if not text:
                text, mode = "", "Demo"
                reason = bedrock.REASON_EMPTY
        else:
            text, mode, reason = "", "Demo", result.reason
        if mode == "Demo":
            text = format_answer(mock_assistant_answer(q, g.form, g.context, payload["known_gaps"], g.run))
        flagged = unsupported_numbers(text, payload)

    if mode != "Local":   # routed messages are fixed text, kept as written
        text = format_answer(text) or text
    return AssistantAnswer(
        text=text, mode=mode, log_saved=_append_log(log_path, q, text),
        usage=usage, seconds=seconds, reason=reason, flagged=tuple(flagged),
        fields_sent=sent,
    )


def report_wrong_answer(question: str, answer_text: str, log_path: Path = LOG_PATH) -> bool:
    """Log a question and answer the user marked as wrong (Requirement 37.4)."""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {"question": question, "answer": answer_text, "reported_wrong": True,
             "timestamp": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False,
        )
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return True
    except Exception:
        return False


def clear_log(log_path: Path = LOG_PATH) -> bool:
    """Delete the assistant log (Requirement 37.4, "Clear Conversation And Log")."""
    try:
        if log_path.exists():
            log_path.unlink()
        return True
    except Exception:
        return False

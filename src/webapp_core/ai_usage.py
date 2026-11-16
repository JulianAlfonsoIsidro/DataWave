"""Token usage records and limits for the AI features (Part 9 round 3).

Pure, no Streamlit (spec part9-layout-fixes, Requirement 33). The page keeps a
list of :class:`UsageRecord` in session state; this module turns it into the
token line, the session totals and the cap check. A Demo or Local call is
recorded with zero tokens and says so. No credential is ever touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

FEATURE_ASSISTANT = "Ask Assistant"
FEATURE_PERSONAS = "Persona Naming"
FEATURE_UPLOAD = "Upload Campaign File"
FEATURES = (FEATURE_UPLOAD, FEATURE_PERSONAS, FEATURE_ASSISTANT)

# Reply caps sent as inferenceConfig.maxTokens (design: "Limits").
# The configured model reasons before it answers, and reasoning counts as
# output, so each cap leaves room for it (design "Limits").
MAX_TOKENS = {FEATURE_ASSISTANT: 1500, FEATURE_PERSONAS: 800, FEATURE_UPLOAD: 1200}
SESSION_TOKEN_CAP = 100_000
# Average tokens for naming one persona with Bedrock, from
# docs/ai-token-report.md (None until measured; the page then shows only the
# request-size estimate).
# Measured 2026-11-13 on global.anthropic.claude-sonnet-5-5 (docs/ai-token-report.md).
MEASURED_TOKENS_PER_PERSONA: int | None = 740
MEASURED_TOKENS_PER_QUESTION: int | None = 5_730   # all fixtures; 2,005 with the form only
MEASURED_TOKENS_PER_UPLOAD: int | None = 6_180     # 1,323 (2,000 chars) to 11,037 (30,000 chars)
MEASURED_LABEL = "measured"
SESSION_QUESTION_LIMIT = 30

# What makes a call use more tokens, one short line per place it matters.
# Shown as hover text or added to an existing caption, never as a new block.
TOKEN_HINTS = {
    "personas": "More personas means more tokens: each persona is named in its own request.",
    "upload": "Longer files use more tokens: the whole masked text is sent.",
    "question": "Longer questions, drafts and summaries use more tokens than short facts.",
    "suggested": "Drafts and summaries write longer answers, so they use more tokens.",
}

CAP_MESSAGE = (
    "This session has used its AI token allowance, so the built-in rules are "
    "used from now on. Start a new session to use Bedrock again."
)

# Plain words for the fixed fallback codes in ai.bedrock.
REASONS = {
    "no_credentials": "no AI service credentials are set",
    "timeout": "the AI service took too long",
    "error": "the AI service could not be reached",
    "bad_json": "the AI reply could not be read",
    "empty_response": "the AI reply was empty",
    "payload_rejected": "the request was blocked because it held client data",
    "invalid_reply": "the AI reply broke the naming rules",
    "cap_reached": "the session token allowance was used up",
    "ai_off": "AI features are switched off",
    "local": "answered by the app without the AI service",
    "builtin_choice": "the built-in rules were chosen",
}


def reason_text(code: str) -> str:
    """Plain words for a fallback code ('' for none)."""
    return REASONS.get(code or "", code or "")


@dataclass(frozen=True)
class UsageRecord:
    """One AI call: what, how, how many tokens and how long."""

    feature: str
    mode: str                  # "Bedrock", "Demo" or "Local"
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    seconds: float = 0.0
    reason: str = ""           # fallback code when mode is not Bedrock

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature, "mode": self.mode,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens, "seconds": round(self.seconds, 2),
            "reason": self.reason,
        }


def record_from(feature: str, mode: str, usage: Any = None, seconds: float = 0.0,
                reason: str = "") -> UsageRecord:
    """Build a record from an ``ai.bedrock.Usage`` (or None, which means 0)."""
    def num(name: str) -> int:
        value = getattr(usage, name, None) if usage is not None else None
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0

    inp, out, tot = num("input_tokens"), num("output_tokens"), num("total_tokens")
    if not tot:
        tot = inp + out
    return UsageRecord(feature, mode, inp, out, tot, float(seconds or 0.0), reason)


def usage_line(rec: UsageRecord | None) -> str:
    """``Input 412 | Output 96 | Total 508 tokens`` (numbers only)."""
    if rec is None:
        return ""
    if rec.mode != "Bedrock" and rec.total_tokens == 0:
        return "0 tokens (built-in rules, no AI service call)"
    return f"Input {rec.input_tokens:,} | Output {rec.output_tokens:,} | Total {rec.total_tokens:,} tokens"


def estimate_line(estimated_input: int) -> str:
    """The line shown while a call runs; always labelled an estimate."""
    return f"Input about {int(estimated_input):,} tokens (estimated)"


def combine(records: Iterable[UsageRecord], feature: str, mode: str) -> UsageRecord:
    """One record summing several (a persona naming run)."""
    recs = list(records)
    return UsageRecord(
        feature, mode,
        sum(r.input_tokens for r in recs), sum(r.output_tokens for r in recs),
        sum(r.total_tokens for r in recs), sum(r.seconds for r in recs),
    )


@dataclass(frozen=True)
class FeatureTotals:
    feature: str
    calls: int
    bedrock_calls: int
    demo_calls: int
    total_tokens: int
    reasons: tuple[str, ...]


def session_totals(records: Iterable[UsageRecord]) -> list[FeatureTotals]:
    """Totals per feature, in the fixed feature order."""
    recs = list(records)
    out = []
    for feature in FEATURES:
        mine = [r for r in recs if r.feature == feature]
        reasons = tuple(dict.fromkeys(reason_text(r.reason) for r in mine
                                      if r.mode != "Bedrock" and r.reason))
        out.append(FeatureTotals(
            feature, len(mine),
            sum(1 for r in mine if r.mode == "Bedrock"),
            sum(1 for r in mine if r.mode != "Bedrock"),
            sum(r.total_tokens for r in mine), reasons,
        ))
    return out


def tokens_used(records: Iterable[UsageRecord]) -> int:
    return sum(r.total_tokens for r in records)


def cap_reached(records: Iterable[UsageRecord], cap: int = SESSION_TOKEN_CAP) -> bool:
    """True once the session has used ``cap`` tokens or more."""
    return tokens_used(records) >= cap

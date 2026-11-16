"""Campaign file extractor: PDF/DOCX text, JSON validation, Mock fallback.

Pure logic with no Streamlit imports (design section 2).

- :func:`extract_text` reads an uploaded PDF or DOCX locally and raises
  :class:`UploadError` with a specific cause (Requirements 2.2, 2.3).
- :func:`validate_fields` drops, never repairs, invalid values (2.5, 2.7).
- :func:`extract_campaign` sends at most 30,000 characters to Bedrock (2.4),
  falls back to ``mocks.mock_extract`` for non-JSON, Demo Mode, or a run
  over 60 s (2.6, 2.8, 2.10), tags every field (2.11), and never raises.
  Each call returns a fresh result, so a new upload replaces the earlier
  one (2.13).

pdfplumber and python-docx are imported lazily.

Part 9 round 3 (Requirements 33, 37): the result carries the call's token
Usage, seconds and fallback reason; the reply is capped with
``inferenceConfig.maxTokens``; ``use_ai=False`` reads the file with the
built-in rules on purpose. The page masks personal details before calling.
"""

from __future__ import annotations

import io
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from ai import bedrock, mocks
from webapp_core.threshold import THRESHOLD_SPECS, ThresholdType

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PROMPT_CHARS = 30_000
EXTRACTION_BUDGET_SECONDS = 60
MAX_REPLY_TOKENS = 1200  # inferenceConfig.maxTokens; room for reasoning (design "Limits")
MAX_REWARD_CHARS = 200

PRODUCT_TYPE_OPTIONS: tuple[str, ...] = ("Savings", "Time Deposit", "Investment", "Credit Card")
MECHANIC_OPTIONS: tuple[str, ...] = ("TOP_UP", "NEW_ACCOUNT", "ADB_INCREASE", "OTHER")
# Must match Part 4's channel labels exactly.
CHANNEL_OPTIONS: tuple[str, ...] = ("In-app", "Email", "SMS")
KNOWN_SEGMENTS: tuple[str, ...] = tuple(mocks.KNOWN_SEGMENTS)

CAMPAIGN_FIELDS: tuple[str, ...] = (
    "product_type",
    "mechanic",
    "threshold_type",
    "threshold_value",
    "reward",
    "eligible_segments",
    "min_adb",
    "channels",
)
CONTEXT_KEYS: tuple[str, ...] = tuple(mocks.CONTEXT_KEYS)

FOUND = "Found in Document"
NEEDS_INPUT = "Needs Input"

SYSTEM_PROMPT = (
    "You extract campaign proposal details from a document. Reply with strict "
    "JSON only, no prose, shaped as {\"fields\": {...}, \"context\": {...}}. "
    "Allowed keys in fields: product_type (one of "
    + ", ".join(PRODUCT_TYPE_OPTIONS)
    + "), mechanic (one of "
    + ", ".join(MECHANIC_OPTIONS)
    + "), threshold_type (one of "
    + ", ".join(t.value for t in ThresholdType)
    + "), threshold_value (number), reward (short text), eligible_segments "
    "(list of customer segments), min_adb (number in PHP), channels (list "
    "of In-app, Email, SMS). Allowed keys in context: "
    + ", ".join(CONTEXT_KEYS)
    + ". Omit any key the document does not state. Never guess."
)


class UploadError(Exception):
    """Raised by :func:`extract_text`; ``cause`` says which check failed."""

    def __init__(self, cause: Literal["type", "size", "unreadable", "empty"], message: str = ""):
        super().__init__(message or cause)
        self.cause = cause


@dataclass(frozen=True)
class ExtractionResult:
    """Validated fields, one tag per Campaign_Field, context, and mode."""

    fields: dict[str, Any]
    tags: dict[str, str]
    context: dict[str, str]
    mode: Literal["Bedrock", "Demo"]
    document_text: str = field(default="")
    usage: Any = None          # ai.bedrock.Usage when Bedrock answered
    seconds: float = 0.0
    reason: str = ""           # fallback code when mode is Demo


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_text(data: bytes, filename: str) -> str:
    """Return the text of a PDF or DOCX upload, or raise :class:`UploadError`."""
    name = (filename or "").lower().strip()
    if name.endswith(".pdf"):
        kind = "pdf"
    elif name.endswith(".docx"):
        kind = "docx"
    else:
        raise UploadError("type", "Only PDF and DOCX files are supported.")
    if len(data or b"") > MAX_UPLOAD_BYTES:
        raise UploadError("size", "The file is larger than 10 MB.")
    try:
        text = _read_pdf(data) if kind == "pdf" else _read_docx(data)
    except UploadError:
        raise
    except Exception as exc:  # noqa: BLE001 - corrupt/encrypted/missing library
        raise UploadError("unreadable", "The file could not be read.") from exc
    if not text or not text.strip():
        raise UploadError("empty", "The file has no readable text.")
    return text


def _read_pdf(data: bytes) -> str:
    import pdfplumber  # lazy

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _read_docx(data: bytes) -> str:
    import docx  # lazy (python-docx)

    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _clean_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple, set, frozenset)) else []


def validate_fields(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only valid Campaign_Fields; invalid values are dropped, not fixed."""
    out: dict[str, Any] = {}
    if not isinstance(raw, Mapping):
        return out

    product = raw.get("product_type")
    if isinstance(product, str) and product in PRODUCT_TYPE_OPTIONS:
        out["product_type"] = product

    mechanic = raw.get("mechanic")
    if isinstance(mechanic, str) and mechanic in MECHANIC_OPTIONS:
        out["mechanic"] = mechanic

    ttype: ThresholdType | None = None
    raw_type = raw.get("threshold_type")
    if isinstance(raw_type, str):
        try:
            ttype = ThresholdType(raw_type)
        except ValueError:
            ttype = None
    if ttype is not None:
        out["threshold_type"] = ttype.value
        number = _finite_number(raw.get("threshold_value"))
        spec = THRESHOLD_SPECS[ttype]
        if number is not None and spec.minimum <= number <= spec.maximum:
            out["threshold_value"] = _clean_number(number)

    reward = raw.get("reward")
    if isinstance(reward, str):
        reward = reward.strip()
        if reward and len(reward) <= MAX_REWARD_CHARS:
            out["reward"] = reward

    if "eligible_segments" in raw:
        known = {s.lower(): s for s in KNOWN_SEGMENTS}
        segments: list[str] = []
        for item in _as_list(raw.get("eligible_segments")):
            if isinstance(item, str) and item.strip().lower() in known:
                canon = known[item.strip().lower()]
                if canon not in segments:
                    segments.append(canon)
        if segments:
            out["eligible_segments"] = segments

    min_adb = _finite_number(raw.get("min_adb"))
    if min_adb is not None and min_adb >= 0:
        out["min_adb"] = _clean_number(min_adb)

    if "channels" in raw:
        wanted = {
            item.strip().lower()
            for item in _as_list(raw.get("channels"))
            if isinstance(item, str)
        }
        channels = [c for c in CHANNEL_OPTIONS if c.lower() in wanted]
        if channels:
            out["channels"] = channels

    return out


def _validate_context(raw: Any) -> dict[str, str]:
    context = {key: "" for key in CONTEXT_KEYS}
    if isinstance(raw, Mapping):
        for key in CONTEXT_KEYS:
            value = raw.get(key)
            if isinstance(value, str):
                context[key] = value.strip()
    return context


def _tag(fields: Mapping[str, Any]) -> dict[str, str]:
    return {name: (FOUND if name in fields else NEEDS_INPUT) for name in CAMPAIGN_FIELDS}


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _mock_result(text: str, reason: str = "", usage: Any = None, seconds: float = 0.0) -> ExtractionResult:
    try:
        mocked = mocks.mock_extract(text)
        fields = validate_fields(mocked.get("fields", {}))
        context = _validate_context(mocked.get("context", {}))
    except Exception:  # noqa: BLE001 - never raise
        fields, context = {}, _validate_context({})
    return ExtractionResult(fields, _tag(fields), context, "Demo", text, usage, seconds, reason)


def request_payload(text: str) -> dict[str, Any]:
    """What one extraction sends: at most 30,000 characters of the text."""
    return {"document_text": (text or "")[:MAX_PROMPT_CHARS]}


def estimated_input_tokens(text: str) -> int:
    """The input estimate shown while the call runs (labelled an estimate)."""
    return bedrock.estimate_tokens(bedrock.request_text(SYSTEM_PROMPT, request_payload(text)))


def extract_campaign(
    text: str,
    *,
    client: Any | None = None,
    env: Mapping[str, str] | None = None,
    clock: Callable[[], float] = time.monotonic,
    use_ai: bool = True,
    off_reason: str = "ai_off",
) -> ExtractionResult:
    """Extract validated, tagged Campaign_Fields from document text. Never raises."""
    text = text if isinstance(text, str) else ""
    if not use_ai:
        return _mock_result(text, off_reason)
    try:
        started = clock()
        result = bedrock.converse(
            SYSTEM_PROMPT,
            request_payload(text),
            expect_json=True,
            client=client,
            env=env,
            max_tokens=MAX_REPLY_TOKENS,
        )
        if clock() - started > EXTRACTION_BUDGET_SECONDS:
            return _mock_result(text, bedrock.REASON_TIMEOUT, result.usage, result.seconds)
        if result.mode != "Bedrock" or not isinstance(result.parsed, Mapping):
            return _mock_result(text, result.reason or bedrock.REASON_BAD_JSON, result.usage, result.seconds)

        parsed = result.parsed
        raw_fields = parsed.get("fields")
        if not isinstance(raw_fields, Mapping):
            raw_fields = parsed  # tolerate a flat object
        fields = validate_fields(raw_fields)
        context = _validate_context(parsed.get("context"))
        return ExtractionResult(fields, _tag(fields), context, "Bedrock", text,
                                result.usage, result.seconds, "")
    except Exception:  # noqa: BLE001
        return _mock_result(text, bedrock.REASON_ERROR)

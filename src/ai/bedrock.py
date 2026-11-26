"""Shared Amazon Bedrock Converse client with per-call Demo Mode reporting.

Every AI feature (campaign extractor, assistant, persona narrator) calls
:func:`converse`. The function never raises: any failure becomes a Demo
result carrying a short fixed reason code, so callers fall back to their
rule-based Mock (Requirements 1.1, 1.5, 1.6).

Guarantees:

- Credentials come from ``.env`` through python-dotenv (Requirement 1.2).
- One attempt, 30 s hard cap enforced by a worker thread (Requirement 1.4).
- The payload is checked by :func:`assert_private` before any network call;
  a rejected payload makes zero boto3 calls (Requirements 1.10, 1.11).
- No credential value is ever placed in a result, reason, or exception text
  (Requirement 1.13).
- Demo Mode is reported per call and never latched (Requirement 1.8).
- No numeric business logic lives here (Requirement 1.12).
- Part 9 round 3 (Requirement 33): a finished call carries its token
  :class:`Usage`, read from ``response["usage"]`` (``inputTokens``,
  ``outputTokens``, ``totalTokens``) and never printed; ``max_tokens`` is
  sent as ``inferenceConfig.maxTokens``; :func:`estimate_tokens` gives the
  shown-while-waiting estimate (about four characters per token).

This module has no Streamlit imports. boto3 is imported lazily so machines
without it still work in Demo Mode.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

TIMEOUT_SECONDS = 30
REQUIRED_ENV = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION",
    "BEDROCK_MODEL_ID",
)

# Fixed reason codes. Never built from exception text or env values.
REASON_NO_CREDENTIALS = "no_credentials"
REASON_ERROR = "error"
REASON_TIMEOUT = "timeout"
REASON_BAD_JSON = "bad_json"
REASON_PAYLOAD_REJECTED = "payload_rejected"
REASON_EMPTY = "empty_response"
REASON_TRUNCATED = "truncated"  # reply stopped at max_tokens (cut off); usage is kept

_CLIENT_ID_KEY = "clientid"
_CLIENT_ID_VALUE = re.compile(r"\bC\d{5,}\b")
_RECORD_KEYS = frozenset({"client_id", "p_join", "best_channel", "control"})
_FENCE = re.compile(r"^\s*```[A-Za-z0-9_-]*[ \t]*\r?\n?(.*?)\r?\n?```\s*$", re.DOTALL)


CHARS_PER_TOKEN = 4  # the estimate shown while a call runs; labelled an estimate


@dataclass(frozen=True)
class Usage:
    """Token counts of one finished call (each an int, or None when absent)."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    @classmethod
    def from_response(cls, response: Any) -> "Usage":
        """Read ``response["usage"]`` like the AWS example; never raises."""
        try:
            usage = response.get("usage", {}) if isinstance(response, Mapping) else {}
        except Exception:
            usage = {}
        if not isinstance(usage, Mapping):
            usage = {}

        def num(key: str) -> int | None:
            value = usage.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            return int(value)

        total = num("totalTokens")
        inp, out = num("inputTokens"), num("outputTokens")
        if total is None and inp is not None and out is not None:
            total = inp + out
        return cls(inp, out, total)


def estimate_tokens(text: str) -> int:
    """About four characters per token (an estimate, labelled as one)."""
    return int(math.ceil(len(text or "") / CHARS_PER_TOKEN))


def request_text(system: str, payload: Mapping[str, Any]) -> str:
    """The text one call sends: the system prompt and the JSON payload."""
    return (system or "") + "\n" + json.dumps(payload, default=str, ensure_ascii=False)


@dataclass(frozen=True)
class BedrockResult:
    """Outcome of one Converse call.

    ``mode`` is ``"Bedrock"`` only when the call succeeded (and, when JSON
    was requested, parsed). Otherwise it is ``"Demo"`` and ``reason`` holds
    one fixed code. ``usage`` is set whenever Bedrock answered (even when
    the reply was then rejected), so spent tokens are still counted.
    """

    mode: Literal["Bedrock", "Demo"]
    text: str | None
    parsed: Any | None
    reason: str = ""
    usage: Usage | None = None
    seconds: float = 0.0
    stop_reason: str = ""   # Converse stopReason when Bedrock answered (for example end_turn, max_tokens)


class PayloadRejected(ValueError):
    """Raised by :func:`assert_private` for a payload that breaks privacy."""


def _normalise_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def assert_private(payload: Any) -> None:
    """Raise :class:`PayloadRejected` unless ``payload`` is aggregate-only.

    Rejects: a ``client_id`` key (any casing/punctuation), a string value
    shaped like a client id, any DataFrame/Series, and any list of two or
    more dicts that look like per-client records (Requirements 1.10, 1.11).
    The message never echoes payload content.
    """
    _check(payload)


def _check(node: Any) -> None:
    # Local import keeps pandas out of the import path until needed.
    import pandas as pd

    if isinstance(node, (pd.DataFrame, pd.Series)):
        raise PayloadRejected("payload contains tabular client data")
    if isinstance(node, Mapping):
        for key, value in node.items():
            if _normalise_key(key) == _CLIENT_ID_KEY:
                raise PayloadRejected("payload contains a client id key")
            _check(key)
            _check(value)
        return
    if isinstance(node, str):
        if _CLIENT_ID_VALUE.search(node):
            raise PayloadRejected("payload contains a client id value")
        return
    if isinstance(node, (list, tuple, set, frozenset)):
        items = list(node)
        records = [i for i in items if isinstance(i, Mapping)]
        if len(records) >= 2 and any(
            _RECORD_KEYS & {str(k).lower() for k in r} for r in records
        ):
            raise PayloadRejected("payload contains per-client rows")
        for item in items:
            _check(item)


def _read_env(env: Mapping[str, str] | None) -> dict[str, str]:
    """Return the four required variables, trimmed ('' when missing)."""
    if env is None:
        try:
            from dotenv import load_dotenv

            load_dotenv(override=False)
        except Exception:  # dotenv absent or unreadable: fall back to os.environ
            pass
        source: Mapping[str, str] = os.environ
    else:
        source = env
    return {name: str(source.get(name) or "").strip() for name in REQUIRED_ENV}


def credentials_available(env: Mapping[str, str] | None = None) -> bool:
    """True when all four required variables are present and non-empty."""
    values = _read_env(env)
    return all(values[name] for name in REQUIRED_ENV)


def model_id(env: Mapping[str, str] | None = None) -> str:
    """The configured ``BEDROCK_MODEL_ID`` ('' when unset). Not a secret."""
    return _read_env(env)["BEDROCK_MODEL_ID"]


def _strip_fence(text: str) -> str:
    """Strip one surrounding Markdown code fence; nothing more lenient."""
    match = _FENCE.match(text)
    return match.group(1) if match else text


def _extract_text(response: Any) -> str:
    content = response["output"]["message"]["content"]
    parts = [c["text"] for c in content if isinstance(c, Mapping) and c.get("text")]
    return "".join(parts)


def _build_client(values: Mapping[str, str]) -> Any:
    import boto3  # lazy: ImportError is handled by the caller
    from botocore.config import Config

    return boto3.client(
        "bedrock-runtime",
        region_name=values["AWS_REGION"],
        aws_access_key_id=values["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=values["AWS_SECRET_ACCESS_KEY"],
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN") or None,
        config=Config(
            connect_timeout=5,
            read_timeout=TIMEOUT_SECONDS,
            retries={"max_attempts": 1},
        ),
    )


def _demo(reason: str, usage: Usage | None = None, seconds: float = 0.0,
          stop_reason: str = "") -> BedrockResult:
    return BedrockResult(mode="Demo", text=None, parsed=None, reason=reason,
                         usage=usage, seconds=seconds, stop_reason=stop_reason)


def converse(
    system: str,
    payload: Mapping[str, Any],
    *,
    expect_json: bool = False,
    client: Any | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    max_tokens: int | None = None,
) -> BedrockResult:
    """Call Bedrock Converse once and report Bedrock or Demo for this call.

    ``client`` and ``env`` are injection points for tests. ``timeout``
    defaults to :data:`TIMEOUT_SECONDS` (read at call time). ``max_tokens``
    caps the reply (``inferenceConfig.maxTokens``).
    """
    try:
        assert_private(payload)
    except PayloadRejected:
        return _demo(REASON_PAYLOAD_REJECTED)
    except Exception:
        return _demo(REASON_PAYLOAD_REJECTED)

    try:
        values = _read_env(env)
        if not all(values[name] for name in REQUIRED_ENV):
            return _demo(REASON_NO_CREDENTIALS)

        limit = TIMEOUT_SECONDS if timeout is None else timeout
        user_text = json.dumps(payload, default=str, ensure_ascii=False)
        box: dict[str, Any] = {}
        request: dict[str, Any] = {
            "modelId": values["BEDROCK_MODEL_ID"],
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user_text}]}],
        }
        if max_tokens:
            request["inferenceConfig"] = {"maxTokens": int(max_tokens)}
        started = time.monotonic()

        def work() -> None:
            try:
                api = client if client is not None else _build_client(values)
                box["response"] = api.converse(**request)
            except BaseException:  # noqa: BLE001 - never leak exception text
                box["error"] = True

        worker = threading.Thread(target=work, name="bedrock-converse", daemon=True)
        worker.start()
        worker.join(limit)
        seconds = time.monotonic() - started
        if worker.is_alive():
            return _demo(REASON_TIMEOUT, seconds=seconds)
        if box.get("error") or "response" not in box:
            return _demo(REASON_ERROR, seconds=seconds)

        usage = Usage.from_response(box["response"])
        stop = str(box["response"].get("stopReason") or "") if isinstance(box["response"], Mapping) else ""
        if stop == "max_tokens":
            # Cut off by the output cap: never show a partial answer as a normal one.
            return _demo(REASON_TRUNCATED, usage, seconds, stop)
        text = _extract_text(box["response"])
    except Exception:
        return _demo(REASON_ERROR)

    if not text or not text.strip():
        return _demo(REASON_EMPTY, usage, seconds, stop)

    if not expect_json:
        return BedrockResult(mode="Bedrock", text=text, parsed=None, usage=usage, seconds=seconds, stop_reason=stop)

    try:
        parsed = json.loads(_strip_fence(text))
    except (ValueError, TypeError):
        return _demo(REASON_BAD_JSON, usage, seconds, stop)
    return BedrockResult(mode="Bedrock", text=text, parsed=parsed, usage=usage, seconds=seconds, stop_reason=stop)

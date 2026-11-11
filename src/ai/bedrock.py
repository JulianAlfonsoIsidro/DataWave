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

This module has no Streamlit imports. boto3 is imported lazily so machines
without it still work in Demo Mode.
"""

from __future__ import annotations

import json
import os
import re
import threading
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

_CLIENT_ID_KEY = "clientid"
_CLIENT_ID_VALUE = re.compile(r"\bC\d{5,}\b")
_RECORD_KEYS = frozenset({"client_id", "p_join", "best_channel", "control"})
_FENCE = re.compile(r"^\s*```[A-Za-z0-9_-]*[ \t]*\r?\n?(.*?)\r?\n?```\s*$", re.DOTALL)


@dataclass(frozen=True)
class BedrockResult:
    """Outcome of one Converse call.

    ``mode`` is ``"Bedrock"`` only when the call succeeded (and, when JSON
    was requested, parsed). Otherwise it is ``"Demo"`` and ``reason`` holds
    one fixed code.
    """

    mode: Literal["Bedrock", "Demo"]
    text: str | None
    parsed: Any | None
    reason: str = ""


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


def _demo(reason: str) -> BedrockResult:
    return BedrockResult(mode="Demo", text=None, parsed=None, reason=reason)


def converse(
    system: str,
    payload: Mapping[str, Any],
    *,
    expect_json: bool = False,
    client: Any | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> BedrockResult:
    """Call Bedrock Converse once and report Bedrock or Demo for this call.

    ``client`` and ``env`` are injection points for tests. ``timeout``
    defaults to :data:`TIMEOUT_SECONDS` (read at call time).
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

        def work() -> None:
            try:
                api = client if client is not None else _build_client(values)
                box["response"] = api.converse(
                    modelId=values["BEDROCK_MODEL_ID"],
                    system=[{"text": system}],
                    messages=[{"role": "user", "content": [{"text": user_text}]}],
                )
            except BaseException:  # noqa: BLE001 - never leak exception text
                box["error"] = True

        worker = threading.Thread(target=work, name="bedrock-converse", daemon=True)
        worker.start()
        worker.join(limit)
        if worker.is_alive():
            return _demo(REASON_TIMEOUT)
        if box.get("error") or "response" not in box:
            return _demo(REASON_ERROR)

        text = _extract_text(box["response"])
    except Exception:
        return _demo(REASON_ERROR)

    if not text or not text.strip():
        return _demo(REASON_EMPTY)

    if not expect_json:
        return BedrockResult(mode="Bedrock", text=text, parsed=None)

    try:
        parsed = json.loads(_strip_fence(text))
    except (ValueError, TypeError):
        return _demo(REASON_BAD_JSON)
    return BedrockResult(mode="Bedrock", text=text, parsed=parsed)

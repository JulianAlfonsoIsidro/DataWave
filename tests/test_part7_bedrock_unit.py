"""Unit tests for the shared Bedrock client (src/ai/bedrock.py).

Every test injects a fake client and an explicit env mapping, so no test
touches the network or reads a real ``.env``.

Covers: the four Demo cases, Demo not latched, no credential text in
results or reasons, and a single attempt.
"""

from __future__ import annotations

import json
import threading

import pytest

from ai import bedrock
from ai.bedrock import BedrockResult, converse

SECRET_KEY_ID = "AKIATESTSECRETKEYID123"
SECRET_KEY = "s3cr3t/ACCESS+key/value/XYZ"
FAKE_ENV = {
    "AWS_ACCESS_KEY_ID": SECRET_KEY_ID,
    "AWS_SECRET_ACCESS_KEY": SECRET_KEY,
    "AWS_REGION": "us-east-1",
    "BEDROCK_MODEL_ID": "fake.model-id-v1",
}
SECRETS = (SECRET_KEY_ID, SECRET_KEY)
PAYLOAD = {"question": "What is the plan?", "aggregate": {"leads": 120}}


class FakeClient:
    """Counts calls and returns a canned Converse response."""

    def __init__(self, text: str = "hello") -> None:
        self.text = text
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        return {"output": {"message": {"content": [{"text": self.text}]}}}


class RaisingClient:
    """Raises an error whose message carries credential values."""

    def __init__(self) -> None:
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        raise RuntimeError(f"denied for {SECRET_KEY_ID} / {SECRET_KEY}")


class SlowClient:
    """Blocks until released, simulating a call past the timeout."""

    def __init__(self) -> None:
        self.calls = 0
        self.release = threading.Event()

    def converse(self, **kwargs):
        self.calls += 1
        self.release.wait(5)
        return {"output": {"message": {"content": [{"text": "late"}]}}}


def _assert_no_secrets(result: BedrockResult) -> None:
    blob = repr(result)
    for secret in SECRETS:
        assert secret not in blob


# --- Demo case 1: missing credentials (Requirement 1.5) -------------------


@pytest.mark.parametrize("missing", list(bedrock.REQUIRED_ENV))
def test_missing_credential_returns_demo_without_calling_client(missing):
    env = {k: v for k, v in FAKE_ENV.items() if k != missing}
    client = FakeClient()
    result = converse("sys", PAYLOAD, client=client, env=env)
    assert result.mode == "Demo"
    assert result.reason == bedrock.REASON_NO_CREDENTIALS
    assert result.text is None and result.parsed is None
    assert client.calls == 0
    _assert_no_secrets(result)


def test_blank_credential_counts_as_missing():
    env = dict(FAKE_ENV, AWS_REGION="   ")
    client = FakeClient()
    result = converse("sys", PAYLOAD, client=client, env=env)
    assert result.mode == "Demo"
    assert result.reason == bedrock.REASON_NO_CREDENTIALS
    assert client.calls == 0


def test_credentials_available_reflects_env():
    assert bedrock.credentials_available(FAKE_ENV) is True
    assert bedrock.credentials_available({}) is False


# --- Demo case 2: failed call (Requirements 1.5, 1.13) --------------------


def test_failed_call_returns_demo_with_fixed_reason_and_no_secrets():
    client = RaisingClient()
    result = converse("sys", PAYLOAD, client=client, env=FAKE_ENV)
    assert result.mode == "Demo"
    assert result.reason == bedrock.REASON_ERROR
    assert result.text is None and result.parsed is None
    _assert_no_secrets(result)
    assert "denied" not in result.reason


# --- Demo case 3: slow call with shortened timeout (Requirement 1.4) ------


def test_slow_call_times_out_to_demo():
    client = SlowClient()
    try:
        result = converse("sys", PAYLOAD, client=client, env=FAKE_ENV, timeout=0.1)
    finally:
        client.release.set()
    assert result.mode == "Demo"
    assert result.reason == bedrock.REASON_TIMEOUT
    assert client.calls == 1
    _assert_no_secrets(result)


# --- Demo case 4: invalid JSON (Requirement 1.6) --------------------------


def test_invalid_json_returns_demo_when_json_expected():
    client = FakeClient(text="this is not json")
    result = converse("sys", PAYLOAD, expect_json=True, client=client, env=FAKE_ENV)
    assert result.mode == "Demo"
    assert result.reason == bedrock.REASON_BAD_JSON
    assert result.parsed is None
    _assert_no_secrets(result)


def test_plain_text_is_accepted_when_json_not_expected():
    client = FakeClient(text="this is not json")
    result = converse("sys", PAYLOAD, client=client, env=FAKE_ENV)
    assert result.mode == "Bedrock"
    assert result.text == "this is not json"


def test_valid_and_single_fenced_json_parse():
    body = {"a": 1}
    plain = converse(
        "sys", PAYLOAD, expect_json=True, env=FAKE_ENV,
        client=FakeClient(json.dumps(body)),
    )
    fenced = converse(
        "sys", PAYLOAD, expect_json=True, env=FAKE_ENV,
        client=FakeClient("```json\n" + json.dumps(body) + "\n```"),
    )
    assert plain.mode == fenced.mode == "Bedrock"
    assert plain.parsed == fenced.parsed == body


# --- Demo is not latched (Requirement 1.8) --------------------------------


def test_demo_is_not_latched_across_calls():
    good = FakeClient(text="ok")
    first = converse("sys", PAYLOAD, client=RaisingClient(), env=FAKE_ENV)
    second = converse("sys", PAYLOAD, client=good, env=FAKE_ENV)
    third = converse("sys", PAYLOAD, client=good, env={})
    fourth = converse("sys", PAYLOAD, client=good, env=FAKE_ENV)
    assert [r.mode for r in (first, second, third, fourth)] == [
        "Demo", "Bedrock", "Demo", "Bedrock",
    ]
    assert second.text == fourth.text == "ok"


# --- Single attempt (Requirements 1.4, 10.5) ------------------------------


def test_failed_call_is_attempted_exactly_once():
    client = RaisingClient()
    converse("sys", PAYLOAD, client=client, env=FAKE_ENV)
    assert client.calls == 1


def test_successful_call_is_attempted_exactly_once():
    client = FakeClient()
    converse("sys", PAYLOAD, client=client, env=FAKE_ENV)
    assert client.calls == 1


def test_real_client_is_configured_for_single_attempt(monkeypatch):
    """The boto3 client built on the default path allows one attempt only."""
    boto3 = pytest.importorskip("boto3")
    captured: dict = {}

    class Stub:
        def converse(self, **kwargs):
            return {"output": {"message": {"content": [{"text": "x"}]}}}

    def fake_client(service, **kwargs):
        captured["service"] = service
        captured.update(kwargs)
        return Stub()

    monkeypatch.setattr(boto3, "client", fake_client)
    result = converse("sys", PAYLOAD, env=FAKE_ENV)
    assert result.mode == "Bedrock"
    assert captured["service"] == "bedrock-runtime"
    assert captured["config"].retries["max_attempts"] == 1


# --- No credential text anywhere in output (Requirement 1.13) -------------


def test_request_error_text_never_reaches_result_or_reason():
    results = [
        converse("sys", PAYLOAD, client=RaisingClient(), env=FAKE_ENV),
        converse("sys", PAYLOAD, client=FakeClient("nope"), expect_json=True, env=FAKE_ENV),
        converse("sys", PAYLOAD, client=FakeClient(), env={}),
    ]
    for result in results:
        assert result.mode == "Demo"
        _assert_no_secrets(result)
        assert result.reason in {
            bedrock.REASON_ERROR,
            bedrock.REASON_BAD_JSON,
            bedrock.REASON_NO_CREDENTIALS,
        }


def test_payload_rejection_message_does_not_echo_content():
    with pytest.raises(bedrock.PayloadRejected) as info:
        bedrock.assert_private({"client_id": SECRET_KEY})
    assert SECRET_KEY not in str(info.value)


class StopClient:
    """Returns text with a given stopReason and token usage."""

    def __init__(self, stop: str, text: str = "partial answer") -> None:
        self.stop = stop
        self.text = text

    def converse(self, **kwargs):
        return {"output": {"message": {"content": [{"text": self.text}]}}, "stopReason": self.stop,
                "usage": {"inputTokens": 100, "outputTokens": 3000, "totalTokens": 3100}}


def test_max_tokens_stop_is_a_failure_and_keeps_usage():
    result = converse("system", PAYLOAD, client=StopClient("max_tokens"), env=FAKE_ENV)
    assert result.mode == "Demo"
    assert result.reason == bedrock.REASON_TRUNCATED
    assert result.text is None
    assert result.stop_reason == "max_tokens"
    assert result.usage is not None and result.usage.total_tokens == 3100


def test_max_tokens_stop_with_json_expected_is_truncated_not_bad_json():
    result = converse("system", PAYLOAD, client=StopClient("max_tokens", '{"fields": {'), env=FAKE_ENV, expect_json=True)
    assert result.reason == bedrock.REASON_TRUNCATED


def test_end_turn_stop_is_a_normal_answer():
    result = converse("system", PAYLOAD, client=StopClient("end_turn", "all good"), env=FAKE_ENV)
    assert result.mode == "Bedrock" and result.text == "all good" and result.stop_reason == "end_turn"

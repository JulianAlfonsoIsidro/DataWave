"""Property test for the Bedrock payload privacy guard (Part 7, Property 1).

Never touches the network: a fake client stands in for boto3.
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from ai.bedrock import PayloadRejected, assert_private, converse
from tests.strategies_part7 import leaky_payloads, private_payloads

_ENV = {
    "AWS_ACCESS_KEY_ID": "fake-key-id",
    "AWS_SECRET_ACCESS_KEY": "fake-secret",
    "AWS_REGION": "us-east-1",
    "BEDROCK_MODEL_ID": "fake-model",
}


class FakeClient:
    """Counts converse calls and returns a minimal valid response."""

    def __init__(self) -> None:
        self.calls = 0

    def converse(self, **_kwargs):
        self.calls += 1
        return {"output": {"message": {"content": [{"text": "ok"}]}}}


@settings(max_examples=100, deadline=None)
@given(
    case=st.one_of(
        leaky_payloads().map(lambda p: ("leaky", p)),
        private_payloads.map(lambda p: ("private", p)),
    )
)
def test_bedrock_payload_privacy(case):
    """**Validates: Requirements 1.10, 1.11, 3.13, 6.2, 6.13, 9.13**

    Property 1: leaky payloads are rejected with zero client calls; private
    payloads are accepted by ``assert_private``.
    """
    kind, payload = case
    client = FakeClient()
    # converse takes a mapping; wrap non-mapping private trees.
    body = payload if isinstance(payload, dict) else {"value": payload}

    if kind == "leaky":
        with pytest.raises(PayloadRejected):
            assert_private(body)
        result = converse("system", body, client=client, env=_ENV)
        assert result.mode == "Demo"
        assert result.reason == "payload_rejected"
        assert client.calls == 0
    else:
        assert_private(body)  # must not raise
        result = converse("system", body, client=client, env=_ENV)
        assert result.mode == "Bedrock"
        assert client.calls == 1

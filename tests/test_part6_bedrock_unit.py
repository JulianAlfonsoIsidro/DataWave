"""Unit tests for the Bedrock chat loop with a stubbed Converse client.

These are concrete example tests (not Hypothesis properties) covering
:func:`assistant.bedrock_driver.answer_with_bedrock` (Requirements 3.1, 3.3,
4.1). ``boto3`` is *not* installed and the driver imports it lazily *inside*
the function, so each test injects a fake ``boto3`` module into
``sys.modules`` before calling the driver. The fake module's
``client("bedrock-runtime", ...)`` returns a fake client whose ``.converse(...)``
is scripted per test -- no real AWS call and no network are ever made.

Covered behaviours:

- A scripted ``tool_use`` turn followed by a terminal text turn drives the loop
  through exactly one tool call, names the tool, grounds the final text, and
  feeds the tool result back as a ``toolResult`` block (Requirements 3.1, 3.3).
- A client whose ``.converse`` raises makes ``answer_with_bedrock`` propagate the
  error so the engine can fall back to Mock Mode (Requirement 4.1).
- An immediate terminal text turn (no tool use) returns the text with
  ``tool_called is None`` and calls ``converse`` exactly once.
"""

from __future__ import annotations

import sys
import types

import pytest

from assistant import bedrock_driver
from assistant.models import ModelConfig


def _install_fake_boto3(monkeypatch, fake_client):
    """Inject a fake ``boto3`` module exposing ``client`` -> ``fake_client``.

    The driver does ``import boto3`` lazily inside ``answer_with_bedrock`` and
    then calls ``boto3.client("bedrock-runtime", ...)``. Placing a fake module
    in ``sys.modules`` makes that lazy import resolve to our fake, so the real
    (uninstalled) SDK is never needed. The returned ``calls`` list records the
    ``(service, kwargs)`` of each ``client(...)`` call.
    """
    calls: list[tuple] = []

    def _client(service, **kwargs):
        calls.append((service, kwargs))
        return fake_client

    fake_module = types.SimpleNamespace(client=_client)
    monkeypatch.setitem(sys.modules, "boto3", fake_module)
    return calls


class _FakeConverseClient:
    """A fake ``bedrock-runtime`` client with a scripted ``.converse``.

    ``responses`` is yielded one per ``converse`` call, in order. Every call's
    keyword arguments are recorded in ``self.calls`` so a test can inspect the
    messages sent back to the model (e.g. assert a ``toolResult`` block was
    included on the follow-up turn).
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _RaisingConverseClient:
    """A fake client whose ``.converse`` always raises, like a Bedrock error."""

    def __init__(self):
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("bedrock unavailable")


def _config():
    """A usable ModelConfig; its values only flow into the fake client."""
    return ModelConfig(
        aws_access_key_id="k",
        aws_secret_access_key="s",
        aws_region="us-east-1",
        bedrock_model_id="m",
    )


def _run_result_with_ready_toppers():
    """A minimal RunResult stand-in whose cards include Ready Toppers.

    ``get_card`` reads only ``run_result.cards``, so a ``SimpleNamespace`` with
    that one attribute is enough to drive the dispatched tool call.
    """
    card = {
        "segment": "Ready Toppers",
        "action": "Include",
        "dominant_channel": "In-app",
        "message_angle": "x",
        "expected_joiners": 120,
        "joiners_90_low": 90,
        "joiners_90_high": 150,
        "expected_value": 240000.0,
        "top_drivers": [],
        "excluded_by_reason": {},
    }
    return types.SimpleNamespace(cards=[card])


def test_tool_use_then_text_drives_one_tool_call_and_names_the_tool(monkeypatch):
    """A scripted tool_use then text loops once through get_card and cites it."""
    tool_use_response = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "t1",
                            "name": "get_card",
                            "input": {"segment": "Ready Toppers"},
                        }
                    }
                ],
            }
        },
        "stopReason": "tool_use",
    }
    terminal_response = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {"text": "Ready Toppers looks strong. (source: get_card)"}
                ],
            }
        },
        "stopReason": "end_turn",
    }
    fake_client = _FakeConverseClient([tool_use_response, terminal_response])
    _install_fake_boto3(monkeypatch, fake_client)

    run_result = _run_result_with_ready_toppers()

    text, tool_called = bedrock_driver.answer_with_bedrock(
        "Why is Ready Toppers prioritized?", run_result, None, _config()
    )

    # The loop ran exactly the tool_use round plus the terminal text round.
    assert len(fake_client.calls) == 2
    # The dispatched tool is named, and the grounded final text is returned.
    assert tool_called == "get_card"
    assert "get_card" in text
    assert text == "Ready Toppers looks strong. (source: get_card)"

    # The follow-up turn fed the tool's ToolResult back as a toolResult block
    # that references the model's toolUseId.
    follow_up_messages = fake_client.calls[1]["messages"]
    tool_result_blocks = [
        block
        for message in follow_up_messages
        for block in message.get("content", [])
        if isinstance(block, dict) and "toolResult" in block
    ]
    assert tool_result_blocks, "expected a toolResult block on the follow-up turn"
    assert tool_result_blocks[0]["toolResult"]["toolUseId"] == "t1"


def test_raising_client_makes_answer_with_bedrock_raise(monkeypatch):
    """A client whose converse raises propagates so the engine can fall back."""
    raising_client = _RaisingConverseClient()
    _install_fake_boto3(monkeypatch, raising_client)

    with pytest.raises(Exception):
        bedrock_driver.answer_with_bedrock(
            "Why is Ready Toppers prioritized?",
            _run_result_with_ready_toppers(),
            None,
            _config(),
        )


def test_immediate_terminal_text_returns_text_with_no_tool_called(monkeypatch):
    """A first-call end_turn text returns the text, tool None, one converse."""
    terminal_response = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "I can help with the current promo run."}],
            }
        },
        "stopReason": "end_turn",
    }
    fake_client = _FakeConverseClient([terminal_response])
    _install_fake_boto3(monkeypatch, fake_client)

    text, tool_called = bedrock_driver.answer_with_bedrock(
        "What can you do?", None, None, _config()
    )

    assert len(fake_client.calls) == 1
    assert tool_called is None
    assert text == "I can help with the current promo run."

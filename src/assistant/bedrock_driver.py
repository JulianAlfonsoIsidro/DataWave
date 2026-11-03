"""Amazon Bedrock chat (Converse API with tool use) and JSON field extraction.

:func:`answer_with_bedrock` drives one chat turn through the boto3 Converse API
with tool use (Requirements 3.1, 3.3). It advertises the four
:data:`assistant.tools.TOOL_SPECS` tools, and whenever the model stops with
``stopReason == "tool_use"`` it dispatches the named tool, feeds the tool's
segment-level :class:`~assistant.models.ToolResult` back as a ``toolResult``
content block, and loops (bounded to a small number of iterations) until the
model returns a final text answer. It returns ``(final_text, tool_called)``.

``boto3`` is imported lazily *inside* the function so this module imports with
no AWS SDK installed and the engine's offline Mock path never needs boto3. Any
boto3/Bedrock error (including a missing ``boto3`` ``ImportError``) propagates
to the caller so the engine falls back to Mock Mode (Requirement 4.1).

:func:`extract_fields_json` is the strict-JSON upload extractor: a single
Converse call demanding JSON-only output with the seven form keys, parsed with
``json.loads`` after stripping any code fence. Any boto3/Bedrock error or
unparsable output raises so :func:`assistant.extract.extract_form` falls back to
the Mock rule extractor (Requirements 7.4, 7.5).
"""

from __future__ import annotations

import json
from typing import Any

from assistant.models import ToolResult
from assistant.prompts import EXTRACTION_SYSTEM_PROMPT, SYSTEM_PROMPT
from assistant.tools import (
    TOOL_SPECS,
    compare_segments,
    get_card,
    past_promo_accuracy,
    what_if,
)

__all__ = ["answer_with_bedrock", "extract_fields_json"]

# How many Converse round-trips to allow before giving up on a terminal text.
# Bounds the tool-use loop so a model that keeps requesting tools cannot run
# away (design: "bounded to a small max, e.g. 3 iterations").
_MAX_ITERATIONS = 3


def _tool_result_payload(result: ToolResult) -> dict[str, Any]:
    """Serialize a :class:`ToolResult` to a JSON-able dict for a tool result.

    Carries only the tool's segment-level data plus its status/note — never any
    individual client data, since the tools already project that away
    (Requirement 2.6).
    """
    return {
        "tool_name": result.tool_name,
        "ok": result.ok,
        "data": result.data,
        "note": result.note,
    }


def _dispatch_tool(name, tool_input, run_result, run_context) -> ToolResult:
    """Run the tool named ``name`` with the model-supplied ``tool_input``.

    Maps each advertised tool name to its function and supplies the right
    arguments from ``tool_input`` and the current run context. An unknown name
    (the model should never emit one, since only :data:`TOOL_SPECS` are
    advertised) yields an ``ok=False`` result rather than raising.
    """
    args = tool_input or {}
    if name == "get_card":
        return get_card(args.get("segment"), run_result)
    if name == "compare_segments":
        return compare_segments(run_result)
    if name == "what_if":
        return what_if(args.get("threshold_php"), run_result, run_context)
    if name == "past_promo_accuracy":
        return past_promo_accuracy(args.get("promo_id"))
    return ToolResult(str(name), False, {}, note="unknown tool")


def _final_text(message: dict[str, Any]) -> str:
    """Concatenate every ``{"text": ...}`` block in an assistant message."""
    parts = [
        block["text"]
        for block in message.get("content", [])
        if isinstance(block, dict) and "text" in block
    ]
    return "\n".join(part for part in parts if part).strip()


def answer_with_bedrock(question, run_result, run_context, config):
    """Drive the Converse API tool-use loop for one chat turn (Req 3.1, 3.3).

    Builds a ``bedrock-runtime`` client from ``config``, advertises the four
    :data:`TOOL_SPECS` tools, and calls ``converse`` with the
    :data:`~assistant.prompts.SYSTEM_PROMPT`. On ``stopReason == "tool_use"`` it
    dispatches each requested tool, appends the tool's :class:`ToolResult` as a
    ``toolResult`` content block, and loops (bounded to ``_MAX_ITERATIONS``)
    until the model returns text. ``boto3`` is imported lazily here so the module
    imports without the SDK and the Mock path never needs it.

    Args:
        question: The analyst's natural-language question.
        run_result: The current in-memory ``RunResult`` (or ``None``).
        run_context: The prebuilt :class:`assistant.tools.RunContext` (or
            ``None``) the run-needing tools use.
        config: The usable :class:`~assistant.models.ModelConfig`.

    Returns:
        tuple[str, str | None]: ``(final_text, tool_called)`` where
        ``tool_called`` is the last tool the model used, or ``None`` if none.

    Raises:
        Exception: Any boto3/Bedrock error (including a missing ``boto3``
            ``ImportError``) propagates so the engine falls back to Mock Mode
            (Requirement 4.1).
    """
    import boto3  # lazy: keep boto3 off the import path / Mock path

    client = boto3.client(
        "bedrock-runtime",
        aws_access_key_id=config.aws_access_key_id,
        aws_secret_access_key=config.aws_secret_access_key,
        region_name=config.aws_region,
    )

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"text": question}]}
    ]
    tool_config = {"tools": [{"toolSpec": spec} for spec in TOOL_SPECS]}

    tool_called: str | None = None
    last_text = ""

    for _ in range(_MAX_ITERATIONS):
        response = client.converse(
            modelId=config.bedrock_model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=messages,
            toolConfig=tool_config,
        )

        output_message = response["output"]["message"]
        messages.append(output_message)

        text = _final_text(output_message)
        if text:
            last_text = text

        if response.get("stopReason") != "tool_use":
            # Terminal turn (end_turn / max_tokens / etc.): return the text.
            return last_text, tool_called

        # The model requested one or more tools. Run each, record the tool that
        # produced the number (keep the last when several are used in one turn),
        # and send every result back in a single follow-up user turn.
        tool_result_blocks: list[dict[str, Any]] = []
        for block in output_message.get("content", []):
            if not isinstance(block, dict) or "toolUse" not in block:
                continue
            tool_use = block["toolUse"]
            name = tool_use.get("name")
            tool_called = name
            result = _dispatch_tool(
                name, tool_use.get("input"), run_result, run_context
            )
            tool_result_blocks.append(
                {
                    "toolResult": {
                        "toolUseId": tool_use.get("toolUseId"),
                        "content": [{"json": _tool_result_payload(result)}],
                    }
                }
            )

        messages.append({"role": "user", "content": tool_result_blocks})

    # Loop bound exhausted without a terminal text turn: return the best text we
    # gathered, or a short fallback, keeping the tool citation.
    if last_text:
        return last_text, tool_called
    return "I could not complete that request.", tool_called


def _strip_code_fence(text: str) -> str:
    """Remove a surrounding Markdown code fence from ``text`` if present.

    Models often wrap JSON in ```` ```json ... ``` ```` or ```` ``` ... ``` ````
    despite being told not to. This drops the opening fence (with an optional
    language tag) and the closing fence so :func:`json.loads` sees raw JSON.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    # Drop the first line (``` or ```json) and a trailing fence line.
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_fields_json(campaign_text, config) -> dict[str, Any]:
    """Ask Bedrock for STRICT JSON matching the seven form fields (Req 7.4).

    Makes a single ``converse`` call with
    :data:`~assistant.prompts.EXTRACTION_SYSTEM_PROMPT` as the system prompt and
    ``campaign_text`` as the user message, concatenates the response text blocks,
    strips any Markdown code fence, and parses the result with ``json.loads``.
    Returns the parsed raw candidate ``dict`` for ``validate_fields`` to check.

    Args:
        campaign_text: The plain text extracted from the Campaign_File.
        config: The usable :class:`~assistant.models.ModelConfig`.

    Returns:
        dict[str, Any]: The raw candidate values parsed from the model's JSON.

    Raises:
        Exception: Any boto3/Bedrock error (including a missing ``boto3``
            ``ImportError``) or unparsable/non-object output propagates so
            :func:`assistant.extract.extract_form` falls back to Mock Mode
            (Requirement 7.5).
    """
    import boto3  # lazy: keep boto3 off the import path / Mock path

    client = boto3.client(
        "bedrock-runtime",
        aws_access_key_id=config.aws_access_key_id,
        aws_secret_access_key=config.aws_secret_access_key,
        region_name=config.aws_region,
    )

    response = client.converse(
        modelId=config.bedrock_model_id,
        system=[{"text": EXTRACTION_SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": campaign_text}]}],
    )

    text = _final_text(response["output"]["message"])
    parsed = json.loads(_strip_code_fence(text))
    if not isinstance(parsed, dict):
        raise ValueError("Bedrock extraction did not return a JSON object")
    return parsed

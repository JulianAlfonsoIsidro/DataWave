"""Turn orchestrator: mode selection, guardrails, logging, and reply assembly.

:func:`answer_turn` is the single entry point the Ask Assistant tab calls for
one chat turn. It owns three decisions in order:

1. **Scope first.** An out-of-scope question (one with no campaign vocabulary)
   short-circuits to the fixed :data:`~assistant.guardrails.OUT_OF_SCOPE_REDIRECT`
   with no tool called and *no* AWS client ever constructed (Requirement 5.3,
   Property 8). The reported ``mode`` reflects configured usability -- ``bedrock``
   when credentials are present, ``mock`` otherwise -- without actually driving
   Bedrock, since no model call is needed to refuse.

2. **Driver selection (credential-driven, total).** When
   :attr:`ModelConfig.is_usable` is true the engine tries the Bedrock driver and,
   on *any* exception, falls back to the offline Mock driver and marks the turn
   ``mock``; it never propagates the error (Requirements 3.1, 4.1, Property 1).
   When credentials are absent it goes straight to Mock and constructs no AWS
   client at all (Requirement 4.1, Property 7). The Bedrock driver is imported
   lazily *inside* the ``is_usable`` branch so (a) the mock path never touches
   boto3 and (b) this module imports and its mock path works before the Bedrock
   driver (task 5.1) lands -- an ``ImportError``/``NotImplementedError`` from the
   stub is just another exception that triggers the Mock fallback.

3. **Guardrails, logging, reply.** The chosen driver's text is privacy-scrubbed
   then length-capped (Requirements 5.1, 5.2, 5.4), the turn is logged under
   ``scratch/`` (Requirement 6.1), and an :class:`~assistant.models.AssistantReply`
   carrying the final text, the mode actually taken, and the tool called (if any)
   is returned.

Run-context construction is resilient: :func:`tools.build_run_context` may raise
``FileNotFoundError`` when the fitted model artifact is absent; the engine
catches that and passes ``run_context=None`` so the tools degrade to a
needs-a-run / run-pipeline note rather than crashing (Requirement 1.4).
"""

from __future__ import annotations

from assistant import tools
from assistant.config import load_model_config
from assistant.guardrails import (
    OUT_OF_SCOPE_REDIRECT,
    cap_length,
    is_in_scope,
    scrub_privacy,
)
from assistant.logging_util import log_turn
from assistant.mock_driver import answer_with_mock
from assistant.models import AssistantReply

__all__ = ["answer_turn"]


def _ensure_run_context(run_context):
    """Return a usable RunContext, building one lazily when not supplied.

    When ``run_context`` is already provided it is used as-is. Otherwise a fresh
    context is built via :func:`tools.build_run_context`; a missing model
    artifact (``FileNotFoundError``) yields ``None`` so the tools fall back to
    their needs-a-run / run-pipeline notes instead of raising (Requirement 1.4).
    """
    if run_context is not None:
        return run_context
    try:
        return tools.build_run_context()
    except FileNotFoundError:
        return None


def answer_turn(question, run_result, run_context=None) -> AssistantReply:
    """Answer one chat turn end to end, returning an :class:`AssistantReply`.

    The engine selects the driver from :func:`load_model_config`: Bedrock only
    when the config is usable, Mock otherwise, and Mock again whenever a Bedrock
    attempt raises -- so mode selection is total and credential-driven and an
    exception is never propagated (Requirements 3.1, 4.1). Out-of-scope
    questions short-circuit to the fixed redirect with no tool called and no AWS
    client built (Requirement 5.3). The driver's text is privacy-scrubbed and
    length-capped, the turn is logged under ``scratch/``, and the final reply
    carries the mode actually taken (Requirements 5.1, 5.2, 5.4, 6.1).

    Args:
        question: The analyst's natural-language question.
        run_result: The current in-memory ``RunResult``, or ``None`` when no
            promo has been run yet (Requirement 1.4).
        run_context: An optional prebuilt :class:`tools.RunContext`; when
            ``None`` the engine builds one lazily and tolerates a missing model
            artifact by passing ``None`` to the tools.

    Returns:
        AssistantReply: ``text`` (scrubbed + capped), ``mode`` ("bedrock" or
        "mock"), and ``tool_called`` (the tool name, or ``None``).
    """
    cfg = load_model_config()

    # 1. Scope first. A question with no campaign vocabulary is refused with the
    #    fixed redirect and no tool -- in both configured modes -- and we never
    #    construct an AWS client to refuse (Requirement 5.3, Property 8). The
    #    reported mode reflects configured usability so the demo badge is honest
    #    about whether Bedrock *would* have been used, without a model call.
    if not is_in_scope(question):
        mode = "bedrock" if cfg.is_usable else "mock"
        text = cap_length(scrub_privacy(OUT_OF_SCOPE_REDIRECT))
        log_turn(question, None, text, mode)
        return AssistantReply(text=text, mode=mode, tool_called=None)

    # 2. Driver selection. Build the run context lazily (tolerating a missing
    #    model artifact) so both drivers' run-needing tools can work when the
    #    artifacts exist and degrade gracefully when they do not.
    resolved_context = _ensure_run_context(run_context)

    text: str
    tool_called: str | None
    mode: str

    if cfg.is_usable:
        try:
            # Lazy, defensive import: only on the usable branch, so the mock
            # path never imports boto3 and this module still imports (and its
            # mock path works) before the Bedrock driver lands (task 5.1). Any
            # exception -- ImportError, NotImplementedError from the current
            # stub, or a live boto3/Bedrock error -- triggers the Mock fallback.
            from assistant.bedrock_driver import answer_with_bedrock

            text, tool_called = answer_with_bedrock(
                question, run_result, resolved_context, cfg
            )
            mode = "bedrock"
        except Exception:
            text, tool_called = answer_with_mock(
                question, run_result, resolved_context
            )
            mode = "mock"
    else:
        # Not usable: go straight to Mock, constructing no AWS client at all
        # (Requirement 4.1, Property 7).
        text, tool_called = answer_with_mock(
            question, run_result, resolved_context
        )
        mode = "mock"

    # 3. Guardrails, logging, reply. Scrub client-id-shaped tokens then cap the
    #    length before logging and returning (Requirements 5.1, 5.2, 5.4, 6.3).
    text = cap_length(scrub_privacy(text))
    log_turn(question, tool_called, text, mode)
    return AssistantReply(text=text, mode=mode, tool_called=tool_called)

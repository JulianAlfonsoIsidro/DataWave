"""Property-based tests for the Part 6 engine: mode selection, citation, scope.

# Feature: part6-assistant, Property 1: mode selection is total and credential-driven
# Feature: part6-assistant, Property 2: numbers come only from tools, with a citation
# Feature: part6-assistant, Property 8: out-of-scope questions are refused in both modes

Covers three engine properties of the part6-assistant spec (task 4.3), driving
:func:`assistant.engine.answer_turn` with the credential source and the Bedrock
driver controlled by monkeypatch so no real AWS is touched and each example is
isolated:

- **Property 1 (mode selection is total and credential-driven):** the engine
  picks Bedrock only when ``ModelConfig.is_usable`` is true, Mock otherwise, and
  a *raising* Bedrock attempt still yields ``mode == "mock"`` (the exception is
  never propagated). When the config is not usable no AWS driver is ever
  entered. Validates Requirements 3.1, 4.1.

- **Property 2 (numbers come only from tools, with a citation):** any reply that
  reports a campaign number has a non-null ``tool_called`` whose name the answer
  text names; a reply whose ``tool_called`` is ``None`` (a scope refusal) carries
  no campaign number -- operationalized as equality with the fixed redirect.
  Validates Requirements 2.1, 2.6.

- **Property 8 (out-of-scope refusal in both modes):** a question lacking any
  campaign vocabulary returns the fixed ``OUT_OF_SCOPE_REDIRECT`` with no tool
  called, under both a usable-config and a not-usable-config setting. Validates
  Requirement 5.3.

Isolation strategy (applied by an autouse fixture):

- ``assistant.engine.load_model_config`` is replaced so each example's
  ``ModelConfig`` is fully controlled and no real ``.env`` / process environment
  leaks in.
- ``assistant.engine.log_turn`` is replaced with a recording no-op so turns
  never touch ``scratch/`` (the engine imported the name directly, so the patch
  lands on ``assistant.engine.log_turn``).
- ``assistant.engine.tools.build_run_context`` is made to raise
  ``FileNotFoundError`` so ``run_context`` resolves to ``None`` and the tests
  stay fast and fully offline (no model artifact or data bundle is read).

The Bedrock driver is controlled by patching ``assistant.bedrock_driver`` --
which the engine imports lazily *inside* the usable branch -- so a usable config
drives whatever fake we install, and we can assert the driver is never entered
when the config is not usable.
"""

from __future__ import annotations

import sys
import types

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Each test installs its own patches via the ``monkeypatch`` fixture (and the
# autouse isolation fixture). Hypothesis warns that a function-scoped fixture is
# not reset between generated inputs; here that is safe because every example
# re-installs its own ``load_model_config`` / ``answer_with_bedrock`` before
# calling the engine, overwriting the prior example's patch. Suppress the health
# check rather than restructure, matching the pure-function style of the other
# part6 property tests.
_SUPPRESS_FIXTURE = [HealthCheck.function_scoped_fixture]

from assistant import engine
from assistant.guardrails import OUT_OF_SCOPE_REDIRECT
from assistant.models import ModelConfig

# Four in-scope questions, one per tool route the Mock driver resolves. Used by
# the citation property so each kind of reply is exercised.
_IN_SCOPE_QUESTIONS = [
    "Why is Ready Toppers prioritized?",   # get_card
    "Compare all segments for this promo",  # compare_segments
    "What if the threshold is P300,000?",   # what_if
    "How accurate was P001?",               # past_promo_accuracy
]

# Clearly off-topic questions carrying no campaign vocabulary at all, so
# is_in_scope is False and the engine must refuse.
_OUT_OF_SCOPE_QUESTIONS = [
    "What's the weather like today?",
    "Tell me a joke about cats",
    "How do I cook adobo?",
    "Who won the basketball game last night?",
    "Translate hello into French",
]


# ---------------------------------------------------------------------------
# Isolation fixture: control credentials, logging, and the run context.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_engine(monkeypatch):
    """Keep every example offline, log-free, and context-free.

    - ``build_run_context`` raises ``FileNotFoundError`` so ``run_context``
      resolves to ``None`` (no model/data read -> fast and hermetic).
    - ``log_turn`` becomes a recording no-op so no ``scratch/`` write happens;
      the recorded calls let a test assert logging still ran.
    """
    def _raise_no_context(*args, **kwargs):
        raise FileNotFoundError("no run context in tests")

    monkeypatch.setattr(
        engine.tools, "build_run_context", _raise_no_context, raising=True
    )

    logged: list[tuple] = []

    def _record_log(question, tool_called, answer, mode):
        logged.append((question, tool_called, answer, mode))

    monkeypatch.setattr(engine, "log_turn", _record_log, raising=True)
    return logged


# ---------------------------------------------------------------------------
# Strategies for ModelConfig: a usable config and an unusable one.
# ---------------------------------------------------------------------------

_PRESENT = st.text(min_size=1, max_size=12).filter(lambda s: s.strip() != "")
# A "missing" value is either None or the empty string -- both falsy, so the
# corresponding ModelConfig field drives ``is_usable`` to False. (A
# whitespace-only string like "   " is deliberately excluded: ``is_usable`` is a
# plain truthiness check over the four fields, so a non-empty whitespace string
# counts as *present* -- using it here would not make the config unusable.)
_MISSING = st.sampled_from([None, ""])


@st.composite
def _usable_config(draw: st.DrawFn) -> ModelConfig:
    """A ModelConfig with all four settings present (is_usable True)."""
    return ModelConfig(
        aws_access_key_id=draw(_PRESENT),
        aws_secret_access_key=draw(_PRESENT),
        aws_region=draw(_PRESENT),
        bedrock_model_id=draw(_PRESENT),
    )


@st.composite
def _unusable_config(draw: st.DrawFn) -> ModelConfig:
    """A ModelConfig with at least one of the four settings missing.

    Each field is independently present-or-missing, with at least one forced
    missing, so ``is_usable`` is guaranteed False across the whole input space.
    """
    values = {
        "aws_access_key_id": draw(st.one_of(_PRESENT, _MISSING)),
        "aws_secret_access_key": draw(st.one_of(_PRESENT, _MISSING)),
        "aws_region": draw(st.one_of(_PRESENT, _MISSING)),
        "bedrock_model_id": draw(st.one_of(_PRESENT, _MISSING)),
    }
    # Force at least one field missing so is_usable is always False.
    forced = draw(st.sampled_from(list(values)))
    values[forced] = draw(_MISSING)
    return ModelConfig(**values)


def _install_config(monkeypatch, config: ModelConfig):
    """Make ``engine.load_model_config`` return the given config."""
    monkeypatch.setattr(
        engine, "load_model_config", lambda: config, raising=True
    )


def _install_bedrock(monkeypatch, fn):
    """Install a fake ``answer_with_bedrock`` the engine's lazy import will find.

    The engine does ``from assistant.bedrock_driver import answer_with_bedrock``
    inside its usable branch, so a module object exposing that attribute must be
    present in ``sys.modules`` under ``assistant.bedrock_driver``.
    """
    module = types.ModuleType("assistant.bedrock_driver")
    module.answer_with_bedrock = fn
    monkeypatch.setitem(sys.modules, "assistant.bedrock_driver", module)


# ---------------------------------------------------------------------------
# Property 1: mode selection is total and credential-driven (Req 3.1, 4.1)
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=None, suppress_health_check=_SUPPRESS_FIXTURE)
@given(_unusable_config())
def test_not_usable_config_never_enters_bedrock(monkeypatch, config):
    """A not-usable config answers in Mock Mode and never calls Bedrock.

    The engine goes straight to Mock, so the fake ``answer_with_bedrock`` -- set
    to blow up if entered -- must never be called, and the reply's ``mode`` is
    ``"mock"`` (Requirement 4.1, Property 1 Case A).

    **Validates: Requirements 3.1, 4.1**
    """
    assert config.is_usable is False
    _install_config(monkeypatch, config)

    called = {"bedrock": False}

    def _must_not_call(*args, **kwargs):
        called["bedrock"] = True
        raise AssertionError("Bedrock must not be entered for an unusable config")

    _install_bedrock(monkeypatch, _must_not_call)

    reply = engine.answer_turn("Why is Ready Toppers prioritized?", None)

    assert reply.mode == "mock"
    assert called["bedrock"] is False


@settings(max_examples=50, deadline=None, suppress_health_check=_SUPPRESS_FIXTURE)
@given(_usable_config())
def test_usable_config_with_raising_bedrock_falls_back_to_mock(monkeypatch, config):
    """A raising Bedrock attempt still yields ``mode == "mock"`` (no propagation).

    With a usable config the engine enters Bedrock; when that call raises, the
    engine must fall back to Mock and return a reply with ``mode == "mock"``
    rather than letting the exception escape (Requirement 4.1, Property 1 Case B).

    **Validates: Requirements 3.1, 4.1**
    """
    assert config.is_usable is True
    _install_config(monkeypatch, config)

    entered = {"bedrock": False}

    def _raising_bedrock(*args, **kwargs):
        entered["bedrock"] = True
        raise RuntimeError("simulated Bedrock failure")

    _install_bedrock(monkeypatch, _raising_bedrock)

    reply = engine.answer_turn("Why is Ready Toppers prioritized?", None)

    assert entered["bedrock"] is True  # it did try Bedrock first
    assert reply.mode == "mock"        # and fell back without raising


@settings(max_examples=50, deadline=None, suppress_health_check=_SUPPRESS_FIXTURE)
@given(_usable_config())
def test_usable_config_with_working_bedrock_reports_bedrock(monkeypatch, config):
    """A usable config + a working Bedrock driver reports ``mode == "bedrock"``.

    The engine returns the driver's text and tool, so a fake that returns a
    tool-cited answer and ``"get_card"`` yields ``mode == "bedrock"`` and
    ``tool_called == "get_card"`` (Requirement 3.1, Property 1 Case C). An
    in-scope question is used so the scope check does not short-circuit.

    **Validates: Requirements 3.1, 4.1**
    """
    assert config.is_usable is True
    _install_config(monkeypatch, config)

    def _working_bedrock(question, run_result, run_context, cfg):
        return ("Ready Toppers looks strong (source: get_card)", "get_card")

    _install_bedrock(monkeypatch, _working_bedrock)

    reply = engine.answer_turn("Why is Ready Toppers prioritized?", None)

    assert reply.mode == "bedrock"
    assert reply.tool_called == "get_card"
    assert "get_card" in reply.text


# ---------------------------------------------------------------------------
# Property 2: numbers come only from tools, with a citation (Req 2.1, 2.6)
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=None, suppress_health_check=_SUPPRESS_FIXTURE)
@given(
    config=_unusable_config(),
    question=st.sampled_from(_IN_SCOPE_QUESTIONS),
)
def test_in_scope_reply_cites_the_tool_it_called(monkeypatch, config, question):
    """An in-scope reply with a tool names that tool in its text (Req 2.6).

    Driven in Mock Mode (not-usable config, ``run_result=None``) across the four
    in-scope question kinds. Whenever ``tool_called`` is not ``None`` the reply
    text must name that tool (the Mock templates cite ``(source: <tool>)``), so
    any surfaced number is attributable to a tool (Requirements 2.1, 2.6).

    **Validates: Requirements 2.1, 2.6**
    """
    _install_config(monkeypatch, config)
    # Guard: Bedrock must never be entered for a not-usable config.
    _install_bedrock(
        monkeypatch,
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("Bedrock must not run in Mock Mode")
        ),
    )

    reply = engine.answer_turn(question, None)

    assert reply.mode == "mock"
    if reply.tool_called is not None:
        assert reply.tool_called in reply.text


@settings(max_examples=50, deadline=None, suppress_health_check=_SUPPRESS_FIXTURE)
@given(
    config=st.one_of(_usable_config(), _unusable_config()),
    question=st.sampled_from(_OUT_OF_SCOPE_QUESTIONS),
)
def test_null_tool_called_carries_no_campaign_number(monkeypatch, config, question):
    """A null ``tool_called`` reply carries no campaign number (Req 2.1).

    An out-of-scope question yields the fixed redirect with ``tool_called is
    None``; operationalize "carries no campaign number" as equality with
    ``OUT_OF_SCOPE_REDIRECT`` (which contains no tool-sourced digits). Holds
    whether the config is usable or not (Requirement 2.1).

    **Validates: Requirements 2.1, 2.6**
    """
    _install_config(monkeypatch, config)
    # Even for a usable config a refusal must not enter Bedrock.
    _install_bedrock(
        monkeypatch,
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("a scope refusal must not enter Bedrock")
        ),
    )

    reply = engine.answer_turn(question, None)

    assert reply.tool_called is None
    assert reply.text == OUT_OF_SCOPE_REDIRECT


# ---------------------------------------------------------------------------
# Property 8: out-of-scope questions are refused in both modes (Req 5.3)
# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None, suppress_health_check=_SUPPRESS_FIXTURE)
@given(
    config=st.one_of(_usable_config(), _unusable_config()),
    question=st.sampled_from(_OUT_OF_SCOPE_QUESTIONS),
)
def test_out_of_scope_refused_in_both_modes(monkeypatch, config, question):
    """Out-of-scope questions get the fixed redirect with no tool, in both modes.

    Under both a usable-config and a not-usable-config setting, a question with
    no campaign vocabulary returns exactly ``OUT_OF_SCOPE_REDIRECT`` with
    ``tool_called is None``. The redirect is short and carries no ``client_id``,
    so the privacy scrub and length cap leave it unchanged. No AWS driver is
    entered to refuse (Requirement 5.3).

    **Validates: Requirements 5.3**
    """
    _install_config(monkeypatch, config)
    _install_bedrock(
        monkeypatch,
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("a scope refusal must not enter Bedrock")
        ),
    )

    reply = engine.answer_turn(question, None)

    assert reply.text == OUT_OF_SCOPE_REDIRECT
    assert reply.tool_called is None
    # The reported mode reflects configured usability (honest demo badge) but no
    # model call was made to produce the refusal.
    assert reply.mode == ("bedrock" if config.is_usable else "mock")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

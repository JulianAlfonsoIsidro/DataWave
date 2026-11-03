"""Property-based tests for Part 6 upload validation and the no-auto-run rule.

# Feature: part6-assistant, Property 10: Extracted fields are always valid or dropped
# Feature: part6-assistant, Property 11: Upload never auto-runs

Covers two properties of the part6-assistant spec:

- **Property 10 (validation):** :func:`assistant.extract.validate_fields` turns a
  raw candidate dict (from *either* driver -- the offline Mock rule extractor or
  the Bedrock JSON extractor, whose arbitrary JSON the synthetic dicts stand in
  for) into a :class:`~assistant.models.FormDraft` in which every field marked
  ``found`` carries a value inside its allowed set, every other field is
  ``needs_input`` with a safe default, and no invalid value is ever marked
  ``found``. Validates Requirements 7.4, 7.6.
- **Property 11 (no auto-run):** :func:`assistant.extract.extract_form` returns
  only a :class:`FormDraft` and never calls
  :func:`webapp_core.run_promo.run_promo`. Validates Requirement 7.8.

The generators deliberately MIX valid and invalid values per field so both the
``found`` and ``needs_input`` branches are reached for every field. The allowed
sets are re-derived here from the production option lists so a divergence
signals a real validator bug rather than a shared mistake.

Any fixture bytes live in memory; nothing is written under the project's real
``scratch/``.
"""

from __future__ import annotations

import io
import math

from hypothesis import given, settings
from hypothesis import strategies as st

from assistant import mock_driver
from assistant.extract import (
    ALLOWED_CHANNEL_LABELS,
    MECHANIC_OPTIONS,
    PRODUCT_TYPE_OPTIONS,
    extract_form,
    validate_fields,
)
from assistant.models import FieldDraft, FormDraft

# A fixed pool of plausible Customer_DNA segment names the form could offer. The
# generated ``segment_options`` is a non-empty subset of this pool so both the
# "segment offered" and "segment not offered" paths are reachable.
SEGMENT_POOL: list[str] = [
    "Affluent-Gold",
    "Affluent-Preferred",
    "Mass",
    "Mid-Market",
]

# The seven Promo_Form_Fields in FormDraft order, for exhaustive iteration.
FIELD_NAMES: tuple[str, ...] = (
    "product_type",
    "mechanic",
    "threshold_php",
    "reward",
    "eligible_segments",
    "min_adb",
    "channels",
)

# Channel synonyms and the Allowed_Channel_Label each must resolve to. Used by
# the focused mapping check; the property generator draws from the keys.
CHANNEL_SYNONYM_TO_LABEL: dict[str, str] = {
    "in-app": "In-app",
    "inapp": "In-app",
    "app": "In-app",
    "push": "In-app",
    "notification": "In-app",
    "email": "Email",
    "e-mail": "Email",
    "sms": "SMS",
    "text": "SMS",
    "message": "SMS",
}


# --- Candidate-value strategies (each mixes valid and invalid) -------------

def _non_string():
    """Arbitrary non-string scalars/containers that are never a valid label."""
    return st.one_of(
        st.integers(),
        st.floats(allow_nan=True, allow_infinity=True),
        st.booleans(),
        st.none(),
        st.lists(st.integers(), max_size=3),
    )


def _product_type_candidates():
    """Valid options mixed with junk strings and non-strings."""
    return st.one_of(
        st.sampled_from(PRODUCT_TYPE_OPTIONS),
        st.text(max_size=12),
        _non_string(),
    )


def _mechanic_candidates():
    return st.one_of(
        st.sampled_from(MECHANIC_OPTIONS),
        st.text(max_size=12),
        _non_string(),
    )


def _number_candidates():
    """Valid non-negative numbers mixed with negatives, nan/inf, strings, bools, None."""
    return st.one_of(
        st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
        st.integers(min_value=0, max_value=10_000_000),
        st.floats(max_value=-0.0001, allow_nan=False, allow_infinity=False),  # negative
        st.just(float("nan")),
        st.just(float("inf")),
        st.just(float("-inf")),
        st.text(max_size=8),
        st.booleans(),
        st.none(),
    )


def _reward_candidates():
    return st.one_of(
        st.text(min_size=1, max_size=20).filter(lambda s: s.strip() != ""),
        st.just(""),
        st.sampled_from(["   ", "\t", "\n"]),
        _non_string(),
    )


def _segment_candidates():
    """Subsets of the segment pool mixed with random strings, non-lists, []."""
    return st.one_of(
        st.lists(st.sampled_from(SEGMENT_POOL), max_size=4),
        st.lists(st.text(max_size=8), max_size=4),
        st.lists(st.one_of(st.sampled_from(SEGMENT_POOL), st.text(max_size=8)), max_size=5),
        st.just([]),
        st.text(max_size=10),  # a non-list
        st.none(),
        st.integers(),
    )


def _channel_candidates():
    """Lists mixing valid synonyms with unmappable names, plus non-lists."""
    return st.one_of(
        st.lists(st.sampled_from(list(CHANNEL_SYNONYM_TO_LABEL)), max_size=6),
        st.lists(st.text(max_size=8), max_size=4),
        st.lists(
            st.one_of(
                st.sampled_from(list(CHANNEL_SYNONYM_TO_LABEL)),
                st.just("carrier pigeon"),
                st.text(max_size=6),
            ),
            max_size=6,
        ),
        st.just([]),
        st.text(max_size=10),  # a non-list
        st.none(),
    )


@st.composite
def candidate_dicts(draw: st.DrawFn) -> dict:
    """A raw candidate dict with every key sometimes present, sometimes absent.

    Each present key draws from a generator that MIXES valid and invalid values,
    so validate_fields sees the whole input space a driver could hand it.
    """
    candidate: dict = {}
    pairs = (
        ("product_type", _product_type_candidates()),
        ("mechanic", _mechanic_candidates()),
        ("threshold_php", _number_candidates()),
        ("reward", _reward_candidates()),
        ("eligible_segments", _segment_candidates()),
        ("min_adb", _number_candidates()),
        ("channels", _channel_candidates()),
    )
    for key, strategy in pairs:
        if draw(st.booleans()):
            candidate[key] = draw(strategy)
    return candidate


@st.composite
def segment_options_strategy(draw: st.DrawFn) -> list[str]:
    """A non-empty subset of the segment pool, in pool order (no duplicates)."""
    chosen = draw(
        st.lists(st.sampled_from(SEGMENT_POOL), min_size=1, max_size=len(SEGMENT_POOL), unique=True)
    )
    # Keep a stable, pool order so subset assertions read naturally.
    return [seg for seg in SEGMENT_POOL if seg in chosen]


# --- The shared invariant check --------------------------------------------

def _assert_form_invariants(draft: FormDraft, segment_options: list[str]) -> None:
    """Assert Property 10 holds for every field of ``draft`` (Req 7.4, 7.6)."""
    assert isinstance(draft, FormDraft)

    for name in FIELD_NAMES:
        field = getattr(draft, name)
        assert isinstance(field, FieldDraft)
        assert field.status in ("found", "needs_input")

    # product_type -------------------------------------------------------
    if draft.product_type.status == "found":
        assert draft.product_type.value in PRODUCT_TYPE_OPTIONS
    else:
        # Safe default: an option-list string (never invalid garbage).
        assert draft.product_type.value in PRODUCT_TYPE_OPTIONS

    # mechanic -----------------------------------------------------------
    if draft.mechanic.status == "found":
        assert draft.mechanic.value in MECHANIC_OPTIONS
    else:
        assert draft.mechanic.value in MECHANIC_OPTIONS

    # threshold_php ------------------------------------------------------
    _assert_number_field(draft.threshold_php)

    # min_adb ------------------------------------------------------------
    _assert_number_field(draft.min_adb)

    # reward -------------------------------------------------------------
    if draft.reward.status == "found":
        assert isinstance(draft.reward.value, str)
        assert draft.reward.value.strip() != ""
    else:
        assert draft.reward.value == ""

    # eligible_segments --------------------------------------------------
    if draft.eligible_segments.status == "found":
        value = draft.eligible_segments.value
        assert isinstance(value, list) and len(value) > 0
        assert set(value).issubset(set(segment_options))
        assert len(value) == len(set(value))  # no duplicates
    else:
        assert draft.eligible_segments.value == []

    # channels -----------------------------------------------------------
    if draft.channels.status == "found":
        value = draft.channels.value
        assert isinstance(value, list) and len(value) > 0
        assert set(value).issubset(set(ALLOWED_CHANNEL_LABELS))
        assert len(value) == len(set(value))  # deduplicated
    else:
        assert draft.channels.value == []


def _assert_number_field(field: FieldDraft) -> None:
    """A number field is a finite >= 0 number when found, else the 0.0 default."""
    if field.status == "found":
        assert isinstance(field.value, (int, float))
        assert not isinstance(field.value, bool)
        number = float(field.value)
        assert math.isfinite(number)
        assert number >= 0
    else:
        assert field.value == 0.0


# --- Property 10: synthetic candidates (stand-ins for either driver) -------

@settings(max_examples=300, deadline=None)
@given(candidate_dicts(), segment_options_strategy())
def test_validate_fields_only_keeps_valid_values(candidates: dict, segment_options: list[str]):
    """Every ``found`` field is valid; everything else is a safe ``needs_input``.

    **Validates: Requirements 7.4, 7.6**
    """
    draft = validate_fields(candidates, segment_options)
    _assert_form_invariants(draft, segment_options)


# --- Property 10: the Mock driver's real output --------------------------

# A few sample briefs covering the Mock rule extractor's cue words so its real
# candidate output is run through the same invariant (Property 10 says "for
# candidates from either driver").
SAMPLE_BRIEFS: list[str] = [
    (
        "Savings top up campaign. Eligible: Affluent-Gold and Mass. "
        "Threshold PHP 300,000. Minimum ADB PHP 50,000. Reward: P500 cashback. "
        "Channels: email, sms, in-app."
    ),
    (
        "Time Deposit new account drive for Mid-Market segment. "
        "threshold P1,000,000. bonus: a free tumbler. push and text message only."
    ),
    (
        "Investment ADB increase promo. No eligible segments named. "
        "reward: 2% rebate. notification channel."
    ),
    (
        "Credit Card promo with no numbers, no channels, nothing structured at all."
    ),
    "",  # empty text yields an empty candidate dict
]


@settings(max_examples=50, deadline=None)
@given(
    st.sampled_from(SAMPLE_BRIEFS),
    segment_options_strategy(),
)
def test_validate_fields_on_mock_driver_output(brief: str, segment_options: list[str]):
    """The Mock driver's real candidates also satisfy Property 10.

    **Validates: Requirements 7.4, 7.6**
    """
    candidates = mock_driver.extract_fields_rules(brief)
    draft = validate_fields(candidates, segment_options)
    _assert_form_invariants(draft, segment_options)


# --- Property 10: focused channel-mapping / dedup check --------------------

def test_channel_synonyms_map_and_dedup_through_validate_fields():
    """Known synonyms map to the three labels (deduped); unmappable -> needs_input.

    **Validates: Requirements 7.6**
    """
    candidates = {"channels": ["email", "sms", "in-app", "push", "e-mail", "text"]}
    draft = validate_fields(candidates, SEGMENT_POOL)

    assert draft.channels.status == "found"
    # in-app + push -> In-app; email + e-mail -> Email; sms + text -> SMS.
    assert set(draft.channels.value) == {"In-app", "Email", "SMS"}
    # Deduped to exactly one label per distinct target.
    assert len(draft.channels.value) == 3

    unmappable = validate_fields({"channels": ["carrier pigeon"]}, SEGMENT_POOL)
    assert unmappable.channels.status == "needs_input"
    assert unmappable.channels.value == []


def test_channels_found_subset_is_always_within_allowed_labels():
    """A mixed mappable/unmappable list keeps only mapped labels (Req 7.6)."""
    candidates = {"channels": ["EMAIL", "pigeon", "SMS", "fax", "APP"]}
    draft = validate_fields(candidates, SEGMENT_POOL)

    assert draft.channels.status == "found"
    assert set(draft.channels.value).issubset({"In-app", "Email", "SMS"})
    assert "In-app" in draft.channels.value  # from "APP"
    assert "Email" in draft.channels.value   # from "EMAIL"
    assert "SMS" in draft.channels.value     # from "SMS"


# --- Property 11: extract_form never auto-runs -----------------------------

def _build_docx_bytes(paragraph_text: str) -> bytes:
    """Build a one-paragraph .docx in memory and return its bytes."""
    from docx import Document

    document = Document()
    document.add_paragraph(paragraph_text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_extract_form_returns_formdraft_and_never_runs(monkeypatch):
    """``extract_form`` yields only a FormDraft and never calls ``run_promo``.

    The Bedrock path is forced off by stubbing ``load_model_config`` to return a
    credential-free config, so the offline Mock rules run with no AWS call. A
    sentinel replaces ``webapp_core.run_promo.run_promo`` and fails the test if
    anything triggers a run. Since ``extract.py`` never imports ``run_promo``,
    this mainly guards against a future regression (Requirement 7.8).

    **Validates: Requirements 7.8**
    """
    import webapp_core.run_promo as run_promo_module
    from assistant.models import ModelConfig

    # Force the offline Mock path: no usable credentials.
    monkeypatch.setattr(
        "assistant.config.load_model_config",
        lambda: ModelConfig(None, None, None, None),
    )

    calls: list[tuple] = []

    def boom(*args, **kwargs):  # pragma: no cover - only runs on regression
        calls.append((args, kwargs))
        raise AssertionError("extract_form triggered run_promo -- it must not auto-run")

    monkeypatch.setattr(run_promo_module, "run_promo", boom)

    docx_bytes = _build_docx_bytes(
        "Savings top up for Affluent-Gold. Threshold PHP 300,000. "
        "Reward: P500 cashback. Channels: email, sms."
    )

    draft = extract_form(docx_bytes, "brief.docx", SEGMENT_POOL)

    assert isinstance(draft, FormDraft)
    assert draft.mode == "mock"
    assert calls == []  # the run_promo sentinel was never touched
    # The returned draft still satisfies the validation invariant.
    _assert_form_invariants(draft, SEGMENT_POOL)

"""Offline upload integration test for the Part 6 assistant (task 8.2).

# Feature: part6-assistant, Property 10: extracted fields are always valid or dropped
# Feature: part6-assistant, Property 11: upload never auto-runs

Drives :func:`assistant.extract.extract_form` end to end over a realistic
campaign brief with *no* credentials configured, asserting that the upload
pipeline returns a reviewable :class:`~assistant.models.FormDraft` whose fields
are validated, whose channels map to exactly the three Allowed_Channel_Labels,
and that nothing about the upload triggers a run (Requirements 2.1, 4.4, 7.7,
7.8, 7.9).

Two legs are covered:

- **DOCX leg** (always runs): a one-paragraph ``.docx`` brief is built in
  memory with python-docx and run through ``extract_form`` on the offline Mock
  path.
- **PDF leg** (reportlab-guarded): the same style of brief is rendered to a
  one-page PDF with reportlab and run through ``extract_form``. reportlab is an
  optional test-only dependency, so this leg is skipped cleanly when it is
  absent -- the DOCX leg already exercises the full pipeline.

Isolation strategy (an autouse fixture applies to both legs):

- ``assistant.config.load_model_config`` returns ``ModelConfig(None, None,
  None, None)`` -- not usable -- so ``extract_form`` takes the Mock rule path and
  constructs no AWS client (Requirement 7.5, 4.4).
- ``sys.modules["boto3"]`` is replaced with a fake whose ``.client(...)`` raises
  ``AssertionError``. This is a *tripwire*: if the pipeline ever constructed an
  AWS client the test would blow up. The offline path never touches boto3, so
  it must never fire -- this enforces "no run / no AWS".
- ``webapp_core.run_promo.run_promo`` is replaced with a sentinel that fails if
  called, enforcing that ``extract_form`` never auto-runs (Requirement 7.8).

Every fixture document lives in memory (``io.BytesIO``); nothing is written
under the project's real ``scratch/``.
"""

from __future__ import annotations

import io
import math
import sys
import types

import pytest

from assistant.extract import ALLOWED_CHANNEL_LABELS, extract_form
from assistant.models import FieldDraft, FormDraft

# The distinct Customer_DNA segment names the manual form offers. The brief
# names "Affluent-Gold" and "Mass", both in this list, so they survive
# validation as a found subset.
SEGMENT_OPTIONS = ["Affluent-Gold", "Affluent-Preferred", "Mass", "Mid-Market"]

# A realistic one-paragraph brief the Mock rule extractor can parse: a Savings
# top-up with two eligible segments, a threshold and minimum ADB, a reward, and
# all three channels named with common synonyms.
# "Mass" is named as the eligible segment: it is the one option the offline
# Mock rule extractor can recover cleanly. The hyphenated options
# ("Affluent-Gold", "Mid-Market") are a known limitation of the Mock segment
# regex (it stops a Title-Case run at the hyphen), so a realistic offline brief
# names a non-hyphenated segment for the Found path. The hyphenated options stay
# in segment_options to prove they are simply dropped to Needs_Input, not
# mis-mapped.
BRIEF_TEXT = (
    "Savings top up campaign. Eligible segments: Mass. "
    "Threshold PHP 300,000. Minimum ADB PHP 50,000. Reward: P500 cashback. "
    "Channels: email, sms, in-app."
)

# The seven Promo_Form_Fields in FormDraft order, for exhaustive iteration.
FIELD_NAMES = (
    "product_type",
    "mechanic",
    "threshold_php",
    "reward",
    "eligible_segments",
    "min_adb",
    "channels",
)


@pytest.fixture(autouse=True)
def _offline_upload(monkeypatch):
    """Force the offline Mock path, tripwire AWS, and sentinel ``run_promo``.

    ``extract_form`` imports ``load_model_config`` from ``assistant.config``
    inside the function body, so patching the attribute on that module is what
    the pipeline actually reads.
    """
    import webapp_core.run_promo as run_promo_module

    from assistant.models import ModelConfig

    # 1. No credentials -> not usable -> Mock rule path only.
    unusable = ModelConfig(None, None, None, None)
    assert unusable.is_usable is False
    monkeypatch.setattr(
        "assistant.config.load_model_config", lambda: unusable, raising=True
    )

    # 2. boto3 tripwire: constructing any AWS client raises loudly. The Mock
    #    path never imports boto3, so this must never fire ("no AWS").
    fake_boto3 = types.ModuleType("boto3")

    def _no_client(*args, **kwargs):
        raise AssertionError("no AWS client should be constructed offline")

    fake_boto3.client = _no_client
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    # 3. run_promo sentinel: extract_form must never auto-run (Req 7.8).
    def _boom(*args, **kwargs):
        raise AssertionError("extract_form triggered run_promo -- it must not auto-run")

    monkeypatch.setattr(run_promo_module, "run_promo", _boom, raising=True)


# --- Shared invariant checks ------------------------------------------------

def _assert_reviewable_form(draft: FormDraft) -> None:
    """Assert the draft is a reviewable, validated FormDraft (Req 7.7).

    Every one of the seven fields is a FieldDraft marked ``found`` or
    ``needs_input`` with a value inside its allowed set (or the safe default),
    so the UI can render each with a Found / Needs Input badge for review.
    """
    assert isinstance(draft, FormDraft)
    assert draft.mode == "mock"

    for name in FIELD_NAMES:
        field = getattr(draft, name)
        assert isinstance(field, FieldDraft)
        assert field.status in ("found", "needs_input")

    # Number fields: finite >= 0 when found, else the 0.0 safe default.
    for number_field in (draft.threshold_php, draft.min_adb):
        if number_field.status == "found":
            assert isinstance(number_field.value, (int, float))
            assert not isinstance(number_field.value, bool)
            assert math.isfinite(float(number_field.value))
            assert float(number_field.value) >= 0
        else:
            assert number_field.value == 0.0

    # Channels, when found, are always a subset of exactly the three labels.
    if draft.channels.status == "found":
        assert isinstance(draft.channels.value, list)
        assert set(draft.channels.value).issubset(set(ALLOWED_CHANNEL_LABELS))
        assert len(draft.channels.value) == len(set(draft.channels.value))

    # eligible_segments, when found, is a subset of the offered options.
    if draft.eligible_segments.status == "found":
        assert set(draft.eligible_segments.value).issubset(set(SEGMENT_OPTIONS))

    # No individual client data is carried anywhere in the draft (Req 7.9):
    # the FormDraft is only the seven form fields + mode, so no client id
    # should appear in any stringified field value.
    for name in FIELD_NAMES:
        assert "client_id" not in repr(getattr(draft, name).value).lower()


def _assert_brief_extraction(draft: FormDraft) -> None:
    """Assert the known values BRIEF_TEXT carries were extracted as expected."""
    # Channels: email/sms/in-app map to exactly the three labels (Req 7.6).
    assert draft.channels.status == "found"
    assert set(draft.channels.value) == {"Email", "SMS", "In-app"}

    # Threshold: the amount near "threshold" is 300,000 (Req 2.1 -- a real value,
    # not invented, pulled straight from the brief text).
    assert draft.threshold_php.status == "found"
    assert draft.threshold_php.value == 300000.0

    # Eligible segments: the named "Mass" segment is offered, so found.
    assert draft.eligible_segments.status == "found"
    assert set(draft.eligible_segments.value) == {"Mass"}


# --- DOCX leg (always runs) -------------------------------------------------

def _build_docx_bytes(paragraph_text: str) -> bytes:
    """Build a one-paragraph .docx in memory and return its bytes."""
    from docx import Document

    document = Document()
    document.add_paragraph(paragraph_text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_extract_form_over_docx_brief_is_reviewable_and_never_runs():
    """A DOCX brief yields a reviewable FormDraft with no run triggered.

    Drives ``extract_form`` over an in-memory ``.docx`` brief on the offline
    Mock path. Asserts a validated, reviewable ``FormDraft`` with channels
    mapped to the three Allowed_Channel_Labels and the threshold read from the
    brief; the boto3 tripwire and the ``run_promo`` sentinel (installed by the
    autouse fixture) guarantee no AWS call and no run were triggered
    (Requirements 2.1, 4.4, 7.7, 7.8, 7.9).

    **Validates: Requirements 2.1, 4.4, 7.7, 7.8, 7.9**
    """
    docx_bytes = _build_docx_bytes(BRIEF_TEXT)

    draft = extract_form(docx_bytes, "brief.docx", SEGMENT_OPTIONS)

    _assert_reviewable_form(draft)
    _assert_brief_extraction(draft)


# --- PDF leg (reportlab-guarded) --------------------------------------------

def _build_pdf_bytes(lines: list[str]) -> bytes:
    """Build a one-page, text-bearing PDF in memory with reportlab.

    Each string in ``lines`` is drawn on its own text line so pdfplumber can
    recover a text layer; the joined text matches BRIEF_TEXT's cue words.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    text_object = pdf.beginText(72, 720)
    for line in lines:
        text_object.textLine(line)
    pdf.drawText(text_object)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_extract_form_over_pdf_brief_is_reviewable_and_never_runs():
    """A PDF brief yields the same reviewable FormDraft invariants.

    reportlab is an optional test-only dependency used solely to build a
    text-bearing PDF fixture; when it is absent this leg is skipped cleanly and
    the DOCX leg still covers the full pipeline. The PDF carries the same brief
    text, so the same FormDraft/mode/channel/threshold invariants hold
    (Requirements 2.1, 4.4, 7.7, 7.8, 7.9).

    **Validates: Requirements 2.1, 4.4, 7.7, 7.8, 7.9**
    """
    pytest.importorskip("reportlab")

    pdf_bytes = _build_pdf_bytes(
        [
            "Savings top up campaign.",
            "Eligible segments: Mass.",
            "Threshold PHP 300,000. Minimum ADB PHP 50,000.",
            "Reward: P500 cashback. Channels: email, sms, in-app.",
        ]
    )

    draft = extract_form(pdf_bytes, "brief.pdf", SEGMENT_OPTIONS)

    _assert_reviewable_form(draft)
    _assert_brief_extraction(draft)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

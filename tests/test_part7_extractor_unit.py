"""Unit tests for the campaign extractor (src/ai/extractor.py, ai/mocks.py).

Fake Bedrock client and explicit env only; no network, no real ``.env``.

Covers: DOCX/PDF reading and the type/size/unreadable/empty errors, the
30,000-character payload cap, JSON validation (valid accepted, missing /
wrong-type / invalid rejected), the Mock extraction rules, and the 60 s budget
through an injectable clock.

Validates: Requirements 2.3, 2.4, 2.5, 2.10, 10.4, 10.5
"""

from __future__ import annotations

import io
import json

import pytest

from ai import extractor, mocks
from ai.extractor import (
    CAMPAIGN_FIELDS,
    FOUND,
    MAX_PROMPT_CHARS,
    MAX_UPLOAD_BYTES,
    NEEDS_INPUT,
    UploadError,
    extract_campaign,
    extract_text,
    validate_fields,
)

FAKE_ENV = {
    "AWS_ACCESS_KEY_ID": "AKIATESTKEYID",
    "AWS_SECRET_ACCESS_KEY": "test-secret",
    "AWS_REGION": "us-east-1",
    "BEDROCK_MODEL_ID": "fake.model-id-v1",
}


class FakeClient:
    """Records the Converse request and returns a canned text reply."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def _run(reply: str, text: str = "doc text", clock=None):
    client = FakeClient(reply)
    kwargs = {"clock": clock} if clock is not None else {}
    result = extract_campaign(text, client=client, env=FAKE_ENV, **kwargs)
    return result, client


# ---------------------------------------------------------------------------
# Fixtures: DOCX and a minimal hand-built PDF
# ---------------------------------------------------------------------------


def _docx_bytes(paragraphs: list[str]) -> bytes:
    import docx

    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def _pdf_bytes(line: str) -> bytes:
    """One-page PDF with a single text line (no external PDF writer needed)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({line}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------


def test_extract_text_reads_docx(tmp_path):
    path = tmp_path / "proposal.docx"
    path.write_bytes(_docx_bytes(["Objective: grow deposits", "Channel: SMS"]))
    text = extract_text(path.read_bytes(), path.name)
    assert "Objective: grow deposits" in text
    assert "Channel: SMS" in text


def test_extract_text_reads_pdf(tmp_path):
    path = tmp_path / "proposal.pdf"
    path.write_bytes(_pdf_bytes("Time Deposit promo"))
    assert "Time Deposit promo" in extract_text(path.read_bytes(), path.name)


def test_extract_text_filename_case_insensitive():
    assert "hello" in extract_text(_docx_bytes(["hello"]), "UPPER.DOCX")


@pytest.mark.parametrize("name", ["notes.txt", "sheet.xlsx", "doc.docx.exe", "", "pdf"])
def test_extract_text_wrong_type(name):
    with pytest.raises(UploadError) as exc:
        extract_text(b"data", name)
    assert exc.value.cause == "type"


def test_extract_text_oversize_rejected_before_reading():
    with pytest.raises(UploadError) as exc:
        extract_text(b"x" * (MAX_UPLOAD_BYTES + 1), "big.pdf")
    assert exc.value.cause == "size"


def test_extract_text_size_limit_is_inclusive():
    # Exactly at the limit passes the size check (then fails as unreadable).
    with pytest.raises(UploadError) as exc:
        extract_text(b"x" * MAX_UPLOAD_BYTES, "edge.docx")
    assert exc.value.cause == "unreadable"


@pytest.mark.parametrize("name", ["bad.pdf", "bad.docx"])
def test_extract_text_unreadable(name):
    with pytest.raises(UploadError) as exc:
        extract_text(b"this is not a real document", name)
    assert exc.value.cause == "unreadable"


def test_extract_text_empty_docx():
    with pytest.raises(UploadError) as exc:
        extract_text(_docx_bytes(["", "   "]), "blank.docx")
    assert exc.value.cause == "empty"


# ---------------------------------------------------------------------------
# Payload truncation (Requirement 2.4)
# ---------------------------------------------------------------------------


def _sent_document(client: FakeClient) -> str:
    content = client.calls[0]["messages"][0]["content"][0]["text"]
    return json.loads(content)["document_text"]


def test_payload_truncated_to_30000_chars():
    long_text = "a" * (MAX_PROMPT_CHARS + 5_000)
    _, client = _run("{}", text=long_text)
    assert MAX_PROMPT_CHARS == 30_000
    assert _sent_document(client) == "a" * 30_000


def test_short_payload_sent_whole():
    _, client = _run("{}", text="short doc")
    assert _sent_document(client) == "short doc"


def test_result_keeps_full_document_text():
    long_text = "b" * 31_000
    result, _ = _run("{}", text=long_text)
    assert result.document_text == long_text


# ---------------------------------------------------------------------------
# JSON validation (Requirement 2.5)
# ---------------------------------------------------------------------------

VALID = {
    "fields": {
        "product_type": "Savings",
        "mechanic": "TOP_UP",
        "threshold_type": "Top-Up Amount",
        "threshold_value": 100000,
        "reward": "1% bonus interest",
        "eligible_segments": ["Mass", "mid-market"],
        "min_adb": 50000,
        "channels": ["sms", "Email"],
    },
    "context": {"objective": " Grow deposits ", "timeline": "Q3"},
}


def test_valid_json_accepted_and_tagged():
    result, _ = _run(json.dumps(VALID))
    assert result.mode == "Bedrock"
    assert result.fields == {
        "product_type": "Savings",
        "mechanic": "TOP_UP",
        "threshold_type": "Top-Up Amount",
        "threshold_value": 100000,
        "reward": "1% bonus interest",
        "eligible_segments": ["Mass", "Mid-Market"],
        "min_adb": 50000,
        "channels": ["Email", "SMS"],
    }
    assert all(result.tags[name] == FOUND for name in CAMPAIGN_FIELDS)
    assert result.context["objective"] == "Grow deposits"
    assert result.context["timeline"] == "Q3"
    assert result.context["key_messages"] == ""


def test_fenced_json_accepted():
    result, _ = _run("```json\n" + json.dumps(VALID) + "\n```")
    assert result.mode == "Bedrock"
    assert result.fields["product_type"] == "Savings"


def test_missing_fields_tagged_needs_input():
    result, _ = _run(json.dumps({"fields": {"product_type": "Savings"}}))
    assert result.tags["product_type"] == FOUND
    assert all(result.tags[n] == NEEDS_INPUT for n in CAMPAIGN_FIELDS if n != "product_type")
    assert set(result.fields) == {"product_type"}


@pytest.mark.parametrize(
    "raw",
    [
        {"product_type": 5},
        {"product_type": "Crypto"},
        {"mechanic": ["TOP_UP"]},
        {"mechanic": "top_up"},
        {"threshold_type": "Mystery"},
        {"threshold_value": 100000},  # value without a type
        {"threshold_type": "Top-Up Amount", "threshold_value": "100000"},
        {"threshold_type": "Top-Up Amount", "threshold_value": True},
        {"threshold_type": "Top-Up Amount", "threshold_value": 10},  # below range
        {"threshold_type": "Balance Increase", "threshold_value": 500},  # above range
        {"threshold_type": "Top-Up Amount", "threshold_value": float("nan")},
        {"reward": 12},
        {"reward": "   "},
        {"reward": "x" * 201},
        {"eligible_segments": "Mass"},
        {"eligible_segments": ["Platinum"]},
        {"min_adb": "50000"},
        {"min_adb": -1},
        {"min_adb": True},
        {"channels": "SMS"},
        {"channels": ["Fax"]},
    ],
)
def test_invalid_field_values_dropped(raw):
    out = validate_fields(raw)
    for key in raw:
        if key == "threshold_type":
            continue
        assert key not in out, f"{key} should have been dropped from {out}"


def test_invalid_threshold_value_keeps_valid_type_only():
    out = validate_fields({"threshold_type": "Top-Up Amount", "threshold_value": 10})
    assert out == {"threshold_type": "Top-Up Amount"}


def test_validate_fields_non_mapping_gives_empty():
    assert validate_fields(["not", "a", "mapping"]) == {}  # type: ignore[arg-type]


def test_validate_fields_does_not_repair_values():
    out = validate_fields({"product_type": "savings", "reward": "  ok  "})
    assert "product_type" not in out  # case is not repaired
    assert out["reward"] == "ok"  # only whitespace is trimmed


def test_flat_object_tolerated():
    result, _ = _run(json.dumps(VALID["fields"]))
    assert result.mode == "Bedrock"
    assert result.fields["product_type"] == "Savings"


def test_non_object_json_falls_back_to_demo():
    result, _ = _run("[1, 2, 3]")
    assert result.mode == "Demo"


def test_non_json_reply_falls_back_to_mock():
    result, _ = _run("Sure! Here is the plan.", text="Time deposit promo via SMS")
    assert result.mode == "Demo"
    assert result.fields["product_type"] == "Time Deposit"
    assert result.fields["channels"] == ["SMS"]


def test_no_credentials_uses_mock_without_calling_client():
    client = FakeClient("{}")
    result = extract_campaign("credit card promo", client=client, env={})
    assert result.mode == "Demo"
    assert client.calls == []
    assert result.fields["product_type"] == "Credit Card"


def test_extract_campaign_never_raises_on_non_string():
    result = extract_campaign(None, client=FakeClient("{}"), env=FAKE_ENV)  # type: ignore[arg-type]
    assert result.document_text == ""


# ---------------------------------------------------------------------------
# Mock rules (Requirements 10.4, 10.5)
# ---------------------------------------------------------------------------

DOC = """Objective: Grow time deposit balances
Target audience: Mass and Affluent-Gold clients
Offer details: Top up and earn
Timeline: July to September
Key messages: Save more, earn more
Reward: 1.5% bonus interest
Top-up of PHP 100,000 required. Minimum ADB of PHP 50k.
Send by email, SMS and in-app.
"""


def test_mock_extract_full_document():
    out = mocks.mock_extract(DOC)
    fields, context = out["fields"], out["context"]
    assert fields["product_type"] == "Time Deposit"
    assert fields["mechanic"] == "TOP_UP"
    assert fields["threshold_type"] == "Top-Up Amount"
    assert fields["threshold_value"] == 100000
    assert fields["reward"] == "1.5% bonus interest"
    assert fields["eligible_segments"] == ["Affluent-Gold", "Mass"]
    assert fields["min_adb"] == 50000
    assert fields["channels"] == ["In-app", "Email", "SMS"]
    assert context == {
        "objective": "Grow time deposit balances",
        "target_audience": "Mass and Affluent-Gold clients",
        "offer_details": "Top up and earn",
        "timeline": "July to September",
        "key_messages": "Save more, earn more",
    }


def test_mock_extract_is_deterministic():
    assert mocks.mock_extract(DOC) == mocks.mock_extract(DOC)


def test_mock_extract_empty_text_has_no_fields_and_five_empty_context_keys():
    out = mocks.mock_extract("")
    assert out["fields"] == {}
    assert out["context"] == {k: "" for k in mocks.CONTEXT_KEYS}


def test_mock_extract_percent_increase_threshold():
    out = mocks.mock_extract("Customers must increase their balance by 20%.")
    assert out["fields"]["threshold_type"] == "Balance Increase"
    assert out["fields"]["threshold_value"] == 20


def test_mock_extract_amount_suffixes():
    out = mocks.mock_extract("Top-up of P1.5M needed.")
    assert out["fields"]["threshold_value"] == 1_500_000


def test_mock_extract_channels_use_exact_labels():
    out = mocks.mock_extract("Use the mobile app and text message.")
    assert out["fields"]["channels"] == ["In-app", "SMS"]


def test_mock_extract_context_first_label_wins():
    out = mocks.mock_extract("Goal: first\nObjective: second")
    assert out["context"]["objective"] == "first"


def test_mock_extract_context_on_one_line():
    """Labeled context sharing one line must not be swallowed by the first label."""
    out = mocks.mock_extract("Objective: grow deposits. Timeline: July to September")
    assert out["context"]["objective"] == "grow deposits."
    assert out["context"]["timeline"] == "July to September"


def test_mock_result_is_validated_and_tagged():
    result = extractor._mock_result(DOC)
    assert result.mode == "Demo"
    assert result.tags["threshold_value"] == FOUND
    assert result.tags["mechanic"] == FOUND
    assert result.document_text == DOC


# ---------------------------------------------------------------------------
# 60 s budget via injectable clock (Requirement 2.10)
# ---------------------------------------------------------------------------


class FakeClock:
    """Returns the queued readings in order, then repeats the last."""

    def __init__(self, *readings: float) -> None:
        self.readings = list(readings)

    def __call__(self) -> float:
        return self.readings.pop(0) if len(self.readings) > 1 else self.readings[0]


def test_over_budget_falls_back_to_mock_even_with_valid_reply():
    result, client = _run(
        json.dumps(VALID), text="Savings promo via SMS", clock=FakeClock(0.0, 60.5)
    )
    assert len(client.calls) == 1
    assert result.mode == "Demo"
    assert result.fields["channels"] == ["SMS"]  # from the Mock, not from VALID


def test_exactly_at_budget_still_uses_bedrock():
    result, _ = _run(json.dumps(VALID), clock=FakeClock(0.0, 60.0))
    assert result.mode == "Bedrock"


def test_under_budget_uses_bedrock():
    result, _ = _run(json.dumps(VALID), clock=FakeClock(100.0, 110.0))
    assert result.mode == "Bedrock"

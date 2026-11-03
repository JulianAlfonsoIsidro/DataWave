"""Property/doc-text tests for Part 6 local document text extraction routing.

# Feature: part6-assistant, Property 9: Local extraction by file type

Covers Property 9 of the part6-assistant spec: :func:`assistant.doc_text.extract_text`
routes a ``.pdf`` to pdfplumber and a ``.docx`` to python-docx (both fully local,
no network), and raises :class:`assistant.doc_text.UnsupportedFile` for any other
extension (Requirements 7.2, 7.3).

Fixtures are tiny real documents:

- a one-paragraph ``.docx`` built in-memory with python-docx, and
- a one-page ``.pdf`` built with reportlab when available (otherwise a minimal
  valid empty PDF so the routing-to-pdfplumber branch is still exercised).

Fixture bytes are kept in memory; where a file on disk is needed it is written
under a self-cleaning ``tmp_path`` so the project's real ``scratch/`` is never
polluted.
"""

from __future__ import annotations

import io

import pytest

from assistant.doc_text import UnsupportedFile, extract_text

# Text we embed in the DOCX fixture and then expect back out of extract_text.
KNOWN_DOCX_TEXT = "Ready Toppers promo brief with a known paragraph."

# Text we embed in the reportlab PDF fixture (when reportlab is installed).
KNOWN_PDF_TEXT = "Untapped Wealth promo threshold 300000 pesos."

# Extensions that are NOT supported and must raise UnsupportedFile (Req 7.2).
UNSUPPORTED_FILENAMES = [
    "brief.txt",
    "brief.csv",
    "brief.md",
    "brief.pdf.exe",
    "brief",  # no extension at all
    "BRIEF.DOC",  # legacy .doc is not .docx
]


def _build_docx_bytes(paragraph_text: str) -> bytes:
    """Build a one-paragraph .docx in memory and return its bytes."""
    from docx import Document

    document = Document()
    document.add_paragraph(paragraph_text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _build_pdf_bytes_reportlab(text: str) -> bytes:
    """Build a one-page PDF with known text using reportlab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=letter)
    pdf_canvas.drawString(72, 720, text)
    pdf_canvas.showPage()
    pdf_canvas.save()
    return buffer.getvalue()


# A minimal, valid one-page PDF (no extractable text). Used only to prove the
# ``.pdf`` extension routes to pdfplumber and returns a ``str`` without raising
# UnsupportedFile, when reportlab is not installed to generate real text.
_MINIMAL_EMPTY_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
    b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
    b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>endobj\n"
    b"xref\n"
    b"0 4\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"trailer<< /Size 4 /Root 1 0 R >>\n"
    b"startxref\n"
    b"190\n"
    b"%%EOF\n"
)


def test_docx_routes_to_python_docx_and_returns_paragraph_text():
    """A ``.docx`` is read with python-docx and its paragraph text comes back.

    **Validates: Requirements 7.2, 7.3**
    """
    docx_bytes = _build_docx_bytes(KNOWN_DOCX_TEXT)

    result = extract_text(docx_bytes, "brief.docx")

    assert isinstance(result, str)
    assert KNOWN_DOCX_TEXT in result


def test_docx_routing_is_case_insensitive_on_extension():
    """An uppercase ``.DOCX`` extension still routes to python-docx (Req 7.2)."""
    docx_bytes = _build_docx_bytes(KNOWN_DOCX_TEXT)

    result = extract_text(docx_bytes, "BRIEF.DOCX")

    assert KNOWN_DOCX_TEXT in result


def test_pdf_with_reportlab_returns_known_text():
    """A real one-page PDF routes to pdfplumber and its text comes back.

    Skipped when reportlab is not installed to generate a text-bearing PDF;
    the routing-only guarantee is still covered by
    :func:`test_pdf_routes_to_pdfplumber_without_unsupported`.

    **Validates: Requirements 7.2, 7.3**
    """
    pytest.importorskip("reportlab")

    pdf_bytes = _build_pdf_bytes_reportlab(KNOWN_PDF_TEXT)

    result = extract_text(pdf_bytes, "brief.pdf")

    assert isinstance(result, str)
    # reportlab lays the string out intact on the page; pdfplumber recovers it.
    assert KNOWN_PDF_TEXT in result


def test_pdf_routes_to_pdfplumber_without_unsupported():
    """A ``.pdf`` routes to pdfplumber and yields a ``str`` without raising.

    A minimal valid (text-free) PDF proves the ``.pdf`` branch is handled by
    pdfplumber rather than rejected, independent of reportlab.

    **Validates: Requirements 7.2, 7.3**
    """
    result = extract_text(_MINIMAL_EMPTY_PDF, "brief.pdf")

    assert isinstance(result, str)


@pytest.mark.parametrize("filename", UNSUPPORTED_FILENAMES)
def test_unsupported_extension_raises(filename):
    """Any non-.pdf/.docx file raises UnsupportedFile (Req 7.2).

    **Validates: Requirements 7.2**
    """
    with pytest.raises(UnsupportedFile):
        extract_text(b"arbitrary bytes that are never parsed", filename)


def test_routing_calls_correct_library_and_no_network(monkeypatch):
    """Each extension dispatches to its own local library and makes no network call.

    ``pdfplumber.open`` is wrapped to record that a ``.pdf`` goes through
    pdfplumber and ``docx.Document`` to record that a ``.docx`` goes through
    python-docx. ``socket.socket`` is replaced with a guard that fails the test
    if extraction tries to open any network connection, enforcing the
    fully-local guarantee (Req 7.3).

    **Validates: Requirements 7.2, 7.3**
    """
    import socket

    import docx
    import pdfplumber

    calls: list[str] = []

    real_pdfplumber_open = pdfplumber.open

    def recording_open(*args, **kwargs):
        calls.append("pdfplumber.open")
        return real_pdfplumber_open(*args, **kwargs)

    real_document = docx.Document

    def recording_document(*args, **kwargs):
        calls.append("docx.Document")
        return real_document(*args, **kwargs)

    # Patch at the source modules so the lazy imports inside doc_text pick them up.
    monkeypatch.setattr(pdfplumber, "open", recording_open)
    monkeypatch.setattr(docx, "Document", recording_document)

    def no_network(*args, **kwargs):  # pragma: no cover - only runs on failure
        raise AssertionError("extraction attempted a network connection")

    monkeypatch.setattr(socket, "socket", no_network)

    docx_bytes = _build_docx_bytes(KNOWN_DOCX_TEXT)

    pdf_text = extract_text(_MINIMAL_EMPTY_PDF, "brief.pdf")
    docx_text = extract_text(docx_bytes, "brief.docx")

    assert isinstance(pdf_text, str)
    assert KNOWN_DOCX_TEXT in docx_text
    assert "pdfplumber.open" in calls
    assert "docx.Document" in calls

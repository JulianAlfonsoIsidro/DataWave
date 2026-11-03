"""Local document text extraction (pdfplumber for PDF, python-docx for DOCX)."""

from __future__ import annotations

import io
import os


class UnsupportedFile(Exception):
    """Raised when a Campaign_File has an extension other than .pdf or .docx."""


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Return plain text from a Campaign_File. A `.pdf` is read with pdfplumber
    (page text joined with newlines); a `.docx` with python-docx (paragraph text
    joined). Extraction is fully local (Requirement 7.3). Raises UnsupportedFile
    for any other extension/content type (Requirement 7.2)."""
    extension = os.path.splitext(filename)[1].lower()

    if extension == ".pdf":
        import pdfplumber

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages]
        return "\n".join(pages)

    if extension == ".docx":
        from docx import Document

        document = Document(io.BytesIO(file_bytes))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    raise UnsupportedFile(
        f"Unsupported file type '{extension or filename}'. "
        "Only .pdf and .docx campaign briefs are supported."
    )

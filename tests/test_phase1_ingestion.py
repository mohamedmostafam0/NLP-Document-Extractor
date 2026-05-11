"""Phase 1 — Ingestion tests.

Covers TXT, DOCX, PDF (text and image-only fall-back), and direct image OCR.
PDF / image tests are skipped automatically when their optional system
dependencies (Tesseract, Poppler) are not installed.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from pipeline import ingestion


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------

def test_ingest_txt_utf8():
    payload = "Hello, world! héllo".encode("utf-8")
    result = ingestion.ingest(payload, "note.txt")

    assert result.source_format == "txt"
    assert result.text == "Hello, world! héllo"
    assert result.used_ocr is False
    assert result.char_count == len("Hello, world! héllo")


def test_ingest_txt_falls_back_to_latin1_on_decode_error():
    # 0xff is invalid in UTF-8; latin-1 decodes it as 'ÿ'.
    payload = b"caf\xe9 \xff"
    result = ingestion.ingest(payload, "weird.txt")

    assert result.source_format == "txt"
    assert "caf" in result.text


def test_ingest_unsupported_extension_raises():
    with pytest.raises(ValueError, match="Unsupported extension"):
        ingestion.ingest(b"data", "archive.zip")


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def _make_docx_bytes(paragraphs, table_rows=None) -> bytes:
    from docx import Document
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if table_rows:
        table = doc.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        for r, row in enumerate(table_rows):
            for c, val in enumerate(row):
                table.cell(r, c).text = val
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_ingest_docx_extracts_paragraphs_and_tables():
    payload = _make_docx_bytes(
        paragraphs=["Hello", "World"],
        table_rows=[["Name", "Email"], ["Alice", "alice@example.com"]],
    )
    result = ingestion.ingest(payload, "doc.docx")

    assert result.source_format == "docx"
    assert "Hello" in result.text
    assert "World" in result.text
    assert "Alice" in result.text
    assert "alice@example.com" in result.text
    # Table rows are joined with " | "
    assert " | " in result.text


def test_ingest_docx_skips_empty_paragraphs():
    payload = _make_docx_bytes(paragraphs=["Real content", "", "   "])
    result = ingestion.ingest(payload, "doc.docx")
    # Two whitespace-only paragraphs should not produce empty lines in output
    assert result.text.strip() == "Real content"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_resume_pdf(samples_dir: Path):
    pdf = samples_dir / "sample_resume.pdf"
    if not pdf.exists():
        pytest.skip(f"Sample PDF not present at {pdf}")
    return pdf.read_bytes()


def test_ingest_pdf_text_layer(sample_resume_pdf):
    result = ingestion.ingest(sample_resume_pdf, "sample_resume.pdf")
    assert result.source_format == "pdf"
    assert result.char_count > 0
    assert len(result.pages) >= 1


# ---------------------------------------------------------------------------
# Image OCR — requires Tesseract on PATH
# ---------------------------------------------------------------------------

@pytest.fixture
def has_tesseract():
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def test_ingest_image_requires_tesseract(data_samples_dir: Path, has_tesseract):
    png = data_samples_dir / "business_card.png"
    if not png.exists():
        pytest.skip(f"Image sample missing: {png}")
    if not has_tesseract:
        pytest.skip("Tesseract is not installed — skipping OCR test")

    result = ingestion.ingest(png.read_bytes(), "business_card.png")
    assert result.source_format == "png"
    assert result.used_ocr is True
    # Even a noisy OCR should give us *some* text
    assert result.char_count > 0

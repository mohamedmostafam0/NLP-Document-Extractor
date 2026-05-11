"""End-to-end orchestrator tests.

Runs the full 5-phase pipeline on hand-crafted text inputs (wrapped as .txt
file bytes so we skip OCR). These tests load the spaCy NER model — slow on
first run, fast afterwards.
"""

from __future__ import annotations

import pytest

from pipeline import orchestrator


pytestmark = pytest.mark.slow


def _to_txt_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def test_pipeline_business_card_completes(business_card_text):
    result = orchestrator.run(
        _to_txt_bytes(business_card_text),
        "card.txt",
        doc_type="business_card",
    )

    assert result.status in {"completed", "needs_review"}
    assert "richard@piedpiper.com" == result.extracted_data.get("email")
    # Name was either found by NER or left for review — either is acceptable here
    if result.extracted_data.get("name"):
        assert "Richard" in result.extracted_data["name"]


def test_pipeline_resume_completes(resume_text):
    result = orchestrator.run(
        _to_txt_bytes(resume_text),
        "resume.txt",
        doc_type="resume",
    )

    # Email is reliable
    assert result.extracted_data.get("email") == "jane.smith@example.com"
    # Name should be picked up by the first-line heuristic
    assert result.extracted_data.get("name") == "Jane Smith"
    # Skills section should have populated
    assert "Python" in (result.extracted_data.get("skills") or [])
    # Language detected
    assert result.language == "en"


def test_pipeline_medical_report_completes(medical_report_text):
    result = orchestrator.run(
        _to_txt_bytes(medical_report_text),
        "report.txt",
        doc_type="medical_report",
    )

    assert result.extracted_data.get("patient_name") == "Sarah Jenkins"
    assert result.extracted_data.get("visit_date") == "2025-10-12"
    assert result.extracted_data.get("date_of_birth") == "1982-05-14"
    assert "Dr." in (result.extracted_data.get("provider") or "")


def test_pipeline_empty_input_fails_gracefully():
    result = orchestrator.run(b"   \n  ", "blank.txt", doc_type="resume")
    assert result.status == "failed"
    assert result.issues
    assert "No text" in result.issues[0]


def test_pipeline_entities_get_normalized(business_card_text):
    result = orchestrator.run(
        _to_txt_bytes(business_card_text),
        "card.txt",
        doc_type="business_card",
    )
    # All EMAIL entities should be lower-cased in normalized_value
    for ent in result.entities:
        if ent.type == "EMAIL" and ent.normalized_value:
            assert ent.normalized_value == ent.normalized_value.lower()

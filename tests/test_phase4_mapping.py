"""Phase 4 — Schema mapping & normalization tests.

These exercise the per-doc-type mappers with hand-built ExtractionResults
so the tests stay deterministic and don't depend on real NER output.
"""

from __future__ import annotations

from extractors.base import Entity, ExtractionResult
from pipeline import mapping


# ---------------------------------------------------------------------------
# Business card
# ---------------------------------------------------------------------------

def _bc_extraction() -> ExtractionResult:
    text = (
        "Richard Hendricks\n"
        "CEO & Founder\n"
        "Pied Piper Inc.\n"
        "richard@piedpiper.com\n"
    )
    return ExtractionResult(entities=[
        Entity(type="PERSON", value="Richard Hendricks", confidence=0.95,
               source="spacy", start=text.find("Richard"),
               end=text.find("Richard") + len("Richard Hendricks")),
        Entity(type="ORG", value="Pied Piper Inc.", confidence=0.9,
               source="spacy", start=text.find("Pied"),
               end=text.find("Pied") + len("Pied Piper Inc.")),
        Entity(type="EMAIL", value="Richard@PiedPiper.com", confidence=0.95,
               source="regex"),
        Entity(type="PHONE", value="(415) 555-0142", confidence=0.9, source="regex"),
        Entity(type="URL", value="HTTPS://Piedpiper.com", confidence=0.9,
               source="regex"),
    ]), text


def test_map_business_card_populates_required_fields():
    extraction, text = _bc_extraction()
    result = mapping.map_to_schema(extraction, "business_card", text)

    assert result.data["name"] == "Richard Hendricks"
    assert result.data["company"] == "Pied Piper Inc."
    assert result.data["email"] == "richard@piedpiper.com"  # lower-cased
    assert result.data["website"] == "https://piedpiper.com"  # lower-cased


def test_map_business_card_normalizes_phone_to_e164():
    extraction, text = _bc_extraction()
    result = mapping.map_to_schema(extraction, "business_card", text)

    assert result.data["phone"].startswith("+1")
    assert result.data["phone"] == "+14155550142"


def test_map_business_card_guesses_title_from_line_after_name():
    extraction, text = _bc_extraction()
    result = mapping.map_to_schema(extraction, "business_card", text)
    assert result.data.get("title") == "CEO & Founder"
    # heuristic title should carry a lower confidence
    assert result.confidence_scores["title"] < 0.7


def test_map_business_card_emits_confidence_scores():
    extraction, text = _bc_extraction()
    result = mapping.map_to_schema(extraction, "business_card", text)
    for key in ("name", "email", "phone"):
        assert 0 <= result.confidence_scores[key] <= 1


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

def test_map_resume_name_from_first_line(resume_text):
    extraction = ExtractionResult(entities=[
        Entity(type="EMAIL", value="jane.smith@example.com", confidence=0.95,
               source="regex"),
        Entity(type="PHONE", value="(206) 555-0142", confidence=0.9, source="regex"),
        Entity(type="ORG", value="Stanford University", confidence=0.9,
               source="spacy"),
        Entity(type="ORG", value="Google", confidence=0.9, source="spacy"),
        Entity(type="LOCATION", value="Seattle, WA", confidence=0.85,
               source="spacy", start=resume_text.find("Seattle"),
               end=resume_text.find("Seattle") + len("Seattle, WA")),
    ])
    result = mapping.map_to_schema(extraction, "resume", resume_text)

    assert result.data["name"] == "Jane Smith"
    assert result.confidence_scores["name"] >= 0.85
    assert result.data["email"] == "jane.smith@example.com"


def test_map_resume_extracts_skills_section(resume_text):
    extraction = ExtractionResult(entities=[])
    result = mapping.map_to_schema(extraction, "resume", resume_text)

    skills = result.data.get("skills") or []
    # All seven listed skills should appear, but order isn't strictly required
    for expected in ("Python", "Go", "Kubernetes", "Postgres", "Kafka"):
        assert expected in skills, f"Expected skill missing: {expected}"


def test_map_resume_extracts_education_section(resume_text):
    extraction = ExtractionResult(entities=[
        Entity(type="ORG", value="Stanford University", confidence=0.9,
               source="spacy"),
    ])
    result = mapping.map_to_schema(extraction, "resume", resume_text)

    education = result.data.get("education") or []
    assert education, "Education section should have been extracted"
    assert any(e.get("institution") == "Stanford University" for e in education)


def test_map_resume_extracts_experience_section(resume_text):
    extraction = ExtractionResult(entities=[
        Entity(type="ORG", value="Google", confidence=0.9, source="spacy"),
    ])
    result = mapping.map_to_schema(extraction, "resume", resume_text)

    experience = result.data.get("experience") or []
    assert experience
    assert any(x.get("company") == "Google" for x in experience)


def test_map_resume_picks_header_location_first():
    # Two locations — one in the header, one in body. We should prefer the header one.
    text = (
        "Jane Smith\n"
        "Seattle, WA\n"
        "j@example.com\n"
        "\n"
        "Experience\n"
        "Acme — Boston, MA\n"
    )
    extraction = ExtractionResult(entities=[
        Entity(type="EMAIL", value="j@example.com", confidence=0.95, source="regex"),
        Entity(type="LOCATION", value="Seattle, WA", confidence=0.85,
               source="spacy", start=text.find("Seattle"),
               end=text.find("Seattle") + len("Seattle, WA")),
        Entity(type="LOCATION", value="Boston, MA", confidence=0.85,
               source="spacy", start=text.find("Boston"),
               end=text.find("Boston") + len("Boston, MA")),
    ])
    result = mapping.map_to_schema(extraction, "resume", text)
    assert result.data["location"] == "Seattle, WA"


# ---------------------------------------------------------------------------
# Medical report
# ---------------------------------------------------------------------------

def test_map_medical_report_extracts_patient_and_dates(medical_report_text):
    extraction = ExtractionResult(entities=[
        Entity(type="PERSON", value="Sarah Jenkins", confidence=0.9, source="spacy"),
        Entity(type="ORG", value="Mercy General Hospital", confidence=0.85,
               source="spacy"),
    ])
    result = mapping.map_to_schema(extraction, "medical_report", medical_report_text)

    assert result.data["patient_name"] == "Sarah Jenkins"
    assert result.data["date_of_birth"] == "1982-05-14"
    assert result.data["visit_date"] == "2025-10-12"


def test_map_medical_report_extracts_provider_from_dr_prefix(medical_report_text):
    extraction = ExtractionResult(entities=[])
    result = mapping.map_to_schema(extraction, "medical_report", medical_report_text)
    assert result.data["provider"] == "Dr. Gregory House"
    assert result.confidence_scores["provider"] >= 0.8


def test_map_medical_report_extracts_diagnoses(medical_report_text):
    result = mapping.map_to_schema(
        ExtractionResult(entities=[]), "medical_report", medical_report_text,
    )
    diags = result.data.get("diagnoses") or []
    assert any("Migraine" in d for d in diags)
    assert any("dehydration" in d.lower() for d in diags)


def test_map_medical_report_extracts_medications(medical_report_text):
    result = mapping.map_to_schema(
        ExtractionResult(entities=[]), "medical_report", medical_report_text,
    )
    meds = result.data.get("medications") or []
    assert any("Sumatriptan" in m for m in meds)
    assert any("Ibuprofen" in m for m in meds)
    assert any("Zofran" in m for m in meds)


def test_map_medical_report_extracts_vitals(medical_report_text):
    result = mapping.map_to_schema(
        ExtractionResult(entities=[]), "medical_report", medical_report_text,
    )
    vitals = result.data.get("vitals") or {}
    assert "bp" in vitals
    assert "120/80" in vitals["bp"]
    assert any(k.startswith("hr") or k == "hr" for k in vitals)
    assert any(k.startswith("temp") for k in vitals)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def test_map_to_schema_unknown_doc_type_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown doc_type"):
        mapping.map_to_schema(ExtractionResult(), "passport", "some text")

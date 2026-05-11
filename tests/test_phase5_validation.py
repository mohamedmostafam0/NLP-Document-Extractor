"""Phase 5 — Validation & QC tests."""

from __future__ import annotations

from datetime import date, timedelta

from pipeline import validation


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_validate_business_card_complete_record_is_valid():
    data = {
        "name": "Richard Hendricks",
        "title": "CEO",
        "company": "Pied Piper Inc.",
        "email": "richard@piedpiper.com",
        "phone": "+14155550142",
        "website": "https://piedpiper.com",
    }
    confs = {k: 0.95 for k in data}
    result = validation.validate(data, confs, "business_card")

    assert result.is_valid is True
    assert result.needs_review is False
    assert result.missing_required == []
    assert result.issues == []


def test_validate_resume_complete_record_is_valid():
    data = {
        "name": "Jane Smith",
        "email": "jane@example.com",
        "phone": "+12065550142",
        "skills": ["Python", "Go"],
    }
    confs = {k: 0.9 for k in data}
    result = validation.validate(data, confs, "resume")

    assert result.is_valid is True
    assert result.needs_review is False


def test_validate_medical_report_complete_record_is_valid():
    data = {
        "patient_name": "Sarah Jenkins",
        "visit_date": "2025-10-12",
        "date_of_birth": "1982-05-14",
        "provider": "Dr. Gregory House",
    }
    confs = {k: 0.9 for k in data}
    result = validation.validate(data, confs, "medical_report")

    assert result.is_valid is True
    assert result.needs_review is False


# ---------------------------------------------------------------------------
# Missing required fields → needs_review
# ---------------------------------------------------------------------------

def test_validate_business_card_missing_email_needs_review():
    data = {"name": "Richard Hendricks"}
    result = validation.validate(data, {"name": 0.9}, "business_card")

    assert result.needs_review is True
    assert "email" in result.missing_required
    assert result.is_valid is False


def test_validate_medical_report_missing_visit_date_needs_review():
    data = {"patient_name": "John Smith"}
    result = validation.validate(data, {"patient_name": 0.9}, "medical_report")

    assert result.needs_review is True
    assert "visit_date" in result.missing_required


# ---------------------------------------------------------------------------
# Low confidence on required fields
# ---------------------------------------------------------------------------

def test_validate_low_confidence_required_field_needs_review():
    data = {"name": "John", "email": "j@example.com"}
    confs = {"name": 0.3, "email": 0.95}  # low confidence on name
    result = validation.validate(data, confs, "business_card")

    assert result.needs_review is True
    assert any("Low confidence" in i for i in result.issues)


# ---------------------------------------------------------------------------
# Outlier checks
# ---------------------------------------------------------------------------

def test_validate_flags_future_dob():
    future = (date.today() + timedelta(days=365)).isoformat()
    data = {
        "patient_name": "Test Patient",
        "visit_date": "2025-10-12",
        "date_of_birth": future,
    }
    result = validation.validate(data, {"patient_name": 0.9, "visit_date": 0.9},
                                 "medical_report")
    assert any("future" in i for i in result.issues)


def test_validate_flags_implausibly_old_dob():
    data = {
        "patient_name": "Methuselah",
        "visit_date": "2025-10-12",
        "date_of_birth": "1850-01-01",
    }
    result = validation.validate(data, {"patient_name": 0.9, "visit_date": 0.9},
                                 "medical_report")
    assert any("implausibly old" in i for i in result.issues)


def test_validate_flags_visit_before_dob():
    data = {
        "patient_name": "Time Traveler",
        "date_of_birth": "2000-01-01",
        "visit_date": "1995-01-01",
    }
    result = validation.validate(data, {"patient_name": 0.9, "visit_date": 0.9},
                                 "medical_report")
    assert any("before" in i for i in result.issues)


def test_validate_flags_bad_email():
    data = {"name": "Test", "email": "not-an-email"}
    result = validation.validate(data, {"name": 0.9, "email": 0.9}, "business_card")
    assert any("email" in i for i in result.issues)


def test_validate_flags_invalid_phone():
    data = {"name": "Test", "email": "t@example.com", "phone": "12345"}
    result = validation.validate(data, {"name": 0.9, "email": 0.9}, "business_card")
    assert any("phone" in i for i in result.issues)


def test_validate_flags_overlong_name():
    data = {
        "name": "X" * 200,
        "email": "x@example.com",
    }
    result = validation.validate(data, {"name": 0.9, "email": 0.9}, "business_card")
    assert any("suspiciously long" in i for i in result.issues)


def test_validate_flags_too_many_skills():
    data = {
        "name": "Jane",
        "email": "j@example.com",
        "skills": [f"skill{i}" for i in range(50)],  # well over the limit of 30
    }
    result = validation.validate(data, {"name": 0.9, "email": 0.9}, "resume")
    assert any("skills" in i and "unusually many" in i for i in result.issues)


# ---------------------------------------------------------------------------
# Unknown doc type
# ---------------------------------------------------------------------------

def test_validate_unknown_doc_type_marks_review():
    result = validation.validate({}, {}, "passport")
    assert result.is_valid is False
    assert result.needs_review is True
    assert any("Unknown doc_type" in i for i in result.issues)

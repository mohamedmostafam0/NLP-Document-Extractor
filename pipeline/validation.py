"""Phase 5 — Validation & QC.

Run typed pydantic validation on the mapped record, enforce required fields
per doc type, flag outliers (e.g. impossible dates), and decide whether the
document should be auto-accepted or routed to the human review queue.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Type

import phonenumbers
from pydantic import BaseModel, ValidationError

from models.schemas import BusinessCardData, MedicalReportData, ResumeData

logger = logging.getLogger("docxtract.validation")

# Required fields per doc type — missing any of these → needs_review.
_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "business_card": ["name", "email"],
    "resume": ["name", "email"],
    "medical_report": ["patient_name", "visit_date"],
}

# Confidence floor — any required field below this triggers review.
_LOW_CONF_THRESHOLD = 0.5

_MODELS: Dict[str, Type[BaseModel]] = {
    "business_card": BusinessCardData,
    "resume": ResumeData,
    "medical_report": MedicalReportData,
}


@dataclass
class ValidationResult:
    """Outcome of validating one extracted record."""

    is_valid: bool
    needs_review: bool
    data: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)


def validate(
    data: Dict[str, Any],
    confidences: Dict[str, float],
    doc_type: str,
) -> ValidationResult:
    issues: List[str] = []
    missing: List[str] = []

    # 1. Pydantic schema validation — types, formats
    model_cls = _MODELS.get(doc_type)
    if model_cls is None:
        return ValidationResult(
            is_valid=False,
            needs_review=True,
            data=data,
            issues=[f"Unknown doc_type: {doc_type}"],
        )

    validated_data = data
    try:
        validated = model_cls.model_validate(data)
        validated_data = validated.model_dump(exclude_none=True)
    except ValidationError as exc:
        for err in exc.errors():
            field_path = ".".join(str(p) for p in err["loc"])
            issues.append(f"{field_path}: {err['msg']}")

    # 2. Required-field check
    for field_name in _REQUIRED_FIELDS.get(doc_type, []):
        if not validated_data.get(field_name):
            missing.append(field_name)

    # 3. Low-confidence check on populated required fields
    low_conf_fields = [
        f for f in _REQUIRED_FIELDS.get(doc_type, [])
        if validated_data.get(f) and confidences.get(f, 1.0) < _LOW_CONF_THRESHOLD
    ]
    if low_conf_fields:
        issues.append(
            f"Low confidence on required fields: {', '.join(low_conf_fields)}"
        )

    # 4. Outlier checks
    issues.extend(_check_dates(validated_data, doc_type))
    issues.extend(_check_phone(validated_data))
    issues.extend(_check_email(validated_data))
    issues.extend(_check_string_lengths(validated_data, doc_type))
    issues.extend(_check_collection_sizes(validated_data, doc_type))

    # 5. Decide overall status
    is_valid = not issues and not missing
    needs_review = bool(missing or low_conf_fields or issues)

    return ValidationResult(
        is_valid=is_valid,
        needs_review=needs_review,
        data=validated_data,
        issues=issues,
        missing_required=missing,
    )


# ---------------------------------------------------------------------------
# Outlier checks
# ---------------------------------------------------------------------------

def _check_dates(data: Dict[str, Any], doc_type: str) -> List[str]:
    issues: List[str] = []
    today = date.today()

    if doc_type == "medical_report":
        dob_raw = data.get("date_of_birth")
        visit_raw = data.get("visit_date")

        dob = _try_parse_iso(dob_raw)
        visit = _try_parse_iso(visit_raw)

        if dob and dob > today:
            issues.append(f"date_of_birth is in the future: {dob_raw}")
        if dob and (today.year - dob.year) > 130:
            issues.append(f"date_of_birth implausibly old: {dob_raw}")
        if visit and visit > today:
            issues.append(f"visit_date is in the future: {visit_raw}")
        if dob and visit and visit < dob:
            issues.append("visit_date is before date_of_birth")

    return issues


def _try_parse_iso(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Phone / email / string-length / collection-size sanity checks
# ---------------------------------------------------------------------------

def _check_phone(data: Dict[str, Any]) -> List[str]:
    """E.164 strings should parse and be valid."""
    issues: List[str] = []
    raw = data.get("phone")
    if not raw:
        return issues
    try:
        num = phonenumbers.parse(raw, None if raw.startswith("+") else "US")
        if not phonenumbers.is_valid_number(num):
            issues.append(f"phone is not a valid number: {raw}")
    except phonenumbers.NumberParseException:
        issues.append(f"phone could not be parsed: {raw}")
    return issues


_EMAIL_LOOSE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _check_email(data: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for key in ("email",):
        val = data.get(key)
        if val and not _EMAIL_LOOSE_RE.match(val):
            issues.append(f"{key} doesn't look like a valid email: {val}")
    return issues


# Per-doc-type max length expectations. If a string is much longer than this,
# it usually means our extractor grabbed too much (e.g. a whole paragraph).
_MAX_STRING_LENGTHS: Dict[str, Dict[str, int]] = {
    "business_card": {
        "name": 80,
        "title": 80,
        "company": 120,
        "address": 200,
    },
    "resume": {
        "name": 80,
    },
    "medical_report": {
        "patient_name": 80,
        "provider": 120,
    },
}


def _check_string_lengths(data: Dict[str, Any], doc_type: str) -> List[str]:
    issues: List[str] = []
    limits = _MAX_STRING_LENGTHS.get(doc_type, {})
    for field_name, max_len in limits.items():
        value = data.get(field_name)
        if isinstance(value, str) and len(value) > max_len:
            issues.append(
                f"{field_name} is suspiciously long ({len(value)} chars > {max_len})"
            )
    return issues


# Per-doc-type max collection sizes. If we extracted "47 skills" or "62 medications"
# that's almost certainly noise.
_MAX_COLLECTION_SIZES: Dict[str, Dict[str, int]] = {
    "resume": {
        "skills": 30,
        "education": 6,
        "experience": 8,
    },
    "medical_report": {
        "diagnoses": 12,
        "medications": 20,
    },
}


def _check_collection_sizes(data: Dict[str, Any], doc_type: str) -> List[str]:
    issues: List[str] = []
    limits = _MAX_COLLECTION_SIZES.get(doc_type, {})
    for field_name, max_size in limits.items():
        value = data.get(field_name)
        if isinstance(value, list) and len(value) > max_size:
            issues.append(
                f"{field_name} has unusually many items ({len(value)} > {max_size})"
            )
    return issues

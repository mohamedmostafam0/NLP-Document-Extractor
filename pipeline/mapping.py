"""Phase 4 — Schema mapping & normalization.

Take the messy bag of entities produced by Phase 3 and project it onto a
typed, normalized record specific to the document type.

Normalizations applied:
  - dates       → ISO 8601 (YYYY-MM-DD) via dateutil
  - phones      → E.164 via phonenumbers
  - currencies  → kept as raw string (parsing per-currency is out of scope)
  - whitespace  → collapsed
  - URLs        → leading scheme/www stripped for the canonical form

Each output field carries a confidence score in `confidence_scores`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import phonenumbers
from dateutil import parser as date_parser

from extractors.base import Entity, ExtractionResult
from utils.money import normalize_money

logger = logging.getLogger("docxtract.mapping")


@dataclass
class MappingResult:
    data: Dict[str, Any] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    entities: List[Entity] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def map_to_schema(
    extraction: ExtractionResult,
    doc_type: str,
    text: str,
) -> MappingResult:
    """Dispatch to the right mapper. `text` is the cleaned text for context."""
    if doc_type == "business_card":
        return _map_business_card(extraction, text)
    if doc_type == "resume":
        return _map_resume(extraction, text)
    if doc_type == "medical_report":
        return _map_medical_report(extraction, text)
    raise ValueError(f"Unknown doc_type for mapping: {doc_type}")


# ---------------------------------------------------------------------------
# Business card
# ---------------------------------------------------------------------------

def _map_business_card(extraction: ExtractionResult, text: str) -> MappingResult:
    data: Dict[str, Any] = {}
    confs: Dict[str, float] = {}

    if name := extraction.best_of_type("PERSON"):
        data["name"] = name.value
        confs["name"] = name.confidence

    if org := extraction.best_of_type("ORG"):
        data["company"] = org.value
        confs["company"] = org.confidence

    if email := extraction.best_of_type("EMAIL"):
        data["email"] = email.value.lower()
        confs["email"] = email.confidence

    if phone := extraction.best_of_type("PHONE"):
        data["phone"] = _normalize_phone(phone.value)
        confs["phone"] = phone.confidence

    if url := extraction.best_of_type("URL"):
        data["website"] = url.value.lower()
        confs["website"] = url.confidence

    # Title is heuristic — try the line above the email or below the name.
    if title := _guess_title(text, data.get("name"), data.get("email")):
        data["title"] = title
        confs["title"] = 0.55  # heuristic, lower confidence

    # Address — concatenate LOCATION entities (rough)
    locations = extraction.of_type("LOCATION")
    if locations:
        data["address"] = ", ".join(_dedupe_preserving_order(e.value for e in locations))
        confs["address"] = max(e.confidence for e in locations)

    return MappingResult(data=data, confidence_scores=confs, entities=extraction.entities)


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

_SKILL_SECTION_RE = re.compile(
    r"(?:^|\n)\s*(?:skills|technical skills|core competencies)\s*[:\n]+(?P<body>.+?)(?:\n\s*\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_EDUCATION_SECTION_RE = re.compile(
    r"(?:^|\n)\s*education\s*\n(?P<body>.+?)(?=\n\s*(?:technical\s+skills|skills|professional\s+experience|experience|work\s+history|employment|projects|certifications|courses|publications|interests|references|$))",
    re.IGNORECASE | re.DOTALL,
)
_EXPERIENCE_SECTION_RE = re.compile(
    r"(?:^|\n)\s*(?:professional\s+)?(?:experience|work\s*history|employment)\s*\n(?P<body>.+?)(?=\n\s*(?:education|projects|skills|technical\s+skills|certifications|courses|publications|interests|references|$))",
    re.IGNORECASE | re.DOTALL,
)


def _map_resume(extraction: ExtractionResult, text: str) -> MappingResult:
    data: Dict[str, Any] = {}
    confs: Dict[str, float] = {}

    # Strong Heuristic for Name: Resumes almost always start with the candidate's name.
    # SpaCy NER often fails on names that are ALL CAPS or have strange spacing.
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    first_line = lines[0] if lines else ""
    if first_line and len(first_line.split()) <= 5 and not re.search(r'\d|@', first_line):
        data["name"] = first_line.title()
        confs["name"] = 0.9
    else:
        # Fallback to NER
        persons = extraction.of_type("PERSON")
        if persons:
            top_persons = [p for p in persons if p.start >= 0 and p.start < 200]
            if top_persons:
                name_ent = max(top_persons, key=lambda e: (len(e.value), e.confidence))
            else:
                with_pos = [p for p in persons if p.start >= 0]
                if with_pos:
                    name_ent = min(with_pos, key=lambda e: e.start)
                else:
                    name_ent = max(persons, key=lambda e: (len(e.value), e.confidence))
            data["name"] = name_ent.value
            confs["name"] = name_ent.confidence

    if email := extraction.best_of_type("EMAIL"):
        data["email"] = email.value.lower()
        confs["email"] = email.confidence

    if phone := extraction.best_of_type("PHONE"):
        data["phone"] = _normalize_phone(phone.value)
        confs["phone"] = phone.confidence

    # Location — useful for resumes
    locations = extraction.of_type("LOCATION")
    if locations:
        # Prefer locations in the header (first 300 characters)
        header_locations = [loc for loc in locations if loc.start >= 0 and loc.start < 300]
        if header_locations:
            data["location"] = header_locations[0].value
            confs["location"] = header_locations[0].confidence
        else:
            # If no header location, check if there's an address-like pattern near the top
            addr_match = re.search(r'\b([A-Za-z\s]+(?:WA|NSW|VIC|QLD|SA|TAS|ACT|NT|[A-Z]{2})\s+\d{4,5})\b', text[:500])
            if addr_match:
                data["location"] = addr_match.group(1).strip()
                confs["location"] = 0.8
            else:
                data["location"] = locations[0].value
                confs["location"] = locations[0].confidence

    skills = _extract_skills_section(text)
    if skills:
        data["skills"] = skills
        confs["skills"] = 0.7

    education = _extract_education_section(text, extraction)
    if education:
        data["education"] = education
        confs["education"] = 0.6

    experience = _extract_experience_section(text, extraction)
    if experience:
        data["experience"] = experience
        confs["experience"] = 0.6

    return MappingResult(data=data, confidence_scores=confs, entities=extraction.entities)


def _extract_skills_section(text: str) -> List[str]:
    m = _SKILL_SECTION_RE.search(text)
    if not m:
        return []
    body = m.group("body")
    # Skills are usually comma- bullet- or pipe-separated
    raw = re.split(r"[,;|•·\n]+", body)
    skills = [s.strip(" -·•\t") for s in raw if 1 < len(s.strip()) < 40]
    return _dedupe_preserving_order(skills)[:30]


def _extract_education_section(text: str, extraction: ExtractionResult) -> List[Dict[str, str]]:
    m = _EDUCATION_SECTION_RE.search(text)
    if not m:
        return []
    body = m.group("body").strip()
    entries: List[Dict[str, str]] = []

    # Known ORG entities for matching
    org_values = {ent.value for ent in extraction.of_type("ORG")}

    # Parse line by line, grouping institution + degree
    current_entry: Dict[str, str] | None = None
    for line in body.splitlines():
        line = line.strip(" -·•\t")
        if len(line) < 5:
            continue

        # Detect year patterns like "2026", "Graduating 2026", "2020 – 2024"
        year_m = re.search(r"\b(19|20)\d{2}\b", line)

        # Check if this line mentions a known ORG (institution)
        matched_org = None
        for org in org_values:
            if org in line and len(org) > 3:  # skip very short ORG names
                matched_org = org
                break

        # Detect degree keywords
        degree_m = re.search(
            r"\b(?:Bachelor|Master|Doctor|Ph\.?D|M\.?S|B\.?S|B\.?A|M\.?A|M\.?B\.?A|Associate|Diploma|Certificate)"
            r"(?:\s+of\s+[A-Za-z\s]+)?",
            line, re.IGNORECASE,
        )

        # If line looks like an institution header (has an ORG and/or degree)
        if matched_org or degree_m:
            if degree_m and current_entry and "institution" in current_entry and "degree" not in current_entry:
                # This is a degree line for the previous institution
                current_entry["degree"] = degree_m.group(0).strip()
                if year_m:
                    current_entry["year"] = year_m.group(0)
            elif matched_org:
                # New institution entry
                if current_entry:
                    entries.append(current_entry)
                current_entry = {"institution": matched_org}
                if degree_m:
                    current_entry["degree"] = degree_m.group(0).strip()
                if year_m:
                    current_entry["year"] = year_m.group(0)
            elif degree_m:
                # Degree line without matched org — start a new entry
                if current_entry:
                    entries.append(current_entry)
                current_entry = {"degree": degree_m.group(0).strip()}
                if year_m:
                    current_entry["year"] = year_m.group(0)
        elif year_m and current_entry and "year" not in current_entry:
            current_entry["year"] = year_m.group(0)

        if len(entries) >= 6:
            break

    if current_entry:
        entries.append(current_entry)

    return entries[:6]


# Regex to detect a role/company header line in experience sections.
# Matches patterns like "Company Name  City, Country" or lines with date ranges.
_DATE_RANGE_RE = re.compile(
    r"(?:\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|\b(?:19|20)\d{2})\s*[-–—to]+\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|(?:19|20)\d{2}|[Pp]resent|[Cc]urrent)",
    re.IGNORECASE,
)


def _extract_experience_section(text: str, extraction: ExtractionResult) -> List[Dict[str, str]]:
    m = _EXPERIENCE_SECTION_RE.search(text)
    if not m:
        return []
    body = m.group("body").strip()
    entries: List[Dict[str, str]] = []

    org_values = {ent.value for ent in extraction.of_type("ORG")}
    current_entry: Dict[str, str] | None = None
    bullets: List[str] = []

    for line in body.splitlines():
        stripped = line.strip(" -·•\t")
        if len(stripped) < 3:
            continue

        # Check if this is a company/role header line
        matched_org = None
        for org in org_values:
            if org in stripped and len(org) > 3:
                matched_org = org
                break

        date_m = _DATE_RANGE_RE.search(stripped)

        # Detect job title patterns
        title_m = re.search(
            r"\b(?:(?:Senior|Junior|Lead|Principal|Staff|Chief|Head)\s+)?"
            r"(?:Software|Data|Frontend|Backend|Full[- ]?Stack|DevOps|Cloud|ML|AI|IT|QA)\s+"
            r"(?:Engineer|Developer|Architect|Analyst|Scientist|Consultant|Manager|Intern|Trainee)"
            r"|\b(?:Founder|Co-Founder|CTO|CEO|VP|Director|Manager|Intern|Trainee)\b",
            stripped, re.IGNORECASE,
        )

        is_header = matched_org or (date_m and not stripped.startswith("Built") and not stripped.startswith("Designed"))
        is_bullet = line.lstrip().startswith("•") or line.lstrip().startswith("-") or line.startswith("  ")

        if is_header and not is_bullet:
            # Save previous entry
            if current_entry:
                if bullets:
                    current_entry["description"] = " ".join(bullets[:3])
                entries.append(current_entry)
                bullets = []

            current_entry = {}
            if matched_org:
                current_entry["company"] = matched_org
            if title_m:
                current_entry["title"] = title_m.group(0).strip()
            if date_m:
                current_entry["dates"] = date_m.group(0).strip()
        elif current_entry is not None and is_bullet:
            bullets.append(stripped)
        elif current_entry is not None and title_m and "title" not in current_entry:
            current_entry["title"] = title_m.group(0).strip()

        if len(entries) >= 8:
            break

    if current_entry:
        if bullets:
            current_entry["description"] = " ".join(bullets[:3])
        entries.append(current_entry)

    return entries[:8]


# ---------------------------------------------------------------------------
# Medical report
# ---------------------------------------------------------------------------

_DOB_RE = re.compile(r"\b(?:DOB|Date\s*of\s*Birth)[\s:]*([\d/\-\.]{6,12})", re.IGNORECASE)
_VISIT_RE = re.compile(r"\b(?:Visit\s*Date|Date\s*of\s*Visit|Encounter\s*Date)[\s:]*([\d/\-\.]{6,12})", re.IGNORECASE)
_DIAG_RE = re.compile(r"(?:^|\n)\s*(?:diagnos[ie]s|assessment|impression)\s*[:\n]+(?P<body>.+?)(?:\n\s*\n|\Z)", re.IGNORECASE | re.DOTALL)
_MEDS_RE = re.compile(r"(?:^|\n)\s*(?:medications?|prescriptions?|rx)\s*[:\n]+(?P<body>.+?)(?:\n\s*\n|\Z)", re.IGNORECASE | re.DOTALL)
_VITAL_LINE_RE = re.compile(
    r"\b(BP|Blood\s*Pressure|HR|Heart\s*Rate|Pulse|Temp(?:erature)?|RR|SpO2|Weight|Height)\s*[:\-]?\s*([0-9./\s]+(?:mmHg|bpm|°[CF]|°|kg|lbs|cm|%)?)",
    re.IGNORECASE,
)


def _map_medical_report(extraction: ExtractionResult, text: str) -> MappingResult:
    data: Dict[str, Any] = {}
    confs: Dict[str, float] = {}

    if name := extraction.best_of_type("PERSON"):
        data["patient_name"] = name.value
        confs["patient_name"] = name.confidence

    if m := _DOB_RE.search(text):
        if iso := _normalize_date(m.group(1)):
            data["date_of_birth"] = iso
            confs["date_of_birth"] = 0.9

    if m := _VISIT_RE.search(text):
        if iso := _normalize_date(m.group(1)):
            data["visit_date"] = iso
            confs["visit_date"] = 0.9
    elif date_ent := extraction.best_of_type("DATE"):
        if iso := _normalize_date(date_ent.value):
            data["visit_date"] = iso
            confs["visit_date"] = date_ent.confidence * 0.7  # less reliable without label

    # Provider — typically an ORG or "Dr. ..." pattern
    dr_m = re.search(r"\bDr\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", text)
    if dr_m:
        data["provider"] = f"Dr. {dr_m.group(1)}"
        confs["provider"] = 0.85
    elif org := extraction.best_of_type("ORG"):
        data["provider"] = org.value
        confs["provider"] = org.confidence * 0.7

    # Diagnoses
    if m := _DIAG_RE.search(text):
        diags = [d.strip(" -·•\t") for d in re.split(r"[\n;]+", m.group("body"))]
        diags = [d for d in diags if 3 < len(d) < 200]
        if diags:
            data["diagnoses"] = diags[:10]
            confs["diagnoses"] = 0.7

    # Medications
    if m := _MEDS_RE.search(text):
        meds = [d.strip(" -·•\t") for d in re.split(r"[\n;]+", m.group("body"))]
        meds = [d for d in meds if 3 < len(d) < 200]
        if meds:
            data["medications"] = meds[:15]
            confs["medications"] = 0.7

    # Vitals
    vitals: Dict[str, str] = {}
    for m in _VITAL_LINE_RE.finditer(text):
        key = re.sub(r"\s+", "_", m.group(1).lower())
        vitals[key] = m.group(2).strip()
    if vitals:
        data["vitals"] = vitals
        confs["vitals"] = 0.8

    return MappingResult(data=data, confidence_scores=confs, entities=extraction.entities)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize_phone(raw: str, default_region: str = "US") -> str:
    try:
        num = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return raw  # leave as-is if we can't normalize


def _normalize_date(raw: str) -> Optional[str]:
    try:
        dt = date_parser.parse(raw, fuzzy=True, dayfirst=False)
        return dt.date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def _guess_title(text: str, name: Optional[str], email: Optional[str]) -> Optional[str]:
    """Find the line right after the person's name or before the email."""
    if not text:
        return None
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Title commonly appears immediately after the name on a business card
    if name:
        for i, line in enumerate(lines):
            if name in line and i + 1 < len(lines):
                candidate = lines[i + 1]
                if 3 < len(candidate) < 60 and not _looks_like_contact(candidate):
                    return candidate

    # Or right before the email line
    if email:
        for i, line in enumerate(lines):
            if email in line and i > 0:
                candidate = lines[i - 1]
                if 3 < len(candidate) < 60 and not _looks_like_contact(candidate):
                    return candidate

    return None


def _looks_like_contact(line: str) -> bool:
    return bool(re.search(r"[@()]|\d{3}", line))


def _dedupe_preserving_order(items) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out

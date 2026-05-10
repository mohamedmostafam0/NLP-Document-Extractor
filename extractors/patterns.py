"""Phase 3b — Regex / rule-based pattern extraction.

Targets structured fields that NER is bad at: emails, phone numbers,
URLs, currency amounts, calendar dates, and ID-like strings (SSN, MRN, etc).
"""

from __future__ import annotations

import logging
import re
from typing import List

import phonenumbers

from .base import Entity, ExtractionResult

logger = logging.getLogger("docxtract.patterns")


# Email — RFC-5322 lite. Good enough for resumes / cards.
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# URL — http(s) and bare domains
_URL_RE = re.compile(
    r"\b(?:https?://|www\.)[^\s,;()<>\[\]]+",
    re.IGNORECASE,
)

# Currency: symbol-prefixed or 3-letter-code
_MONEY_RE = re.compile(
    r"(?:[\$€£¥₹]|\b(?:USD|EUR|GBP|JPY|INR|EGP|AED|SAR)\b)\s?\d{1,3}(?:[,\d]{0,12})(?:\.\d{1,2})?",
    re.IGNORECASE,
)

# Common date formats — let dateutil parse the actual value in mapping.
_DATE_RES = [
    # ISO 2024-03-15
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    # 03/15/2024 or 15-03-2024
    re.compile(r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b"),
    # March 15, 2024 / 15 March 2024
    re.compile(
        r"\b(?:\d{1,2}\s+)?"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2}(?:,\s*|\s+)\d{2,4}\b",
        re.IGNORECASE,
    ),
]

# Identifier-like strings. These intentionally only match in clearly-labelled
# contexts to avoid false positives; mapping handles unlabelled cases.
_ID_RE = re.compile(
    r"(?P<label>(?:SSN|MRN|Patient\s*ID|Employee\s*ID|National\s*ID|Passport|License)[\s#:]*)"
    r"(?P<value>[A-Z0-9][A-Z0-9\-]{4,20})",
    re.IGNORECASE,
)


def extract_patterns(text: str, default_region: str = "US") -> ExtractionResult:
    if not text:
        return ExtractionResult()

    out: List[Entity] = []
    out.extend(_extract_emails(text))
    out.extend(_extract_phones(text, default_region))
    out.extend(_extract_urls(text))
    out.extend(_extract_money(text))
    out.extend(_extract_dates(text))
    out.extend(_extract_ids(text))
    out.extend(_extract_codes(text))

    logger.info("Regex patterns produced %d entities", len(out))
    return ExtractionResult(entities=out)


# ---------------------------------------------------------------------------

def _extract_emails(text: str) -> List[Entity]:
    out = []
    for m in _EMAIL_RE.finditer(text):
        out.append(Entity(
            type="EMAIL",
            value=m.group(0),
            confidence=0.95,
            source="regex",
            start=m.start(),
            end=m.end(),
        ))
    return out


def _extract_phones(text: str, default_region: str) -> List[Entity]:
    """phonenumbers does the heavy lifting — it handles formats from many regions."""
    out = []
    seen_spans: set[tuple[int, int]] = set()
    for match in phonenumbers.PhoneNumberMatcher(text, default_region):
        span = (match.start, match.end)
        if span in seen_spans:
            continue
        seen_spans.add(span)
        out.append(Entity(
            type="PHONE",
            value=text[match.start:match.end],
            confidence=0.9,
            source="regex",
            start=match.start,
            end=match.end,
        ))
    return out


def _extract_urls(text: str) -> List[Entity]:
    out = []
    for m in _URL_RE.finditer(text):
        # Trim trailing punctuation
        url = m.group(0).rstrip(".,;:")
        out.append(Entity(
            type="URL",
            value=url,
            confidence=0.9,
            source="regex",
            start=m.start(),
            end=m.start() + len(url),
        ))
    return out


def _extract_money(text: str) -> List[Entity]:
    out = []
    for m in _MONEY_RE.finditer(text):
        out.append(Entity(
            type="MONEY",
            value=m.group(0).strip(),
            confidence=0.85,
            source="regex",
            start=m.start(),
            end=m.end(),
        ))
    return out


def _extract_dates(text: str) -> List[Entity]:
    out: List[Entity] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in _DATE_RES:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            # Avoid duplicate hits from overlapping patterns
            if any(_overlaps(span, s) for s in seen_spans):
                continue
            seen_spans.add(span)
            out.append(Entity(
                type="DATE",
                value=m.group(0),
                confidence=0.88,
                source="regex",
                start=m.start(),
                end=m.end(),
            ))
    return out


def _extract_ids(text: str) -> List[Entity]:
    out = []
    for m in _ID_RE.finditer(text):
        label = m.group("label").strip().rstrip("#:").strip()
        out.append(Entity(
            type="ID",
            value=f"{label}: {m.group('value')}",
            confidence=0.9,
            source="regex",
            start=m.start(),
            end=m.end(),
        ))
    return out


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


# ---------------------------------------------------------------------------
# Codes — postal, country, product (ISBN/UPC/EAN/SKU)
# ---------------------------------------------------------------------------

# US ZIP (5 or 9 digit) — must be labelled or end-of-line/comma to avoid grabbing dates
_US_ZIP_RE = re.compile(
    r"(?:\bzip(?:\s*code)?\s*[:#-]?\s*)?(\d{5}(?:-\d{4})?)\b",
    re.IGNORECASE,
)

# UK postcode — format like SW1A 1AA
_UK_POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b"
)

# Canadian postal code — A1A 1A1
_CA_POSTCODE_RE = re.compile(
    r"\b([A-Z]\d[A-Z])\s*(\d[A-Z]\d)\b"
)

# ISBN-13 (with optional dashes); also matches ISBN-10
_ISBN_RE = re.compile(
    r"\bISBN(?:-1[03])?[\s:]*((?:97[89][\d-]{10,17}|[\dX][\d-]{8,15}))\b",
    re.IGNORECASE,
)

# UPC-A (12 digits) / EAN-13 (13 digits) — only when explicitly labelled
# to avoid catching arbitrary 12-digit numbers in resumes/reports.
_BARCODE_RE = re.compile(
    r"\b(?:UPC|EAN|GTIN|barcode)[\s:#-]*(\d{8,14})\b",
    re.IGNORECASE,
)

# Generic SKU / product code — labelled, alphanumeric with optional dashes
_SKU_RE = re.compile(
    r"\b(?:SKU|Part\s*(?:No|Number|#)|Item\s*(?:No|Number|#)|Product\s*Code|Model)"
    r"[\s:#-]*([A-Z0-9][A-Z0-9\-]{2,20})\b",
    re.IGNORECASE,
)

# ISO 3166 alpha-2 country codes — only when surrounded by clear context
# (uppercase, isolated by punctuation/whitespace, and labelled "country" nearby
# OR appearing alongside a known city/region pattern). We keep this conservative
# to avoid catching every pair of capitals in a resume.
_COUNTRY_LABELLED_RE = re.compile(
    r"\b(?:country|nationality)\s*[:#-]?\s*([A-Z]{2,3})\b",
    re.IGNORECASE,
)

_KNOWN_COUNTRY_CODES_2 = frozenset({
    "US", "GB", "UK", "DE", "FR", "ES", "IT", "NL", "SE", "NO", "DK", "FI",
    "JP", "CN", "IN", "BR", "MX", "CA", "AU", "NZ", "ZA", "EG", "AE", "SA",
    "TR", "IL", "RU", "PL", "CH", "AT", "BE", "PT", "IE", "GR", "KR",
})


def _extract_codes(text: str) -> List[Entity]:
    out: List[Entity] = []
    seen_spans: set[tuple[int, int]] = set()

    def _add(start: int, end: int, value: str, code_type: str, conf: float):
        span = (start, end)
        if any(_overlaps(span, s) for s in seen_spans):
            return
        seen_spans.add(span)
        out.append(Entity(
            type="CODE",
            value=f"{code_type}: {value}",
            confidence=conf,
            source="regex",
            start=start,
            end=end,
        ))

    # ISBN
    for m in _ISBN_RE.finditer(text):
        digits = re.sub(r"[^\dX]", "", m.group(1).upper())
        if len(digits) in (10, 13):
            _add(m.start(), m.end(), digits, "ISBN", 0.95)

    # UPC / EAN / GTIN — labelled
    for m in _BARCODE_RE.finditer(text):
        _add(m.start(), m.end(), m.group(1), "BARCODE", 0.9)

    # SKU / part number / model — labelled
    for m in _SKU_RE.finditer(text):
        _add(m.start(), m.end(), m.group(1).upper(), "SKU", 0.85)

    # UK postcode
    for m in _UK_POSTCODE_RE.finditer(text):
        value = f"{m.group(1)} {m.group(2)}"
        _add(m.start(), m.end(), value, "POSTCODE_UK", 0.9)

    # Canadian postal code
    for m in _CA_POSTCODE_RE.finditer(text):
        value = f"{m.group(1)} {m.group(2)}"
        _add(m.start(), m.end(), value, "POSTCODE_CA", 0.9)

    # US ZIP — only when labelled "zip" OR sitting at end of an address-looking line
    for m in _US_ZIP_RE.finditer(text):
        if m.group(0).lower().startswith("zip") or _looks_like_address_zip(text, m):
            _add(m.start(1), m.end(1), m.group(1), "POSTCODE_US", 0.85)

    # Labelled country code
    for m in _COUNTRY_LABELLED_RE.finditer(text):
        code = m.group(1).upper()
        if code in _KNOWN_COUNTRY_CODES_2 or len(code) == 3:
            _add(m.start(1), m.end(1), code, "COUNTRY", 0.9)

    return out


def _looks_like_address_zip(text: str, m: re.Match) -> bool:
    """Cheap heuristic: a 5-digit number preceded by 'STATE,' or a US state abbrev
    on the same line is very likely a ZIP."""
    line_start = text.rfind("\n", 0, m.start()) + 1
    line = text[line_start:m.start()]
    if re.search(r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|"
                 r"MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|"
                 r"SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\s*,?\s*$", line):
        return True
    return False

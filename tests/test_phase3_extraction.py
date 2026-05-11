"""Phase 3 — Extraction tests (regex patterns + NER).

The regex-based pattern tests are fully deterministic. NER tests load the
spaCy model lazily and are tolerant about exact spans because models differ.
"""

from __future__ import annotations

import pytest

from extractors import ner, patterns
from extractors.base import Entity, ExtractionResult


# ---------------------------------------------------------------------------
# ExtractionResult helpers
# ---------------------------------------------------------------------------

def test_extraction_result_of_type_filters_correctly():
    ents = [
        Entity(type="EMAIL", value="a@b.com", confidence=0.9),
        Entity(type="PHONE", value="+15555550000", confidence=0.8),
        Entity(type="EMAIL", value="c@d.com", confidence=0.5),
    ]
    result = ExtractionResult(entities=ents)
    emails = result.of_type("EMAIL")
    assert len(emails) == 2
    assert {e.value for e in emails} == {"a@b.com", "c@d.com"}


def test_extraction_result_best_of_type_picks_highest_confidence():
    ents = [
        Entity(type="PERSON", value="John", confidence=0.5),
        Entity(type="PERSON", value="John Doe", confidence=0.9),
        Entity(type="PERSON", value="Jane", confidence=0.7),
    ]
    best = ExtractionResult(entities=ents).best_of_type("PERSON")
    assert best is not None
    assert best.value == "John Doe"


def test_extraction_result_best_of_type_empty_returns_none():
    assert ExtractionResult().best_of_type("PERSON") is None


# ---------------------------------------------------------------------------
# Regex patterns — emails
# ---------------------------------------------------------------------------

def test_pattern_extracts_emails():
    result = patterns.extract_patterns("Contact: john.doe@example.com or jane@sub.co.uk!")
    emails = [e for e in result.entities if e.type == "EMAIL"]
    values = {e.value for e in emails}
    assert "john.doe@example.com" in values
    assert "jane@sub.co.uk" in values


def test_pattern_emails_get_high_confidence():
    result = patterns.extract_patterns("user@host.com")
    emails = [e for e in result.entities if e.type == "EMAIL"]
    assert emails and emails[0].confidence >= 0.9


# ---------------------------------------------------------------------------
# Regex patterns — phones
# ---------------------------------------------------------------------------

def test_pattern_extracts_us_phone():
    result = patterns.extract_patterns("Call me at (415) 555-0142 anytime.")
    phones = [e for e in result.entities if e.type == "PHONE"]
    assert phones, "Expected at least one phone match"


def test_pattern_extracts_international_phone():
    result = patterns.extract_patterns("UK office: +44 20 7946 0958")
    phones = [e for e in result.entities if e.type == "PHONE"]
    assert phones


# ---------------------------------------------------------------------------
# Regex patterns — URLs, money, dates
# ---------------------------------------------------------------------------

def test_pattern_extracts_urls_and_trims_punctuation():
    result = patterns.extract_patterns("See https://example.com/path. and www.foo.org!")
    urls = [e for e in result.entities if e.type == "URL"]
    assert any(u.value == "https://example.com/path" for u in urls)
    assert any(u.value.startswith("www.foo.org") for u in urls)
    # Trailing punctuation must be stripped
    assert all(not u.value.endswith((".", ",", ";", ":")) for u in urls)


def test_pattern_extracts_money():
    result = patterns.extract_patterns(
        "The price is $1,234.56, or EUR 200, or £50."
    )
    monies = [e for e in result.entities if e.type == "MONEY"]
    assert len(monies) >= 3


def test_pattern_extracts_iso_date():
    result = patterns.extract_patterns("Effective 2024-03-15.")
    dates = [e for e in result.entities if e.type == "DATE"]
    assert any(d.value == "2024-03-15" for d in dates)


def test_pattern_extracts_slash_date():
    result = patterns.extract_patterns("DOB 05/14/1982.")
    dates = [e for e in result.entities if e.type == "DATE"]
    assert any("05/14/1982" in d.value for d in dates)


def test_pattern_extracts_long_month_date():
    result = patterns.extract_patterns("Born March 15, 2024.")
    dates = [e for e in result.entities if e.type == "DATE"]
    assert dates


def test_pattern_dates_dont_double_count_overlaps():
    # Both the ISO and slash patterns could match parts of a normal date
    # if not deduped.
    result = patterns.extract_patterns("Today is 2024-03-15. Yes, 2024-03-15.")
    dates = [e for e in result.entities if e.type == "DATE"]
    assert len(dates) == 2  # two distinct occurrences, no overlap inflation


# ---------------------------------------------------------------------------
# Regex patterns — IDs and codes
# ---------------------------------------------------------------------------

def test_pattern_extracts_labelled_ssn():
    result = patterns.extract_patterns("SSN: 123-45-6789")
    ids = [e for e in result.entities if e.type == "ID"]
    assert any("SSN" in e.value for e in ids)


def test_pattern_extracts_isbn():
    result = patterns.extract_patterns("ISBN: 978-3-16-148410-0")
    codes = [e for e in result.entities if e.type == "CODE" and "ISBN" in e.value]
    assert codes


def test_pattern_extracts_uk_postcode():
    result = patterns.extract_patterns("Office at SW1A 1AA, London.")
    codes = [e for e in result.entities if e.type == "CODE" and "POSTCODE_UK" in e.value]
    assert codes


def test_pattern_extracts_us_zip_when_labelled():
    result = patterns.extract_patterns("Zip: 98101")
    codes = [e for e in result.entities if e.type == "CODE" and "POSTCODE_US" in e.value]
    assert codes


def test_pattern_does_not_extract_unlabelled_country_code():
    # Bare "US" should not become a COUNTRY code without a label
    result = patterns.extract_patterns("She works with US clients.")
    codes = [e for e in result.entities if e.type == "CODE" and "COUNTRY" in e.value]
    assert not codes


def test_pattern_empty_input_returns_empty_result():
    result = patterns.extract_patterns("")
    assert result.entities == []


# ---------------------------------------------------------------------------
# NER (spaCy) — these tests load the model lazily; they're slower.
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_ner_identifies_person_and_org():
    text = "Tim Cook is the CEO of Apple Inc."
    result = ner.extract_entities(text)
    types = {e.type for e in result.entities}
    assert "PERSON" in types
    # ORG label is also expected, but be lenient — spaCy small model
    # sometimes labels companies as PRODUCT.
    assert any(e.type in {"ORG", "PRODUCT"} for e in result.entities)


@pytest.mark.slow
def test_ner_handles_empty_text():
    result = ner.extract_entities("")
    assert result.entities == []


@pytest.mark.slow
def test_ner_extracts_location():
    text = "She moved from Seattle to Berlin last year."
    result = ner.extract_entities(text)
    locations = [e for e in result.entities if e.type == "LOCATION"]
    assert locations

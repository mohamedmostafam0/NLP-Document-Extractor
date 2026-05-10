"""Phase 2 — Preprocessing & cleaning.

Cleans raw ingested text (noise removal), detects language, segments into
sentences, tokenizes, and deduplicates repeated lines. The cleaner output
feeds directly into Phase 3 extractors.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

from langdetect import DetectorFactory, LangDetectException, detect

logger = logging.getLogger("docxtract.preprocessing")

# Make langdetect deterministic — it's seeded internally otherwise.
DetectorFactory.seed = 42

# Lazy-loaded spaCy pipeline. The model is only used for sentence segmentation
# and tokenization here; NER lives in extractors/ner.py.
_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is None:
        import spacy
        try:
            _NLP = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
        except OSError:
            logger.warning("spaCy model en_core_web_sm not found, downloading at runtime")
            from spacy.cli import download
            download("en_core_web_sm")
            _NLP = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
    return _NLP


# Common OCR / scan artifacts to remove
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTIPLE_SPACES_RE = re.compile(r"[ \t]+")
_MULTIPLE_NEWLINES_RE = re.compile(r"\n{3,}")
_PAGE_NUMBER_RE = re.compile(r"^\s*(?:page\s+)?\d+\s*(?:of\s+\d+)?\s*$", re.IGNORECASE)


@dataclass
class PreprocessingResult:
    cleaned_text: str
    sentences: List[str] = field(default_factory=list)
    tokens: List[str] = field(default_factory=list)
    language: Optional[str] = None
    duplicate_lines_removed: int = 0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def preprocess(raw_text: str) -> PreprocessingResult:
    cleaned, removed = _clean_and_dedupe(raw_text)
    language = _detect_language(cleaned)
    sentences, tokens = _segment(cleaned)

    return PreprocessingResult(
        cleaned_text=cleaned,
        sentences=sentences,
        tokens=tokens,
        language=language,
        duplicate_lines_removed=removed,
    )


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

def _clean_and_dedupe(text: str) -> tuple[str, int]:
    if not text:
        return "", 0

    # Unicode normalize (NFC). Strip control chars but keep \n and \t.
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL_CHARS_RE.sub("", text)

    # Per-line cleanup
    seen: set[str] = set()
    cleaned_lines: List[str] = []
    duplicates = 0

    for raw_line in text.splitlines():
        line = _MULTIPLE_SPACES_RE.sub(" ", raw_line).strip()

        # Drop empty lines (we'll re-collapse later) and pure page-numbers
        if not line:
            cleaned_lines.append("")
            continue
        if _PAGE_NUMBER_RE.match(line):
            continue

        # Dedupe — but only against meaningful, longer lines (>10 chars)
        # so we don't strip legitimate short repeats like field labels.
        if len(line) > 10:
            key = line.lower()
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)

        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = _MULTIPLE_NEWLINES_RE.sub("\n\n", cleaned).strip()
    return cleaned, duplicates


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def _detect_language(text: str) -> Optional[str]:
    if len(text.strip()) < 20:
        return None
    try:
        return detect(text)
    except LangDetectException:
        return None


# ---------------------------------------------------------------------------
# Segmentation & tokenization (spaCy)
# ---------------------------------------------------------------------------

def _segment(text: str) -> tuple[List[str], List[str]]:
    if not text.strip():
        return [], []

    nlp = _get_nlp()
    # spaCy default max_length is 1M chars — fine for any single document.
    doc = nlp(text)
    sentences = [s.text.strip() for s in doc.sents if s.text.strip()]
    tokens = [t.text for t in doc if not t.is_space]
    return sentences, tokens

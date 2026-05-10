"""Phase 3a — Named Entity Recognition.

Runs two models in parallel and merges their results:
  - spaCy en_core_web_sm  (fast, deterministic)
  - HuggingFace dslim/bert-base-NER  (higher recall, slower)

Each entity carries a confidence score. When both extractors agree on a span
we boost the confidence; the merger keeps the higher-confidence label on
overlap.
"""

from __future__ import annotations

import logging
from typing import List

from .base import Entity, ExtractionResult

logger = logging.getLogger("docxtract.ner")

# spaCy → canonical label map. We use uppercased canonical labels so the
# whole pipeline shares one vocabulary.
_SPACY_LABEL_MAP = {
    "PERSON": "PERSON",
    "ORG": "ORG",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "DATE": "DATE",
    "TIME": "TIME",
    "MONEY": "MONEY",
    "PERCENT": "PERCENT",
    "NORP": "NORP",
    "FAC": "FACILITY",
    "PRODUCT": "PRODUCT",
}

# dslim/bert-base-NER → canonical label map (it uses CoNLL-2003 schema)
_HF_LABEL_MAP = {
    "PER": "PERSON",
    "ORG": "ORG",
    "LOC": "LOCATION",
    "MISC": "MISC",
}

# Confidence floor below which we discard transformer hits as noise
_HF_MIN_SCORE = 0.65


# ---------------------------------------------------------------------------
# Lazy model loaders
# ---------------------------------------------------------------------------

_SPACY = None
_HF_PIPELINE = None


def _get_spacy():
    global _SPACY
    if _SPACY is None:
        import spacy
        try:
            _SPACY = spacy.load("en_core_web_sm")
        except OSError:
            logger.warning("Downloading en_core_web_sm at runtime")
            from spacy.cli import download
            download("en_core_web_sm")
            _SPACY = spacy.load("en_core_web_sm")
    return _SPACY


def _get_hf():
    global _HF_PIPELINE
    if _HF_PIPELINE is None:
        try:
            from transformers import pipeline
            _HF_PIPELINE = pipeline(
                "ner",
                model="dslim/bert-base-NER",
                aggregation_strategy="simple",
            )
        except Exception:
            logger.exception("Failed to load HuggingFace NER pipeline; will skip")
            _HF_PIPELINE = False  # sentinel: tried & failed
    return _HF_PIPELINE if _HF_PIPELINE else None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_entities(text: str) -> ExtractionResult:
    if not text.strip():
        return ExtractionResult()

    spacy_ents = _run_spacy(text)
    hf_ents = _run_hf(text)
    merged = _merge(spacy_ents + hf_ents)
    logger.info(
        "NER produced %d entities (spaCy=%d, HF=%d, merged=%d)",
        len(merged), len(spacy_ents), len(hf_ents), len(merged),
    )
    return ExtractionResult(entities=merged)


# ---------------------------------------------------------------------------
# Per-model runners
# ---------------------------------------------------------------------------

def _run_spacy(text: str) -> List[Entity]:
    nlp = _get_spacy()
    doc = nlp(text)
    out: List[Entity] = []
    for ent in doc.ents:
        canonical = _SPACY_LABEL_MAP.get(ent.label_)
        if not canonical:
            continue
        out.append(Entity(
            type=canonical,
            value=ent.text.strip(),
            confidence=0.85,  # spaCy doesn't expose per-entity probs by default
            source="spacy",
            start=ent.start_char,
            end=ent.end_char,
        ))
    return out


def _run_hf(text: str) -> List[Entity]:
    pipe = _get_hf()
    if pipe is None:
        return []

    # bert-base-NER's tokenizer max length is 512; chunk long inputs.
    out: List[Entity] = []
    for chunk_start, chunk in _chunked(text, max_chars=2000):
        try:
            results = pipe(chunk)
        except Exception:
            logger.exception("HF NER failed on chunk")
            continue

        for r in results:
            score = float(r.get("score", 0.0))
            if score < _HF_MIN_SCORE:
                continue
            label = _HF_LABEL_MAP.get(r.get("entity_group", ""))
            if not label:
                continue
            out.append(Entity(
                type=label,
                value=r["word"].strip(),
                confidence=score,
                source="transformer",
                start=chunk_start + int(r.get("start", -1)),
                end=chunk_start + int(r.get("end", -1)),
            ))
    return out


def _chunked(text: str, max_chars: int):
    """Yield (offset, chunk) pairs split on paragraph boundaries when possible."""
    if len(text) <= max_chars:
        yield 0, text
        return

    pos = 0
    n = len(text)
    while pos < n:
        end = min(pos + max_chars, n)
        # Try to break at a newline within the last 200 chars of the window
        if end < n:
            split = text.rfind("\n", pos, end)
            if split > pos + max_chars - 200:
                end = split
        yield pos, text[pos:end]
        pos = end


# ---------------------------------------------------------------------------
# Merging — dedupe overlapping spans, prefer higher confidence
# ---------------------------------------------------------------------------

def _merge(entities: List[Entity]) -> List[Entity]:
    """Combine spaCy + HF results.

    Strategy: bucket by (type, normalized_value). When the same entity
    appears from both sources, average their confidences and bump by 0.1
    (capped at 0.99) — agreement is a strong signal.
    """
    groups: dict[tuple[str, str], List[Entity]] = {}
    for ent in entities:
        key = (ent.type, _normalize(ent.value))
        groups.setdefault(key, []).append(ent)

    out: List[Entity] = []
    for (etype, _value), group in groups.items():
        if len(group) == 1:
            out.append(group[0])
            continue

        # Consensus: keep the longest value, average confidence + boost
        best = max(group, key=lambda e: (len(e.value), e.confidence))
        avg_conf = sum(e.confidence for e in group) / len(group)
        boosted = min(0.99, avg_conf + 0.1)
        out.append(Entity(
            type=etype,
            value=best.value,
            confidence=boosted,
            source="consensus",
            start=best.start,
            end=best.end,
        ))

    return out


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())

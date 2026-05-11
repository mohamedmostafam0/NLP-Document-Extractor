"""End-to-end pipeline orchestrator.

Runs phases 1 → 5 for a single document and returns a consolidated result
that the API layer (Phase 6) can persist and expose.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

import json

from extractors.base import Entity, ExtractionResult
from extractors.ner import extract_entities as run_ner
from extractors.patterns import extract_patterns as run_patterns
from utils.money import normalize_money

from routers.progress import set_phase
from . import ingestion, mapping, preprocessing, validation

logger = logging.getLogger("docxtract.orchestrator")


@dataclass
class PipelineResult:
    raw_text: str = ""
    cleaned_text: str = ""
    language: str | None = None
    used_ocr: bool = False
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    entities: List[Entity] = field(default_factory=list)
    status: str = "completed"      # completed | needs_review | failed
    issues: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)


def _normalize_entities_in_place(entities: List[Entity]) -> None:
    """Fill `Entity.normalized_value` for types that have a canonical form."""
    from dateutil import parser as date_parser
    import phonenumbers

    for ent in entities:
        if ent.normalized_value:
            continue
        try:
            if ent.type == "MONEY":
                norm = normalize_money(ent.value)
                if norm:
                    ent.normalized_value = json.dumps(norm)
            elif ent.type == "DATE":
                dt = date_parser.parse(ent.value, fuzzy=True, dayfirst=False)
                ent.normalized_value = dt.date().isoformat()
            elif ent.type == "PHONE":
                num = phonenumbers.parse(ent.value, "US")
                if phonenumbers.is_valid_number(num):
                    ent.normalized_value = phonenumbers.format_number(
                        num, phonenumbers.PhoneNumberFormat.E164,
                    )
            elif ent.type == "EMAIL":
                ent.normalized_value = ent.value.lower()
            elif ent.type == "URL":
                ent.normalized_value = ent.value.lower().rstrip("/")
        except Exception:
            # Normalization is best-effort — never fail the pipeline over it.
            pass


def run(file_bytes: bytes, filename: str, doc_type: str, doc_id: int | None = None) -> PipelineResult:
    logger.info("Starting pipeline for %s (%s)", filename, doc_type)

    def _emit(phase: str, detail: str = "", status: str = "active") -> None:
        if doc_id is not None:
            set_phase(doc_id, phase, status=status, detail=detail)

    # Phase 1 — ingest
    _emit("ingestion", "Extracting text from document…")
    ingested = ingestion.ingest(file_bytes, filename)
    logger.info(
        "Phase 1 done: %d chars, format=%s, ocr=%s",
        ingested.char_count, ingested.source_format, ingested.used_ocr,
    )

    if not ingested.text.strip():
        return PipelineResult(
            raw_text="",
            status="failed",
            issues=["No text could be extracted from the document."],
            used_ocr=ingested.used_ocr,
        )

    # Phase 2 — preprocess
    _emit("preprocessing", "Cleaning text & detecting language…")
    pre = preprocessing.preprocess(ingested.text)
    logger.info(
        "Phase 2 done: language=%s, sentences=%d, dupes_removed=%d",
        pre.language, len(pre.sentences), pre.duplicate_lines_removed,
    )

    # Phase 3 — NER + patterns (run on cleaned text)
    _emit("extraction", "Running NER & pattern matching…")
    ner_result = run_ner(pre.cleaned_text)
    pattern_result = run_patterns(pre.cleaned_text)
    combined = ExtractionResult(entities=ner_result.entities + pattern_result.entities)
    logger.info("Phase 3 done: %d entities", len(combined.entities))

    # Phase 4 — schema mapping & normalization
    _emit("mapping", "Mapping entities to structured fields…")
    mapped = mapping.map_to_schema(combined, doc_type, pre.cleaned_text)
    _normalize_entities_in_place(combined.entities)
    logger.info(
        "Phase 4 done: %d fields populated",
        len(mapped.data),
    )

    # Phase 5 — validate & QC
    _emit("validation", "Running quality checks…")
    validated = validation.validate(mapped.data, mapped.confidence_scores, doc_type)
    logger.info(
        "Phase 5 done: valid=%s, needs_review=%s, issues=%d",
        validated.is_valid, validated.needs_review, len(validated.issues),
    )

    status = (
        "needs_review" if validated.needs_review
        else "completed" if validated.is_valid
        else "completed"  # not strictly invalid → still let it through
    )

    _emit("done", f"Pipeline finished — {status}")

    return PipelineResult(
        raw_text=ingested.text,
        cleaned_text=pre.cleaned_text,
        language=pre.language,
        used_ocr=ingested.used_ocr,
        extracted_data=validated.data,
        confidence_scores=mapped.confidence_scores,
        entities=combined.entities,
        status=status,
        issues=validated.issues,
        missing_required=validated.missing_required,
    )

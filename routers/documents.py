"""API endpoints — upload, list, process, export, delete, and review queue."""

import csv
import io
import json
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from config import settings
from models.database import AuditLog, Document, ExtractedEntity, get_db
from models.schemas import (
    ApproveRequest,
    AuditLogEntry,
    AuditLogResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
    StatusResponse,
)
from pipeline.orchestrator import run as run_pipeline
from services.storage import get_storage

logger = logging.getLogger("docxtract.api")
router = APIRouter()

VALID_DOC_TYPES = frozenset({"business_card", "resume", "medical_report"})
_SAFE_FILENAME_RE = re.compile(r"[^\w\s\-.]", re.UNICODE)


def _sanitize_filename(name: str) -> str:
    name = name.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    name = _SAFE_FILENAME_RE.sub("", name)
    return name.strip() or "unnamed"


def _get_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", maxsplit=1)[-1].lower()


def _log_event(
    db: Session,
    *,
    document_id: int | None,
    event_type: str,
    detail: dict | None = None,
    actor: str = "system",
) -> None:
    """Append an audit-log row. Caller is responsible for committing."""
    db.add(AuditLog(
        document_id=document_id,
        event_type=event_type,
        actor=actor,
        detail=detail,
    ))


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    db: Session = Depends(get_db),
):
    if doc_type not in VALID_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type. Must be one of: {', '.join(sorted(VALID_DOC_TYPES))}",
        )

    safe_name = _sanitize_filename(file.filename or "unnamed.txt")
    ext = _get_extension(safe_name)
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '.{ext}'. Allowed: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Max: {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    object_name = f"{doc_type}/{uuid.uuid4().hex}.{ext}"
    try:
        storage = get_storage()
        storage.upload_file(content, object_name, file.content_type or "application/octet-stream")
    except Exception:
        logger.exception("MinIO upload failed for %s", safe_name)
        raise HTTPException(status_code=502, detail="File storage is currently unavailable.")

    doc = Document(
        filename=safe_name,
        doc_type=doc_type,
        status="uploaded",
        minio_path=object_name,
        file_size=len(content),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _log_event(db, document_id=doc.id, event_type="upload", detail={
        "filename": safe_name,
        "doc_type": doc_type,
        "file_size": len(content),
    })
    db.commit()

    logger.info("Uploaded document id=%d filename=%s type=%s", doc.id, safe_name, doc_type)
    return DocumentUploadResponse.model_validate(doc)


# ---------------------------------------------------------------------------
# List & detail
# ---------------------------------------------------------------------------

@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    query = db.query(Document)
    if status_filter:
        query = query.filter(Document.status == status_filter)
    docs = query.order_by(Document.created_at.desc()).all()
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in docs],
        total=len(docs),
    )


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentResponse.model_validate(doc)


# ---------------------------------------------------------------------------
# Process — runs the full pipeline
# ---------------------------------------------------------------------------

@router.post("/documents/{doc_id}/process", response_model=StatusResponse)
async def process_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.status == "processing":
        raise HTTPException(status_code=409, detail="Document is already being processed.")

    doc.status = "processing"
    db.commit()

    try:
        storage = get_storage()
        file_data = storage.get_file(doc.minio_path)

        # Run the full pipeline. This is sync today — fine for small files;
        # later we'd hand it to a worker queue.
        result = run_pipeline(file_data, doc.filename, doc.doc_type)

        doc.raw_text = result.raw_text
        doc.extracted_data = result.extracted_data
        doc.confidence_scores = result.confidence_scores
        doc.issues = result.issues or None
        doc.missing_required = result.missing_required or None
        doc.language = result.language
        doc.used_ocr = "true" if result.used_ocr else "false"
        doc.status = result.status
        doc.processed_at = datetime.now(timezone.utc)
        doc.error_message = None

        # Persist individual entities for searchability
        # (clear any previous run first)
        db.query(ExtractedEntity).filter(ExtractedEntity.document_id == doc.id).delete()
        for ent in result.entities:
            db.add(ExtractedEntity(
                document_id=doc.id,
                entity_type=ent.type,
                entity_value=ent.value,
                normalized_value=ent.normalized_value or ent.value,
                confidence=ent.confidence,
            ))

        _log_event(db, document_id=doc.id, event_type="process", detail={
            "result_status": doc.status,
            "fields_extracted": len(result.extracted_data or {}),
            "entities": len(result.entities),
            "issues": len(result.issues),
            "used_ocr": result.used_ocr,
            "language": result.language,
        })
        db.commit()
        logger.info("Processed document id=%d status=%s", doc.id, doc.status)

    except Exception as exc:
        logger.exception("Pipeline failed for document id=%d", doc.id)
        db.rollback()
        doc.status = "failed"
        doc.error_message = str(exc)[:500]
        _log_event(db, document_id=doc.id, event_type="process_failed", detail={
            "error": str(exc)[:500],
        })
        db.commit()
        raise HTTPException(status_code=500, detail="Document processing failed.")

    return StatusResponse(status=doc.status, document_id=doc_id)


# ---------------------------------------------------------------------------
# Export — JSON or CSV
# ---------------------------------------------------------------------------

@router.get("/documents/{doc_id}/export")
async def export_document(
    doc_id: int,
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if not doc.extracted_data:
        raise HTTPException(status_code=400, detail="Document has no extracted data to export.")

    _log_event(db, document_id=doc.id, event_type="export", detail={"format": format})
    db.commit()

    if format == "json":
        payload = {
            "id": doc.id,
            "filename": doc.filename,
            "doc_type": doc.doc_type,
            "status": doc.status,
            "extracted_data": doc.extracted_data,
            "confidence_scores": doc.confidence_scores,
            "language": doc.language,
            "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
        }
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        return StreamingResponse(
            iter([body]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{doc.filename}.json"'},
        )

    # CSV — flatten one level deep
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["field", "value", "confidence"])
    for key, value in (doc.extracted_data or {}).items():
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        conf = (doc.confidence_scores or {}).get(key, "")
        writer.writerow([key, value, conf])

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}.csv"'},
    )


# ---------------------------------------------------------------------------
# Bulk export — all completed docs of a type as a single JSON array
# ---------------------------------------------------------------------------

@router.get("/export/bulk")
async def bulk_export(
    doc_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Document).filter(Document.extracted_data.isnot(None))
    if doc_type:
        if doc_type not in VALID_DOC_TYPES:
            raise HTTPException(status_code=400, detail="Invalid doc_type.")
        query = query.filter(Document.doc_type == doc_type)

    docs = query.order_by(Document.created_at.desc()).all()
    payload = [
        {
            "id": d.id,
            "filename": d.filename,
            "doc_type": d.doc_type,
            "status": d.status,
            "extracted_data": d.extracted_data,
            "confidence_scores": d.confidence_scores,
            "processed_at": d.processed_at.isoformat() if d.processed_at else None,
        }
        for d in docs
    ]
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return StreamingResponse(
        iter([body]),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="docxtract-bulk.json"'},
    )


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

@router.get("/review-queue", response_model=ReviewQueueResponse)
async def review_queue(db: Session = Depends(get_db)):
    """All documents that need human review."""
    docs = (
        db.query(Document)
        .filter(Document.status == "needs_review")
        .order_by(Document.created_at.desc())
        .all()
    )
    return ReviewQueueResponse(
        items=[ReviewQueueItem.model_validate(d) for d in docs],
        total=len(docs),
    )


@router.post("/documents/{doc_id}/approve", response_model=StatusResponse)
async def approve_document(
    doc_id: int,
    payload: ApproveRequest,
    db: Session = Depends(get_db),
):
    """Mark a needs_review document as completed; optionally update fields."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.status not in ("needs_review", "completed"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve document in status '{doc.status}'.",
        )

    if payload.extracted_data is not None:
        # Reviewer-corrected fields → confidence pinned to 1.0 for those keys
        doc.extracted_data = payload.extracted_data
        confs = dict(doc.confidence_scores or {})
        for k in payload.extracted_data:
            confs[k] = 1.0
        doc.confidence_scores = confs

    doc.status = "completed"
    doc.issues = None
    doc.missing_required = None
    _log_event(db, document_id=doc.id, event_type="approve", actor="reviewer", detail={
        "fields_corrected": list(payload.extracted_data.keys()) if payload.extracted_data else [],
    })
    db.commit()

    logger.info("Document id=%d approved by reviewer", doc.id)
    return StatusResponse(status="completed", document_id=doc.id)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit-log", response_model=AuditLogResponse)
async def audit_log_global(
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Most recent audit events across all documents."""
    rows = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return AuditLogResponse(
        events=[AuditLogEntry.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.get("/documents/{doc_id}/audit-log", response_model=AuditLogResponse)
async def audit_log_for_document(doc_id: int, db: Session = Depends(get_db)):
    """Full audit history for a single document."""
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.document_id == doc_id)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    return AuditLogResponse(
        events=[AuditLogEntry.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.delete("/documents/{doc_id}", response_model=StatusResponse)
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    try:
        storage = get_storage()
        storage.delete_file(doc.minio_path)
    except Exception:
        logger.warning("Failed to delete MinIO object %s (may already be removed)", doc.minio_path)

    # Snapshot before deletion so the audit row survives the cascade
    snapshot = {"filename": doc.filename, "doc_type": doc.doc_type, "status": doc.status}
    db.delete(doc)
    db.flush()  # cascade fires before we add the audit row
    _log_event(db, document_id=None, event_type="delete", detail=snapshot)
    db.commit()

    logger.info("Deleted document id=%d", doc_id)
    return StatusResponse(status="deleted", document_id=doc_id)

"""API endpoints for document upload, listing, processing, and deletion."""

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from models.database import get_db, Document
from models.schemas import (
    DocumentResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    StatusResponse,
)
from services.storage import get_storage

logger = logging.getLogger("docxtract.api")
router = APIRouter()

# Valid document types accepted by the system
VALID_DOC_TYPES = frozenset({"business_card", "resume", "medical_report"})

# Regex for sanitising filenames — keep only safe characters
_SAFE_FILENAME_RE = re.compile(r"[^\w\s\-.]", re.UNICODE)


def _sanitize_filename(name: str) -> str:
    """Strip path components and dangerous characters from a user-supplied filename."""
    # Remove any directory path traversal
    name = name.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    # Remove non-safe chars
    name = _SAFE_FILENAME_RE.sub("", name)
    return name.strip() or "unnamed"


def _get_extension(filename: str) -> str:
    """Extract and validate the lowercase file extension."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", maxsplit=1)[-1].lower()


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    db: Session = Depends(get_db),
):
    """Upload a document to MinIO staging and register it in the database."""

    # --- Validate doc_type ---
    if doc_type not in VALID_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type. Must be one of: {', '.join(sorted(VALID_DOC_TYPES))}",
        )

    # --- Validate filename / extension ---
    safe_name = _sanitize_filename(file.filename or "unnamed.txt")
    ext = _get_extension(safe_name)
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '.{ext}'. Allowed: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}",
        )

    # --- Read & validate size ---
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Max: {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    # --- Upload to MinIO ---
    object_name = f"{doc_type}/{uuid.uuid4().hex}.{ext}"
    try:
        storage = get_storage()
        storage.upload_file(content, object_name, file.content_type or "application/octet-stream")
    except Exception:
        logger.exception("MinIO upload failed for %s", safe_name)
        raise HTTPException(status_code=502, detail="File storage is currently unavailable.")

    # --- Persist to DB ---
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

    logger.info("Uploaded document id=%d filename=%s type=%s", doc.id, safe_name, doc_type)
    return DocumentUploadResponse.model_validate(doc)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(db: Session = Depends(get_db)):
    """List all documents, most recent first."""
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in docs],
        total=len(docs),
    )


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: int, db: Session = Depends(get_db)):
    """Get a single document with its extracted data."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentResponse.model_validate(doc)


# ---------------------------------------------------------------------------
# Process
# ---------------------------------------------------------------------------

@router.post("/documents/{doc_id}/process", response_model=StatusResponse)
async def process_document(doc_id: int, db: Session = Depends(get_db)):
    """Trigger the NLP extraction pipeline for a specific document."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if doc.status == "processing":
        raise HTTPException(status_code=409, detail="Document is already being processed.")

    # Mark as processing
    doc.status = "processing"
    db.commit()

    try:
        # Read file from MinIO staging layer
        storage = get_storage()
        file_data = storage.get_file(doc.minio_path)
        raw_text = file_data.decode("utf-8", errors="replace")

        # TODO: Replace with actual pipeline invocation
        # pipeline_result = orchestrator.run(raw_text, doc.doc_type)
        doc.raw_text = raw_text
        doc.status = "completed"
        doc.extracted_data = {"_note": "Pipeline not yet implemented — raw text stored."}
        doc.processed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("Processed document id=%d status=completed", doc.id)

    except Exception:
        logger.exception("Pipeline failed for document id=%d", doc.id)
        db.rollback()
        doc.status = "failed"
        doc.error_message = "An error occurred during processing."
        db.commit()
        raise HTTPException(status_code=500, detail="Document processing failed.")

    return StatusResponse(status="completed", document_id=doc_id)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/documents/{doc_id}", response_model=StatusResponse)
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """Delete a document record and its file from MinIO."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Best-effort MinIO cleanup
    try:
        storage = get_storage()
        storage.delete_file(doc.minio_path)
    except Exception:
        logger.warning("Failed to delete MinIO object %s (may already be removed)", doc.minio_path)

    db.delete(doc)
    db.commit()

    logger.info("Deleted document id=%d", doc_id)
    return StatusResponse(status="deleted", document_id=doc_id)

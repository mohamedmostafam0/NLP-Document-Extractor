import logging
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float,
    DateTime, JSON, ForeignKey, Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from config import settings

logger = logging.getLogger("docxtract.db")


def _make_engine():
    """Build an engine with dialect-appropriate connect args."""
    kwargs = {"pool_pre_ping": True}
    if settings.DATABASE_URL.startswith("sqlite"):
        # SQLite needs check_same_thread=False for FastAPI's request-scoped sessions
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(settings.DATABASE_URL, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Document(Base):
    """A user-uploaded document and its processing results."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(50), nullable=False)
    status = Column(String(20), default="uploaded", nullable=False)
    minio_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True)
    extracted_data = Column(JSON, nullable=True)
    confidence_scores = Column(JSON, nullable=True)
    issues = Column(JSON, nullable=True)
    missing_required = Column(JSON, nullable=True)
    language = Column(String(10), nullable=True)
    used_ocr = Column(String(5), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime, nullable=True)

    entities = relationship(
        "ExtractedEntity", back_populates="document",
        cascade="all, delete-orphan",
    )
    audit_events = relationship(
        "AuditLog", back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_documents_doc_type", "doc_type"),
        Index("ix_documents_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status!r}>"


class ExtractedEntity(Base):
    """An individual entity extracted from a document."""

    __tablename__ = "extracted_entities"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type = Column(String(100), nullable=False)
    entity_value = Column(Text, nullable=False)
    normalized_value = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)

    document = relationship("Document", back_populates="entities")

    def __repr__(self) -> str:
        return (
            f"<ExtractedEntity id={self.id} type={self.entity_type!r} "
            f"value={self.entity_value!r}>"
        )


class AuditLog(Base):
    """Append-only record of significant events on a document.

    Captures who/what/when for upload, process, approve, delete, export.
    `actor` is a free-form string today (no auth wired up); when auth lands,
    it'll hold the authenticated user id.
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,   # nullable so we keep records of deleted docs if cascade is removed later
        index=True,
    )
    event_type = Column(String(50), nullable=False, index=True)
    actor = Column(String(100), nullable=True)
    detail = Column(JSON, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    document = relationship("Document", back_populates="audit_events")

    def __repr__(self) -> str:
        return f"<AuditLog event={self.event_type!r} doc_id={self.document_id}>"


def create_tables():
    """Create all tables if they don't already exist, then patch in any new columns."""
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()
    logger.info("Database tables ensured.")


def _apply_lightweight_migrations():
    """Add columns introduced after the initial schema.

    Dialect-aware: uses information_schema on Postgres, PRAGMA on SQLite.
    Safe to run repeatedly — each ALTER is guarded.
    """
    from sqlalchemy import text

    new_columns = {
        "issues": "JSON",
        "missing_required": "JSON",
        "language": "VARCHAR(10)",
        "used_ocr": "VARCHAR(5)",
    }

    dialect = engine.dialect.name

    with engine.connect() as conn:
        if dialect == "sqlite":
            existing = {
                row[1] for row in conn.execute(text("PRAGMA table_info(documents)"))
            }
        else:
            # Postgres / MySQL / etc.
            rows = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'documents'"
            ))
            existing = {row[0] for row in rows}

        for col, ddl in new_columns.items():
            if col in existing:
                continue
            try:
                conn.execute(text(f"ALTER TABLE documents ADD COLUMN {col} {ddl}"))
                conn.commit()
                logger.info("Added column documents.%s", col)
            except Exception:
                logger.warning("Could not add column %s (may already exist)", col)

import logging
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float,
    DateTime, JSON, ForeignKey, Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from config import settings

logger = logging.getLogger("docxtract.db")

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
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
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime, nullable=True)

    entities = relationship(
        "ExtractedEntity", back_populates="document",
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


def create_tables():
    """Create all tables if they don't already exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured.")

"""Pydantic schemas for API request/response validation and domain data models."""

from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime


# ---------------------------------------------------------------------------
# API response schemas
# ---------------------------------------------------------------------------

class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    doc_type: str
    status: str
    file_size: Optional[int] = None
    created_at: datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    doc_type: str
    status: str
    file_size: Optional[int] = None
    raw_text: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    confidence_scores: Optional[Dict[str, float]] = None
    error_message: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int


class StatusResponse(BaseModel):
    """Generic acknowledgement response."""
    status: str
    document_id: int


# ---------------------------------------------------------------------------
# Document-type-specific extraction schemas
# ---------------------------------------------------------------------------

class BusinessCardData(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None


class EducationEntry(BaseModel):
    degree: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[str] = None


class ExperienceEntry(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    dates: Optional[str] = None
    description: Optional[str] = None


class ResumeData(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    education: Optional[List[EducationEntry]] = None
    experience: Optional[List[ExperienceEntry]] = None
    skills: Optional[List[str]] = None


class MedicalReportData(BaseModel):
    patient_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    visit_date: Optional[str] = None
    provider: Optional[str] = None
    diagnoses: Optional[List[str]] = None
    medications: Optional[List[str]] = None
    vitals: Optional[Dict[str, str]] = None

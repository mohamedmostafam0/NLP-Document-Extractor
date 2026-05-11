"""Shared pytest fixtures.

Heavy NLP models (spaCy + HuggingFace transformer) are loaded lazily inside
the extractors. We expose session-scoped fixtures so each model is loaded
at most once across the whole test run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = PROJECT_ROOT / "samples"
DATA_SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"


# ---------------------------------------------------------------------------
# Sample text fixtures — short, hand-crafted inputs that don't need OCR.
# ---------------------------------------------------------------------------

@pytest.fixture
def business_card_text() -> str:
    return (
        "Richard Hendricks\n"
        "CEO & Founder\n"
        "\n"
        "Pied Piper Inc.\n"
        "5230 Penfield Ave\n"
        "Woodland Hills, CA 91364\n"
        "\n"
        "Mobile: (415) 555-0142\n"
        "Email: richard@piedpiper.com\n"
        "Website: https://www.piedpiper.com\n"
    )


@pytest.fixture
def resume_text() -> str:
    return (
        "Jane Smith\n"
        "Seattle, WA\n"
        "jane.smith@example.com | (206) 555-0142 | https://janesmith.dev\n"
        "\n"
        "Education\n"
        "Stanford University\n"
        "Bachelor of Science in Computer Science, 2020\n"
        "\n"
        "Professional Experience\n"
        "Google  Mountain View, CA\n"
        "Senior Software Engineer    Jan 2021 – Present\n"
        "  • Built large-scale data ingestion pipelines\n"
        "  • Designed gRPC microservices used by 200M+ users\n"
        "\n"
        "Technical Skills\n"
        "Python, Go, Kubernetes, Postgres, Kafka, AWS, Terraform\n"
    )


@pytest.fixture
def medical_report_text() -> str:
    return (
        "MERCY GENERAL HOSPITAL - PATIENT ENCOUNTER REPORT\n"
        "\n"
        "Patient Name: Sarah Jenkins\n"
        "Date of Birth: 05/14/1982\n"
        "Date of Visit: 10/12/2025\n"
        "Provider: Dr. Gregory House.\n"
        "\n"
        "vitals\n"
        "BP: 120/80\n"
        "HR: 72 bpm\n"
        "Temp: 98.6 F\n"
        "Weight: 145 lbs\n"
        "\n"
        "Diagnoses:\n"
        "1. Acute Migraine without aura\n"
        "2. Mild dehydration\n"
        "\n"
        "Medications:\n"
        "- Sumatriptan 50mg\n"
        "- Ibuprofen 400mg\n"
        "- Zofran 4mg\n"
    )


@pytest.fixture
def samples_dir() -> Path:
    return SAMPLES_DIR


@pytest.fixture
def data_samples_dir() -> Path:
    return DATA_SAMPLES_DIR

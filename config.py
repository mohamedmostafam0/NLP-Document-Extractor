import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base directory for resolving relative paths
BASE_DIR = Path(__file__).resolve().parent

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("docxtract")


class Settings:
    """Centralised application settings, sourced from environment variables."""

    # MinIO
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ROOT_USER", "docxtract")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_ROOT_PASSWORD", "docxtract123")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "documents")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'data' / 'docxtract.db'}",
    )

    # App
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))

    # Upload constraints
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20"))
    ALLOWED_EXTENSIONS: set = {"pdf", "docx", "doc", "txt"}

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


settings = Settings()

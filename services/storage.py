"""MinIO storage service for the document staging layer."""

import logging
from io import BytesIO

from minio import Minio
from minio.error import S3Error

from config import settings

logger = logging.getLogger("docxtract.storage")


class StorageService:
    """Thin wrapper around the MinIO Python client."""

    def __init__(self) -> None:
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._ensure_bucket()

    # ------------------------------------------------------------------
    # Bucket management
    # ------------------------------------------------------------------

    def _ensure_bucket(self) -> None:
        """Create the target bucket if it doesn't exist yet."""
        try:
            if not self.client.bucket_exists(settings.MINIO_BUCKET):
                self.client.make_bucket(settings.MINIO_BUCKET)
                logger.info("Created MinIO bucket: %s", settings.MINIO_BUCKET)
            else:
                logger.info("MinIO bucket already exists: %s", settings.MINIO_BUCKET)
        except S3Error as exc:
            logger.error("Failed to initialise MinIO bucket: %s", exc)
            raise

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def upload_file(
        self,
        file_data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload *file_data* to MinIO under *object_name*. Returns the full path."""
        data = BytesIO(file_data)
        self.client.put_object(
            settings.MINIO_BUCKET,
            object_name,
            data,
            length=len(file_data),
            content_type=content_type,
        )
        logger.info(
            "Uploaded %s (%d bytes) to %s/%s",
            object_name, len(file_data), settings.MINIO_BUCKET, object_name,
        )
        return f"{settings.MINIO_BUCKET}/{object_name}"

    def get_file(self, object_name: str) -> bytes:
        """Download the object from MinIO and return its raw bytes."""
        response = None
        try:
            response = self.client.get_object(settings.MINIO_BUCKET, object_name)
            return response.read()
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def delete_file(self, object_name: str) -> None:
        """Remove a single object from MinIO."""
        self.client.remove_object(settings.MINIO_BUCKET, object_name)
        logger.info("Deleted %s/%s", settings.MINIO_BUCKET, object_name)

    def file_exists(self, object_name: str) -> bool:
        """Check whether *object_name* exists in the bucket."""
        try:
            self.client.stat_object(settings.MINIO_BUCKET, object_name)
            return True
        except S3Error:
            return False


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------

_storage: StorageService | None = None


def get_storage() -> StorageService:
    """Return (and lazily create) the global StorageService instance."""
    global _storage
    if _storage is None:
        _storage = StorageService()
    return _storage

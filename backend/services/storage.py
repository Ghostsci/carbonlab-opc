"""MinIO / S3-compatible object storage for documents.

Supports local filesystem fallback for development.
"""

import io
import logging
import uuid
import mimetypes
from datetime import timedelta
from pathlib import Path
from typing import Optional

from backend.config import settings

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parent.parent / ".uploads"


# ── Interface ──

class StorageBackend:
    """Abstract storage backend interface."""

    def upload(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        raise NotImplementedError

    def download(self, object_name: str) -> Optional[bytes]:
        raise NotImplementedError

    def presigned_url(self, object_name: str, expires_hours: int = 1) -> str:
        raise NotImplementedError

    def delete(self, object_name: str) -> bool:
        raise NotImplementedError

    def exists(self, object_name: str) -> bool:
        raise NotImplementedError


# ── Local Filesystem Backend ──

class LocalStorage(StorageBackend):
    def upload(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        path = UPLOAD_DIR / object_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def download(self, object_name: str) -> Optional[bytes]:
        path = UPLOAD_DIR / object_name
        if path.exists():
            return path.read_bytes()
        return None

    def presigned_url(self, object_name: str, expires_hours: int = 1) -> str:
        return f"/files/{object_name}"

    def delete(self, object_name: str) -> bool:
        path = UPLOAD_DIR / object_name
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, object_name: str) -> bool:
        return (UPLOAD_DIR / object_name).exists()


# ── MinIO Backend ──

class MinioStorage(StorageBackend):
    def __init__(self):
        try:
            from minio import Minio
            self._client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            self._bucket = settings.minio_bucket
            self._ensure_bucket()
            self._enabled = True
        except Exception as e:
            if settings.app_env != "development":
                logger.exception(
                    "MinIO init failed; refusing local fallback in %s",
                    settings.app_env,
                )
                raise RuntimeError("MinIO storage initialization failed") from e
            logger.warning("MinIO init failed, falling back to local storage: %s", e)
            self._enabled = False
            self._fallback = LocalStorage()

    def _ensure_bucket(self):
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("Created MinIO bucket: %s", self._bucket)

    def upload(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        if not self._enabled:
            return self._fallback.upload(object_name, data, content_type)
        self._client.put_object(
            bucket_name=self._bucket,
            object_name=object_name,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return object_name

    def download(self, object_name: str) -> Optional[bytes]:
        if not self._enabled:
            return self._fallback.download(object_name)
        try:
            resp = self._client.get_object(bucket_name=self._bucket, object_name=object_name)
            return resp.read()
        except Exception:
            return None

    def presigned_url(self, object_name: str, expires_hours: int = 1) -> str:
        if not self._enabled:
            return self._fallback.presigned_url(object_name, expires_hours)
        try:
            return self._client.presigned_get_object(
                bucket_name=self._bucket,
                object_name=object_name,
                expires=timedelta(hours=expires_hours),
            )
        except Exception:
            return self._fallback.presigned_url(object_name, expires_hours)

    def delete(self, object_name: str) -> bool:
        if not self._enabled:
            return self._fallback.delete(object_name)
        try:
            self._client.remove_object(bucket_name=self._bucket, object_name=object_name)
            return True
        except Exception:
            return False

    def exists(self, object_name: str) -> bool:
        if not self._enabled:
            return self._fallback.exists(object_name)
        try:
            self._client.stat_object(bucket_name=self._bucket, object_name=object_name)
            return True
        except Exception:
            return False

    def list_objects(self, prefix: str = "") -> list[str]:
        if not self._enabled:
            return []
        objects = self._client.list_objects(bucket_name=self._bucket, prefix=prefix)
        return [obj.object_name for obj in objects]


# ── Singleton ──

_storage: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        if settings.storage_backend == "minio":
            _storage = MinioStorage()
        else:
            _storage = LocalStorage()
    return _storage


# ── Convenience helpers ──

def generate_object_name(filename: str, file_id: Optional[str] = None) -> str:
    """Generate a safe object name: {year}/{month}/{file_id}_{safe_name}"""
    from datetime import datetime, timezone
    fid = file_id or str(uuid.uuid4())
    ext = Path(filename).suffix.lower()
    safe_name = Path(filename).stem[:80]
    safe_name = ''.join(c for c in safe_name if c.isalnum() or c in '._-')
    now = datetime.now(timezone.utc)
    return f"{now.year}/{now.month:02d}/{fid}_{safe_name}{ext}"


def detect_content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
    }
    return mapping.get(ext, "application/octet-stream")

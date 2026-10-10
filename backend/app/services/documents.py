"""Document intake: validation, storage and persistence."""

from pathlib import PurePath

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Document, DocumentStatus, new_id
from app.llm.truth import sha256_bytes
from app.ocr.base import SUPPORTED_TYPES
from app.services.storage import Storage

MAGIC: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF",),
    "image/png": (b"\x89PNG",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/tiff": (b"II*\x00", b"MM\x00*"),
    "image/webp": (b"RIFF",),
}
EXTENSIONS = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}


def sniff_content_type(filename: str, declared: str | None, data: bytes) -> str:
    """Trust the bytes, not the client: the magic number must match a supported type."""
    for content_type, prefixes in MAGIC.items():
        if data.startswith(prefixes):
            return content_type
    hint = (
        declared
        if declared in SUPPORTED_TYPES
        else EXTENSIONS.get(PurePath(filename).suffix.lower())
    )
    raise AppError(
        415,
        f"Unsupported file type{f' ({hint})' if hint else ''}: "
        "upload a PDF, PNG, JPEG, TIFF or WebP",
        code="unsupported-media-type",
    )


def create_document(
    session: Session,
    storage: Storage,
    *,
    filename: str,
    declared_type: str | None,
    data: bytes,
    max_bytes: int,
) -> Document:
    if not data:
        raise AppError(422, "The uploaded file is empty", code="empty-file")
    if len(data) > max_bytes:
        raise AppError(
            413,
            f"File is {len(data) / 1_048_576:.1f} MB; the limit is {max_bytes / 1_048_576:.0f} MB",
            code="file-too-large",
        )
    content_type = sniff_content_type(filename, declared_type, data)
    safe_name = PurePath(filename or "upload").name[:255] or "upload"
    doc_id = new_id()
    key = f"{doc_id[:2]}/{doc_id}{PurePath(safe_name).suffix.lower()[:10]}"
    storage.save(key, data)
    doc = Document(
        id=doc_id,
        filename=safe_name,
        content_type=content_type,
        size_bytes=len(data),
        sha256=sha256_bytes(data),
        storage_key=key,
        status=DocumentStatus.QUEUED,
    )
    session.add(doc)
    session.commit()
    return doc

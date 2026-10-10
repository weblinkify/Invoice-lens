"""ORM models. Tables: documents, extractions, field_corrections, vendors,
webhook_endpoints, webhook_deliveries, app_settings."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JsonType, utcnow


def new_id() -> str:
    return str(uuid.uuid4())


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    EXTRACTED = "extracted"
    APPROVED = "approved"
    FAILED = "failed"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    vat_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    documents: Mapped[list["Document"]] = relationship(back_populates="vendor")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.QUEUED)
    error: Mapped[str | None] = mapped_column(Text)
    ocr_method: Mapped[str | None] = mapped_column(String(20))
    page_count: Mapped[int | None]
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    approved_at: Mapped[datetime | None]

    vendor: Mapped[Vendor | None] = relationship(back_populates="documents")
    extraction: Mapped["Extraction | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), unique=True
    )
    provider: Mapped[str] = mapped_column(String(30))
    raw: Mapped[dict[str, Any]] = mapped_column(JsonType)
    overrides: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    data: Mapped[dict[str, Any]] = mapped_column(JsonType)
    needs_review: Mapped[bool] = mapped_column(default=False, index=True)
    min_confidence: Mapped[float] = mapped_column(default=0.0)
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    invoice_number: Mapped[str | None] = mapped_column(String(100))
    total: Mapped[float | None]
    currency: Mapped[str | None] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    document: Mapped[Document] = relationship(back_populates="extraction")


class FieldCorrection(Base):
    __tablename__ = "field_corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), index=True)
    field_path: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[Any] = mapped_column(JsonType, nullable=True)
    new_value: Mapped[Any] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2048))
    secret: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType)
    status: Mapped[str] = mapped_column(String(20), default=DeliveryStatus.PENDING)
    attempts: Mapped[int] = mapped_column(default=0)
    last_status_code: Mapped[int | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    delivered_at: Mapped[datetime | None]

    endpoint: Mapped[WebhookEndpoint] = relationship(back_populates="deliveries")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JsonType)

"""Request/response DTOs for the HTTP API (the source of the generated TS types)."""

from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.domain.schema import InvoiceExtraction


class DocumentOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )

    id: str
    filename: str
    content_type: str
    size_bytes: int
    status: Literal["queued", "processing", "needs_review", "extracted", "approved", "failed"]
    error: str | None
    ocr_method: str | None
    page_count: int | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    vendor_name: str | None = None
    invoice_number: str | None = None
    total: float | None = None
    currency: str | None = None
    needs_review: bool | None = None
    min_confidence: float | None = None


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class UploadAccepted(BaseModel):
    id: str
    status: str
    status_url: str


class ExtractionOut(BaseModel):
    document_id: str
    provider: str
    threshold: float
    data: InvoiceExtraction
    corrected_fields: list[str]
    updated_at: datetime


class FieldCorrectionIn(BaseModel):
    field: str = Field(examples=["invoice_number", "line_items.0.quantity"])
    value: str | float | None


class CorrectionRequest(BaseModel):
    corrections: list[FieldCorrectionIn] = Field(min_length=1)


class SettingsOut(BaseModel):
    confidence_threshold: float
    llm_provider: str
    demo_mode: bool
    max_upload_bytes: int


class SettingsUpdate(BaseModel):
    confidence_threshold: float = Field(ge=0.0, le=1.0)


class WebhookEndpointIn(BaseModel):
    url: AnyHttpUrl
    secret: str = Field(min_length=8, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    active: bool = True


class WebhookEndpointUpdate(BaseModel):
    url: AnyHttpUrl | None = None
    secret: str | None = Field(default=None, min_length=8, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    active: bool | None = None


class WebhookEndpointOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )

    id: int
    url: str
    description: str | None
    active: bool
    created_at: datetime
    secret_hint: str


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )

    id: int
    endpoint_id: int
    document_id: str | None
    event: str
    status: Literal["pending", "succeeded", "failed"]
    attempts: int
    last_status_code: int | None
    last_error: str | None
    created_at: datetime
    delivered_at: datetime | None


class SampleOut(BaseModel):
    name: str
    template: str | None
    edge_cases: list[str]
    size_bytes: int


class HealthOut(BaseModel):
    status: Literal["ok"]
    provider: str
    version: str


class ProblemFieldError(BaseModel):
    loc: list[str]
    msg: str
    type: str


class Problem(BaseModel):
    """RFC 7807 error envelope returned as ``application/problem+json``."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
    errors: list[ProblemFieldError] | None = None


PROBLEM_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {"model": Problem, "description": "Problem details (RFC 7807)"}
    for status in ("4XX", 422, "5XX")
}

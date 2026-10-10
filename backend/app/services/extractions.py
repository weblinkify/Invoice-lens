"""Materialize an extraction: provider output + reviewer overrides → scored result."""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Document, DocumentStatus, Extraction, FieldCorrection
from app.domain.confidence import score
from app.domain.schema import AnyField, DateField, InvoiceExtraction, NumberField, field_kind

JsonValue = str | float | None


def to_json_value(fld: AnyField) -> JsonValue:
    value = fld.value
    return value.isoformat() if isinstance(value, date) else value


def coerce(path: str, value: JsonValue) -> JsonValue:
    """Validate a reviewer-supplied value for the field's type; '' means null."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    kind = field_kind(path)
    try:
        if kind is NumberField:
            return round(float(value), 4)
        if kind is DateField:
            return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError as exc:
        raise AppError(
            422,
            f"{path}: {value!r} is not a valid {kind.__name__[:-5].lower()}",
            code="invalid-field-value",
        ) from exc
    return str(value).strip()


def materialize(
    raw: dict[str, Any], overrides: dict[str, Any], threshold: float
) -> InvoiceExtraction:
    inv = InvoiceExtraction.model_validate(raw)
    for path, value in overrides.items():
        try:
            fld = inv.get_field(path)
        except KeyError:
            continue
        fld.value = value
        fld.confidence = 1.0
    inv = InvoiceExtraction.model_validate(inv.model_dump())  # re-validate coerced values
    scored = score(inv, threshold)
    for path in overrides:
        try:
            scored.get_field(path).confidence = 1.0  # human-verified
        except KeyError:
            continue
    scored.needs_review = bool(scored.validation_issues) or any(
        f.confidence < threshold for _, f in scored.iter_fields()
    )
    return scored


def store(extraction: Extraction, inv: InvoiceExtraction) -> None:
    extraction.data = inv.model_dump(mode="json")
    extraction.needs_review = inv.needs_review
    extraction.min_confidence = inv.min_confidence()
    extraction.vendor_name = inv.vendor_name.value
    extraction.invoice_number = inv.invoice_number.value
    extraction.total = inv.total.value
    currency = inv.currency.value
    extraction.currency = currency[:3] if currency else None


def apply_corrections(
    session: Session,
    document: Document,
    corrections: list[tuple[str, JsonValue]],
    threshold: float,
) -> InvoiceExtraction:
    extraction = document.extraction
    if extraction is None:
        raise AppError(409, "Document has no extraction yet", code="not-extracted")
    current = InvoiceExtraction.model_validate(extraction.data)
    overrides = dict(extraction.overrides or {})
    for path, raw_value in corrections:
        try:
            old = to_json_value(current.get_field(path))
        except KeyError as exc:
            raise AppError(422, f"Unknown field {path}", code="unknown-field") from exc
        new = coerce(path, raw_value)
        overrides[path] = new
        if old != new:
            session.add(
                FieldCorrection(
                    document_id=document.id,
                    vendor_id=document.vendor_id,
                    field_path=path,
                    old_value=old,
                    new_value=new,
                )
            )
    extraction.overrides = overrides
    inv = materialize(extraction.raw, overrides, threshold)
    store(extraction, inv)
    return inv


def rescore_all(session: Session, threshold: float) -> int:
    """Re-apply a new threshold to every extraction and sync non-final document statuses."""
    count = 0
    for extraction in session.scalars(select(Extraction)).all():
        inv = materialize(extraction.raw, extraction.overrides or {}, threshold)
        store(extraction, inv)
        doc = extraction.document
        if doc.status in (DocumentStatus.NEEDS_REVIEW, DocumentStatus.EXTRACTED):
            doc.status = (
                DocumentStatus.NEEDS_REVIEW if inv.needs_review else DocumentStatus.EXTRACTED
            )
        count += 1
    return count

"""Vendor matching and few-shot example lookup."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FieldCorrection, Vendor
from app.domain.fewshot import Correction, FewShotExample, build_fewshot_examples
from app.domain.schema import InvoiceExtraction
from app.domain.validators import normalize_vat_id


def _squash(text: str) -> str:
    return re.sub(r"[\s.\-]", "", text).upper()


def detect_vendor(session: Session, ocr_text: str) -> Vendor | None:
    """Find a known vendor mentioned in the OCR text (VAT ID first, then exact name)."""
    if not ocr_text.strip():
        return None
    squashed = _squash(ocr_text)
    vendors = session.scalars(select(Vendor)).all()
    for vendor in vendors:
        if vendor.vat_id and vendor.vat_id in squashed:
            return vendor
    lowered = ocr_text.lower()
    for vendor in vendors:
        if vendor.name and vendor.name.lower() in lowered:
            return vendor
    return None


def upsert_vendor(session: Session, inv: InvoiceExtraction) -> Vendor | None:
    name = inv.vendor_name.value
    vat_id = normalize_vat_id(inv.vendor_vat_id.value) if inv.vendor_vat_id.value else None
    if not name and not vat_id:
        return None
    vendor = None
    if vat_id:
        vendor = session.scalar(select(Vendor).where(Vendor.vat_id == vat_id))
    if vendor is None and name:
        vendor = session.scalar(select(Vendor).where(Vendor.name == name))
    if vendor is None:
        vendor = Vendor(name=name or vat_id or "Unknown vendor", vat_id=vat_id)
        session.add(vendor)
        session.flush()
    elif vat_id and vendor.vat_id is None:
        vendor.vat_id = vat_id
    return vendor


def examples_for_vendor(
    session: Session, vendor_id: int, exclude_document: str | None, limit: int
) -> list[FewShotExample]:
    rows = session.scalars(
        select(FieldCorrection)
        .where(FieldCorrection.vendor_id == vendor_id)
        .order_by(FieldCorrection.created_at.desc())
        .limit(200)
    ).all()
    corrections = [
        Correction(r.document_id, r.field_path, r.old_value, r.new_value, r.created_at)
        for r in rows
        if r.document_id != exclude_document
    ]
    return build_fewshot_examples(corrections, max_examples=limit)

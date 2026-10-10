"""Prompt + structured-output model shared by the real LLM providers."""

from datetime import date

from pydantic import BaseModel, Field

from app.domain.fewshot import render_fewshot_prompt
from app.domain.schema import (
    DateField,
    InvoiceExtraction,
    LineItem,
    NumberField,
    StringField,
)
from app.llm.base import ExtractionRequest

SYSTEM_PROMPT = """\
You extract structured data from supplier invoices for an accounts-payable team.

Rules:
- Return every field. Use null when the invoice does not contain a value; never invent one.
- Dates as YYYY-MM-DD. Amounts as plain numbers with a dot decimal separator (1 234,56 -> 1234.56).
- currency is the ISO 4217 code (EUR, SEK, USD, ...). vat_rate is a percentage (25.5, not 0.255).
- IBAN and VAT IDs without spaces, upper case.
- confidence (0..1) is how sure you are that the value is exactly right, including a null.
  Use < 0.5 when you are guessing, 0.5-0.8 when the text is ambiguous or hard to read,
  and > 0.9 only when the value is printed clearly and labelled.
- source_page is the 1-based page where you read the value.
"""


class LLMString(BaseModel):
    value: str | None
    confidence: float
    source_page: int | None


class LLMNumber(BaseModel):
    value: float | None
    confidence: float
    source_page: int | None


class LLMDate(BaseModel):
    value: str | None = Field(description="YYYY-MM-DD")
    confidence: float
    source_page: int | None


class LLMLineItem(BaseModel):
    description: LLMString
    quantity: LLMNumber
    unit_price: LLMNumber
    vat_rate: LLMNumber
    line_total: LLMNumber


class LLMInvoice(BaseModel):
    """What the model returns. Deliberately simple: no bboxes (we locate those from OCR)."""

    vendor_name: LLMString
    vendor_vat_id: LLMString
    invoice_number: LLMString
    invoice_date: LLMDate
    due_date: LLMDate
    currency: LLMString
    line_items: list[LLMLineItem]
    subtotal: LLMNumber
    vat_total: LLMNumber
    total: LLMNumber
    iban: LLMString
    payment_reference: LLMString


def build_user_prompt(request: ExtractionRequest) -> str:
    parts: list[str] = []
    fewshot = render_fewshot_prompt(request.examples)
    if fewshot:
        parts.append(fewshot)
    if request.ocr.pages:
        pages = "\n\n".join(f"--- page {p.number} ---\n{p.text}" for p in request.ocr.pages)
        parts.append(f"OCR text of the invoice (may contain recognition errors):\n{pages}")
    parts.append("Extract the invoice fields.")
    return "\n\n".join(parts)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def _page(page: int | None) -> int | None:
    return page if page is not None and page >= 1 else None


def _s(f: LLMString) -> StringField:
    value = f.value.strip() if f.value else None
    return StringField(
        value=value or None, confidence=_clamp(f.confidence), source_page=_page(f.source_page)
    )


def _n(f: LLMNumber) -> NumberField:
    return NumberField(
        value=f.value, confidence=_clamp(f.confidence), source_page=_page(f.source_page)
    )


def _d(f: LLMDate) -> DateField:
    try:
        value = date.fromisoformat(f.value) if f.value else None
    except ValueError:
        return DateField(value=None, confidence=0.0, source_page=_page(f.source_page))
    return DateField(value=value, confidence=_clamp(f.confidence), source_page=_page(f.source_page))


def to_extraction(out: LLMInvoice) -> InvoiceExtraction:
    return InvoiceExtraction(
        vendor_name=_s(out.vendor_name),
        vendor_vat_id=_s(out.vendor_vat_id),
        invoice_number=_s(out.invoice_number),
        invoice_date=_d(out.invoice_date),
        due_date=_d(out.due_date),
        currency=_s(out.currency),
        line_items=[
            LineItem(
                description=_s(item.description),
                quantity=_n(item.quantity),
                unit_price=_n(item.unit_price),
                vat_rate=_n(item.vat_rate),
                line_total=_n(item.line_total),
            )
            for item in out.line_items
        ],
        subtotal=_n(out.subtotal),
        vat_total=_n(out.vat_total),
        total=_n(out.total),
        iban=_s(out.iban),
        payment_reference=_s(out.payment_reference),
    )

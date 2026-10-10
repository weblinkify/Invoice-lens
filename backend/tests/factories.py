"""Builders for valid domain objects used across tests."""

from datetime import date

from app.domain.schema import (
    DateField,
    InvoiceExtraction,
    LineItem,
    NumberField,
    StringField,
)


def s(value: str | None, confidence: float = 0.95) -> StringField:
    return StringField(value=value, confidence=confidence, source_page=1)


def n(value: float | None, confidence: float = 0.95) -> NumberField:
    return NumberField(value=value, confidence=confidence, source_page=1)


def d(value: date | None, confidence: float = 0.95) -> DateField:
    return DateField(value=value, confidence=confidence, source_page=1)


def line(desc: str, qty: float, price: float, vat: float = 24.0) -> LineItem:
    return LineItem(
        description=s(desc),
        quantity=n(qty),
        unit_price=n(price),
        vat_rate=n(vat),
        line_total=n(round(qty * price, 2)),
    )


def valid_invoice() -> InvoiceExtraction:
    """A consistent invoice: 2x100 + 3x50 = 350, VAT 24% = 84, total 434."""
    return InvoiceExtraction(
        vendor_name=s("Nordic Widgets Oy"),
        vendor_vat_id=s("FI12345671"),
        invoice_number=s("INV-2026-0001"),
        invoice_date=d(date(2026, 3, 1)),
        due_date=d(date(2026, 3, 31)),
        currency=s("EUR"),
        line_items=[line("Widget", 2, 100.0), line("Gadget", 3, 50.0)],
        subtotal=n(350.0),
        vat_total=n(84.0),
        total=n(434.0),
        iban=s("FI2112345600000785"),
        payment_reference=s("RF18539007547034"),
    )

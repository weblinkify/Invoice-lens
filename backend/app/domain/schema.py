"""Invoice extraction schema.

Every extracted value is wrapped in a field object carrying ``confidence`` (0..1), the
page it came from and an optional normalized bounding box ``[x0, y0, x1, y1]`` (0..1,
top-left origin) so the UI can highlight it on the document.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
BBox = Annotated[list[float], Field(min_length=4, max_length=4)]

HEADER_FIELDS: tuple[str, ...] = (
    "vendor_name",
    "vendor_vat_id",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal",
    "vat_total",
    "total",
    "iban",
    "payment_reference",
)
LINE_ITEM_FIELDS: tuple[str, ...] = (
    "description",
    "quantity",
    "unit_price",
    "vat_rate",
    "line_total",
)
DATE_FIELDS = frozenset({"invoice_date", "due_date"})
NUMBER_FIELDS = frozenset(
    {"subtotal", "vat_total", "total", "quantity", "unit_price", "vat_rate", "line_total"}
)
REQUIRED_FIELDS = frozenset({"vendor_name", "invoice_number", "invoice_date", "currency", "total"})


class _FieldBase(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    confidence: Confidence = 0.0
    source_page: int | None = Field(default=None, ge=1)
    bbox: BBox | None = None


class StringField(_FieldBase):
    value: str | None = None


class NumberField(_FieldBase):
    value: float | None = None


class DateField(_FieldBase):
    value: date | None = None


AnyField = StringField | NumberField | DateField


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    description: StringField = Field(default_factory=StringField)
    quantity: NumberField = Field(default_factory=NumberField)
    unit_price: NumberField = Field(default_factory=NumberField)
    vat_rate: NumberField = Field(default_factory=NumberField)
    line_total: NumberField = Field(default_factory=NumberField)


class ValidationIssue(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    code: str
    message: str
    fields: list[str] = Field(default_factory=list)


class InvoiceExtraction(BaseModel):
    """Strict extraction result. Field paths look like ``total`` or ``line_items.2.line_total``."""

    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)

    vendor_name: StringField = Field(default_factory=StringField)
    vendor_vat_id: StringField = Field(default_factory=StringField)
    invoice_number: StringField = Field(default_factory=StringField)
    invoice_date: DateField = Field(default_factory=DateField)
    due_date: DateField = Field(default_factory=DateField)
    currency: StringField = Field(default_factory=StringField)
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: NumberField = Field(default_factory=NumberField)
    vat_total: NumberField = Field(default_factory=NumberField)
    total: NumberField = Field(default_factory=NumberField)
    iban: StringField = Field(default_factory=StringField)
    payment_reference: StringField = Field(default_factory=StringField)

    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    needs_review: bool = False

    def iter_fields(self) -> Iterator[tuple[str, AnyField]]:
        """Yield ``(path, field)`` for every leaf field, line items included."""
        for name in HEADER_FIELDS:
            yield name, getattr(self, name)
        for idx, item in enumerate(self.line_items):
            for name in LINE_ITEM_FIELDS:
                yield f"line_items.{idx}.{name}", getattr(item, name)

    def get_field(self, path: str) -> AnyField:
        parts = path.split(".")
        if len(parts) == 1 and parts[0] in HEADER_FIELDS:
            field: AnyField = getattr(self, parts[0])
            return field
        if len(parts) == 3 and parts[0] == "line_items" and parts[2] in LINE_ITEM_FIELDS:
            idx = int(parts[1])
            if 0 <= idx < len(self.line_items):
                item_field: AnyField = getattr(self.line_items[idx], parts[2])
                return item_field
        raise KeyError(path)

    def min_confidence(self) -> float:
        return min((f.confidence for _, f in self.iter_fields()), default=0.0)

    def plain_values(self) -> dict[str, Any]:
        """Flatten to plain JSON-ready values (used by exports and webhooks)."""
        data: dict[str, Any] = {
            name: _jsonable(getattr(self, name).value) for name in HEADER_FIELDS
        }
        data["line_items"] = [
            {name: _jsonable(getattr(item, name).value) for name in LINE_ITEM_FIELDS}
            for item in self.line_items
        ]
        return data


def _jsonable(value: object) -> object:
    return value.isoformat() if isinstance(value, date) else value


def field_kind(path: str) -> type[AnyField]:
    leaf = path.rsplit(".", 1)[-1]
    if leaf in DATE_FIELDS:
        return DateField
    if leaf in NUMBER_FIELDS:
        return NumberField
    return StringField

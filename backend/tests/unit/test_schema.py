from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.schema import (
    DateField,
    InvoiceExtraction,
    NumberField,
    StringField,
    field_kind,
)
from tests.factories import valid_invoice


def test_iter_fields_includes_line_items() -> None:
    paths = [path for path, _ in valid_invoice().iter_fields()]
    assert paths[0] == "vendor_name"
    assert "line_items.1.line_total" in paths
    assert len(paths) == 11 + 2 * 5


def test_get_field() -> None:
    inv = valid_invoice()
    assert inv.get_field("total").value == 434.0
    assert inv.get_field("line_items.0.description").value == "Widget"
    for bad in ["nope", "line_items.9.quantity", "line_items.0.nope", "a.b"]:
        with pytest.raises(KeyError):
            inv.get_field(bad)


def test_plain_values_serializes_dates() -> None:
    plain = valid_invoice().plain_values()
    assert plain["invoice_date"] == "2026-03-01"
    assert plain["line_items"][0] == {
        "description": "Widget",
        "quantity": 2,
        "unit_price": 100.0,
        "vat_rate": 24.0,
        "line_total": 200.0,
    }


def test_min_confidence() -> None:
    inv = valid_invoice()
    inv.iban.confidence = 0.3
    assert inv.min_confidence() == 0.3


def test_strict_schema_rejects_bad_values() -> None:
    with pytest.raises(ValidationError):
        StringField(value="x", confidence=1.5)
    with pytest.raises(ValidationError):
        NumberField(value=1, confidence=0.5, bbox=[0, 0, 1])
    with pytest.raises(ValidationError):
        InvoiceExtraction.model_validate({"unknown": 1})


def test_json_roundtrip() -> None:
    inv = valid_invoice()
    again = InvoiceExtraction.model_validate_json(inv.model_dump_json())
    assert again == inv
    assert again.invoice_date.value == date(2026, 3, 1)


def test_field_kind() -> None:
    assert field_kind("due_date") is DateField
    assert field_kind("line_items.0.quantity") is NumberField
    assert field_kind("iban") is StringField

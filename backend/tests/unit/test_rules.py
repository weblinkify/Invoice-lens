from datetime import date

import pytest

from app.domain.rules import TOLERANCE, run_rules
from app.domain.schema import InvoiceExtraction
from tests.factories import d, n, s, valid_invoice


def codes(inv: InvoiceExtraction) -> list[str]:
    return [issue.code for issue in run_rules(inv)]


def test_valid_invoice_has_no_issues() -> None:
    assert run_rules(valid_invoice()) == []


@pytest.mark.parametrize(
    ("subtotal", "expect_issue"),
    [(350.0, False), (350.01, False), (349.99, False), (350.02, True), (300.0, True)],
)
def test_line_items_sum(subtotal: float, expect_issue: bool) -> None:
    inv = valid_invoice()
    inv.subtotal = n(subtotal)
    inv.total = n(subtotal + 84.0)
    assert ("line_items_sum_mismatch" in codes(inv)) is expect_issue


def test_line_items_sum_skipped_when_values_missing() -> None:
    inv = valid_invoice()
    inv.line_items[0].line_total = n(None)
    assert "line_items_sum_mismatch" not in codes(inv)


@pytest.mark.parametrize(
    ("total", "expect_issue"),
    [(434.0, False), (434.0 + TOLERANCE, False), (434.02, True), (500.0, True)],
)
def test_totals(total: float, expect_issue: bool) -> None:
    inv = valid_invoice()
    inv.total = n(total)
    issues = [i for i in run_rules(inv) if i.code == "totals_mismatch"]
    assert bool(issues) is expect_issue
    if issues:
        assert issues[0].fields == ["subtotal", "vat_total", "total"]


def test_totals_skipped_when_vat_missing() -> None:
    inv = valid_invoice()
    inv.vat_total = n(None)
    assert "totals_mismatch" not in codes(inv)


@pytest.mark.parametrize(
    ("due", "expect_issue"),
    [
        (date(2026, 3, 31), False),
        (date(2026, 3, 1), False),
        (date(2026, 2, 28), True),
        (None, False),
    ],
)
def test_due_date(due: date | None, expect_issue: bool) -> None:
    inv = valid_invoice()
    inv.due_date = d(due)
    assert ("due_before_invoice_date" in codes(inv)) is expect_issue


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("iban", "FI2112345600000786", "invalid_iban"),
        ("vendor_vat_id", "FI12345672", "invalid_vat_id"),
        ("currency", "ABC", "invalid_currency"),
    ],
)
def test_identifier_rules(field: str, value: str, code: str) -> None:
    inv = valid_invoice()
    setattr(inv, field, s(value))
    assert code in codes(inv)


@pytest.mark.parametrize("field", ["vendor_name", "invoice_number", "currency"])
def test_required_fields(field: str) -> None:
    inv = valid_invoice()
    setattr(inv, field, s(None))
    issues = [i for i in run_rules(inv) if i.code == "required_missing"]
    assert [i.fields for i in issues] == [[field]]


def test_line_item_arithmetic() -> None:
    inv = valid_invoice()
    inv.line_items[1].quantity = n(4)
    issue = next(i for i in run_rules(inv) if i.code == "line_item_arithmetic")
    assert issue.fields[0] == "line_items.1.quantity"

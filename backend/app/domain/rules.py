"""Business validation rules. Each rule is a pure function returning zero or more issues."""

from collections.abc import Callable

from app.domain.schema import REQUIRED_FIELDS, InvoiceExtraction, ValidationIssue
from app.domain.validators import is_valid_currency, is_valid_iban, is_valid_vat_id

TOLERANCE = 0.01

Rule = Callable[[InvoiceExtraction], list[ValidationIssue]]


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE + 1e-9


def rule_required_fields(inv: InvoiceExtraction) -> list[ValidationIssue]:
    missing = sorted(name for name in REQUIRED_FIELDS if inv.get_field(name).value in (None, ""))
    return [
        ValidationIssue(code="required_missing", message=f"{name} is required", fields=[name])
        for name in missing
    ]


def rule_line_items_sum(inv: InvoiceExtraction) -> list[ValidationIssue]:
    subtotal = inv.subtotal.value
    totals = [item.line_total.value for item in inv.line_items]
    if subtotal is None or not totals or any(t is None for t in totals):
        return []
    total_sum = round(sum(t for t in totals if t is not None), 2)
    if _close(total_sum, subtotal):
        return []
    return [
        ValidationIssue(
            code="line_items_sum_mismatch",
            message=f"Line totals sum to {total_sum:.2f} but subtotal is {subtotal:.2f}",
            fields=["subtotal", *(f"line_items.{i}.line_total" for i in range(len(totals)))],
        )
    ]


def rule_totals(inv: InvoiceExtraction) -> list[ValidationIssue]:
    sub, vat, total = inv.subtotal.value, inv.vat_total.value, inv.total.value
    if sub is None or vat is None or total is None or _close(sub + vat, total):
        return []
    return [
        ValidationIssue(
            code="totals_mismatch",
            message=(
                f"Subtotal {sub:.2f} + VAT {vat:.2f} = {sub + vat:.2f}, but total is {total:.2f}"
            ),
            fields=["subtotal", "vat_total", "total"],
        )
    ]


def rule_line_item_arithmetic(inv: InvoiceExtraction) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for idx, item in enumerate(inv.line_items):
        qty, price, line_total = item.quantity.value, item.unit_price.value, item.line_total.value
        if qty is None or price is None or line_total is None:
            continue
        if not _close(round(qty * price, 2), line_total):
            issues.append(
                ValidationIssue(
                    code="line_item_arithmetic",
                    message=f"Line {idx + 1}: {qty:g} x {price:.2f} != {line_total:.2f}",
                    fields=[
                        f"line_items.{idx}.quantity",
                        f"line_items.{idx}.unit_price",
                        f"line_items.{idx}.line_total",
                    ],
                )
            )
    return issues


def rule_due_date(inv: InvoiceExtraction) -> list[ValidationIssue]:
    issued, due = inv.invoice_date.value, inv.due_date.value
    if issued is None or due is None or due >= issued:
        return []
    return [
        ValidationIssue(
            code="due_before_invoice_date",
            message=f"Due date {due.isoformat()} is before invoice date {issued.isoformat()}",
            fields=["invoice_date", "due_date"],
        )
    ]


def rule_iban(inv: InvoiceExtraction) -> list[ValidationIssue]:
    value = inv.iban.value
    if not value or is_valid_iban(value):
        return []
    return [
        ValidationIssue(code="invalid_iban", message="IBAN checksum is invalid", fields=["iban"])
    ]


def rule_vat_id(inv: InvoiceExtraction) -> list[ValidationIssue]:
    value = inv.vendor_vat_id.value
    if not value or is_valid_vat_id(value):
        return []
    return [
        ValidationIssue(
            code="invalid_vat_id",
            message=f"VAT ID {value} fails the format/checksum check",
            fields=["vendor_vat_id"],
        )
    ]


def rule_currency(inv: InvoiceExtraction) -> list[ValidationIssue]:
    value = inv.currency.value
    if not value or is_valid_currency(value):
        return []
    return [
        ValidationIssue(
            code="invalid_currency",
            message=f"{value} is not a supported ISO 4217 code",
            fields=["currency"],
        )
    ]


DEFAULT_RULES: tuple[Rule, ...] = (
    rule_required_fields,
    rule_line_items_sum,
    rule_totals,
    rule_line_item_arithmetic,
    rule_due_date,
    rule_iban,
    rule_vat_id,
    rule_currency,
)


def run_rules(
    inv: InvoiceExtraction, rules: tuple[Rule, ...] = DEFAULT_RULES
) -> list[ValidationIssue]:
    return [issue for rule in rules for issue in rule(inv)]

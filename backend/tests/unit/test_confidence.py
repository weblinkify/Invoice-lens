import pytest

from app.domain.confidence import confidence_band, needs_review, score
from app.domain.schema import InvoiceExtraction, StringField
from tests.factories import n, s, valid_invoice


@pytest.mark.parametrize(
    ("value", "threshold", "band"),
    [(0.95, 0.8, "high"), (0.8, 0.8, "high"), (0.79, 0.8, "medium"), (0.5, 0.8, "medium"),
     (0.49, 0.8, "low"), (0.0, 0.8, "low"), (0.6, 0.6, "high")],
)  # fmt: skip
def test_confidence_band(value: float, threshold: float, band: str) -> None:
    assert confidence_band(value, threshold) == band


def test_score_clean_invoice_does_not_need_review() -> None:
    result = score(valid_invoice(), threshold=0.8)
    assert result.validation_issues == []
    assert result.needs_review is False
    assert result.total.confidence == 0.95


def test_score_penalizes_fields_in_failed_rules() -> None:
    inv = valid_invoice()
    inv.total = n(999.0)
    result = score(inv, threshold=0.8, penalty=0.5)
    assert [i.code for i in result.validation_issues] == ["totals_mismatch"]
    assert result.total.confidence == pytest.approx(0.475)
    assert result.subtotal.confidence == pytest.approx(0.475)
    assert result.vendor_name.confidence == 0.95
    assert result.needs_review is True
    # the input is not mutated
    assert inv.total.confidence == 0.95


def test_missing_required_field_gets_zero_confidence() -> None:
    inv = valid_invoice()
    inv.invoice_number = StringField(value=None, confidence=0.9)
    result = score(inv, threshold=0.8)
    assert result.invoice_number.confidence == 0.0
    assert result.needs_review


def test_low_confidence_field_alone_triggers_review() -> None:
    inv = valid_invoice()
    inv.iban = s("FI2112345600000785", confidence=0.6)
    result = score(inv, threshold=0.8)
    assert result.validation_issues == []
    assert result.needs_review
    assert not score(inv, threshold=0.5).needs_review


def test_needs_review_with_issues() -> None:
    inv = InvoiceExtraction()
    assert needs_review(inv, 0.0) is False
    scored = score(inv, threshold=0.0)
    assert scored.needs_review  # required fields missing

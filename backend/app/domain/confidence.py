"""Confidence scoring: combine provider confidence with validation outcomes."""

from typing import Literal

from app.domain.rules import DEFAULT_RULES, Rule, run_rules
from app.domain.schema import REQUIRED_FIELDS, InvoiceExtraction

DEFAULT_PENALTY = 0.5
LOW_BAND_CEILING = 0.5

Band = Literal["high", "medium", "low"]


def confidence_band(confidence: float, threshold: float) -> Band:
    """Green at/above the review threshold, amber down to 0.5, red below."""
    if confidence >= threshold:
        return "high"
    if confidence >= LOW_BAND_CEILING:
        return "medium"
    return "low"


def needs_review(inv: InvoiceExtraction, threshold: float) -> bool:
    if inv.validation_issues:
        return True
    return any(field.confidence < threshold for _, field in inv.iter_fields())


def score(
    inv: InvoiceExtraction,
    threshold: float,
    *,
    penalty: float = DEFAULT_PENALTY,
    rules: tuple[Rule, ...] = DEFAULT_RULES,
) -> InvoiceExtraction:
    """Validate ``inv`` and return a copy with issues attached and confidences adjusted.

    - every failed rule multiplies the confidence of the fields it involves by ``penalty``
    - a missing required field gets confidence 0
    - ``needs_review`` is set when any issue exists or any field is below ``threshold``
    """
    result = inv.model_copy(deep=True)
    issues = run_rules(result, rules)
    for issue in issues:
        for path in issue.fields:
            try:
                field = result.get_field(path)
            except KeyError:
                continue
            field.confidence = round(field.confidence * penalty, 4)
    for name in REQUIRED_FIELDS:
        field = result.get_field(name)
        if field.value in (None, ""):
            field.confidence = 0.0
    result.validation_issues = issues
    result.needs_review = needs_review(result, threshold)
    return result

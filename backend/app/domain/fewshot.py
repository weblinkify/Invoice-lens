"""Turn stored field corrections into few-shot examples for the next extraction of a vendor."""

from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field

JsonScalar = str | float | None


@dataclass(frozen=True)
class Correction:
    document_id: str
    field_path: str
    old_value: JsonScalar
    new_value: JsonScalar
    created_at: datetime


class FieldFix(BaseModel):
    field: str
    extracted: JsonScalar
    corrected: JsonScalar


class FewShotExample(BaseModel):
    document_id: str
    fixes: list[FieldFix] = Field(default_factory=list)


def build_fewshot_examples(
    corrections: Iterable[Correction], max_examples: int = 3
) -> list[FewShotExample]:
    """Group corrections per document, newest document first, last correction per field wins.

    No-op corrections (value unchanged) are dropped, as are documents left with no fixes.
    """
    ordered = sorted(corrections, key=lambda c: c.created_at, reverse=True)
    by_doc: OrderedDict[str, dict[str, Correction]] = OrderedDict()
    for corr in ordered:
        fields = by_doc.setdefault(corr.document_id, {})
        # newest first, so the first correction we see per field is the final one;
        # but the *original* extracted value is the oldest correction's old_value.
        if corr.field_path in fields:
            first = fields[corr.field_path]
            fields[corr.field_path] = Correction(
                document_id=first.document_id,
                field_path=first.field_path,
                old_value=corr.old_value,
                new_value=first.new_value,
                created_at=first.created_at,
            )
        else:
            fields[corr.field_path] = corr

    examples: list[FewShotExample] = []
    for doc_id, fields in by_doc.items():
        fixes = [
            FieldFix(field=c.field_path, extracted=c.old_value, corrected=c.new_value)
            for c in sorted(fields.values(), key=lambda c: c.field_path)
            if c.old_value != c.new_value
        ]
        if fixes:
            examples.append(FewShotExample(document_id=doc_id, fixes=fixes))
        if len(examples) >= max_examples:
            break
    return examples


def known_fixes(examples: Iterable[FewShotExample]) -> dict[str, FieldFix]:
    """Most recent fix per field path across examples (used for deterministic re-application)."""
    fixes: dict[str, FieldFix] = {}
    for example in examples:
        for fix in example.fixes:
            fixes.setdefault(fix.field, fix)
    return fixes


def render_fewshot_prompt(examples: Iterable[FewShotExample]) -> str:
    """Human-readable block injected into the LLM prompt."""
    lines: list[str] = []
    for n, example in enumerate(examples, start=1):
        lines.append(f"Example {n} (previous invoice from this vendor, corrected by a reviewer):")
        for fix in example.fixes:
            lines.append(
                f"  - {fix.field}: extracted {fix.extracted!r} -> correct {fix.corrected!r}"
            )
    if not lines:
        return ""
    return "\n".join(
        ["Reviewers corrected earlier extractions from this vendor. Learn from them:", *lines]
    )

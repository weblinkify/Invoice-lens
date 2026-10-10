"""Field-level accuracy of the pipeline against fixture ground truth."""

from collections.abc import Iterable
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from app.domain.confidence import score
from app.domain.schema import AnyField, InvoiceExtraction
from app.llm.base import ExtractionRequest, LLMProvider
from app.llm.truth import load_truth, sha256_bytes, truth_path_for, truth_to_extraction
from app.ocr.base import OcrEngine

AMOUNT_TOLERANCE = 0.01


class FieldScore(BaseModel):
    correct: int = 0
    total: int = 0

    @property
    def accuracy(self) -> float:
        return round(self.correct / self.total, 4) if self.total else 0.0


class FieldAccuracy(BaseModel):
    field: str
    correct: int
    total: int
    accuracy: float


class DocumentAccuracy(BaseModel):
    file: str
    correct: int
    total: int
    accuracy: float
    needs_review: bool
    mismatched_fields: list[str]


class AccuracyReport(BaseModel):
    provider: str
    documents: int
    fields_total: int
    fields_correct: int
    accuracy: float
    review_rate: float
    per_field: list[FieldAccuracy]
    per_document: list[DocumentAccuracy]


def values_match(expected: AnyField, actual: AnyField) -> bool:
    e, a = expected.value, actual.value
    if isinstance(e, float) and isinstance(a, float):
        return abs(e - a) <= AMOUNT_TOLERANCE
    if isinstance(e, str) and isinstance(a, str):
        return " ".join(e.split()).casefold() == " ".join(a.split()).casefold()
    if isinstance(e, date) or isinstance(a, date):
        return e == a
    return e == a


def compare(truth: InvoiceExtraction, got: InvoiceExtraction) -> tuple[list[str], list[str]]:
    """Return (all paths, mismatched paths). Missing line items count as mismatches."""
    paths, wrong = [], []
    for path, expected in truth.iter_fields():
        paths.append(path)
        try:
            actual = got.get_field(path)
        except KeyError:
            wrong.append(path)
            continue
        if not values_match(expected, actual):
            wrong.append(path)
    return paths, wrong


def _group(path: str) -> str:
    parts = path.split(".")
    return f"line_items.{parts[2]}" if parts[0] == "line_items" else path


def evaluate(
    pdfs: Iterable[Path], ocr: OcrEngine, provider: LLMProvider, threshold: float
) -> AccuracyReport:
    per_field: dict[str, FieldScore] = {}
    docs: list[DocumentAccuracy] = []
    for pdf in pdfs:
        truth_file = truth_path_for(pdf)
        if not truth_file.exists():
            continue
        truth = truth_to_extraction(load_truth(truth_file))
        data = pdf.read_bytes()
        result = ocr.extract(data, "application/pdf")
        got = provider.extract(
            ExtractionRequest(pdf.name, data, "application/pdf", sha256_bytes(data), result)
        )
        scored = score(got, threshold)
        paths, wrong = compare(truth, got)
        for path in paths:
            bucket = per_field.setdefault(_group(path), FieldScore())
            bucket.total += 1
            bucket.correct += path not in wrong
        docs.append(
            DocumentAccuracy(
                file=pdf.name,
                correct=len(paths) - len(wrong),
                total=len(paths),
                accuracy=round((len(paths) - len(wrong)) / len(paths), 4) if paths else 0.0,
                needs_review=scored.needs_review,
                mismatched_fields=wrong,
            )
        )
    total = sum(d.total for d in docs)
    correct = sum(d.correct for d in docs)
    return AccuracyReport(
        provider=provider.name,
        documents=len(docs),
        fields_total=total,
        fields_correct=correct,
        accuracy=round(correct / total, 4) if total else 0.0,
        review_rate=round(sum(d.needs_review for d in docs) / len(docs), 4) if docs else 0.0,
        per_field=[
            FieldAccuracy(field=k, correct=v.correct, total=v.total, accuracy=v.accuracy)
            for k, v in per_field.items()
        ],
        per_document=docs,
    )

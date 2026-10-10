"""Print the README accuracy table (markdown) for the bundled fixtures.

Compares the default MockProvider (ground truth + injected OCR-style noise) with the pure
regex/OCR heuristics it falls back to when a document has no ground truth. Run inside the
backend container so tesseract is available for the scanned invoice:

    docker compose exec -T backend python -m scripts.accuracy_report
"""

from collections.abc import Sequence
from pathlib import Path

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.mock import MockProvider
from app.llm.truth import TruthIndex
from app.ocr.engines import build_ocr_engine
from app.services.accuracy import AccuracyReport, evaluate

FIELD_ORDER = [
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
    "line_items.description",
    "line_items.quantity",
    "line_items.unit_price",
    "line_items.vat_rate",
    "line_items.line_total",
]


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def table(reports: Sequence[tuple[str, AccuracyReport]]) -> str:
    header = "| Field | " + " | ".join(name for name, _ in reports) + " |"
    sep = "| --- | " + " | ".join("---:" for _ in reports) + " |"
    by_field = [{f.field: f for f in r.per_field} for _, r in reports]
    rows = []
    for field in FIELD_ORDER:
        cells = [pct(m[field].accuracy) if field in m else "—" for m in by_field]
        rows.append(f"| `{field}` | " + " | ".join(cells) + " |")
    total = (
        "| **All fields** | "
        + " | ".join(
            f"**{pct(r.accuracy)}** ({r.fields_correct}/{r.fields_total})" for _, r in reports
        )
        + " |"
    )
    review = "| Routed to review | " + " | ".join(pct(r.review_rate) for _, r in reports) + " |"
    return "\n".join([header, sep, *rows, total, review])


def main() -> None:
    settings = get_settings()
    truth = TruthIndex(settings.fixtures_dirs)
    pdfs: dict[str, Path] = {}
    for directory in settings.fixtures_dirs:
        for pdf in sorted(Path(directory).glob("*.pdf")):
            pdfs.setdefault(pdf.name, pdf)
    ocr = build_ocr_engine(settings.ocr_engine, settings.tesseract_cmd)
    providers: list[tuple[str, LLMProvider]] = [
        ("MockProvider (default)", MockProvider(truth, seed=settings.mock_seed)),
        ("OCR + heuristics only", MockProvider(truth, use_ground_truth=False)),
    ]
    reports = [
        (name, evaluate(sorted(pdfs.values()), ocr, provider, settings.confidence_threshold))
        for name, provider in providers
    ]
    print(f"Evaluated on {reports[0][1].documents} generated invoices.\n")
    print(table(reports))


if __name__ == "__main__":
    main()

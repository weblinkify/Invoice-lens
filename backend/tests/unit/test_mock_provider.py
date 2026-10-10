import random
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.fewshot import Correction, build_fewshot_examples
from app.domain.schema import InvoiceExtraction
from app.llm.base import ExtractionRequest
from app.llm.mock import NOISY_FIELDS, MockProvider, apply_examples, corrupt
from app.llm.truth import TruthIndex, load_truth, sha256_bytes, truth_to_extraction
from app.ocr.base import OcrResult
from app.ocr.engines import PdfTextEngine
from tests.conftest import FIXTURES, fixture_path
from tests.factories import valid_invoice


def request_for(pdf: Path, name: str | None = None, data: bytes | None = None) -> ExtractionRequest:
    data = data if data is not None else pdf.read_bytes()
    return ExtractionRequest(
        filename=name or pdf.name,
        data=data,
        content_type="application/pdf",
        sha256=sha256_bytes(data),
        ocr=PdfTextEngine().extract(data, "application/pdf"),
    )


def truth_for(pdf: Path) -> InvoiceExtraction:
    return truth_to_extraction(load_truth(pdf.with_name(pdf.stem + ".truth.json")))


def test_truth_index(truth_index: TruthIndex, fixture_pdfs: list[Path]) -> None:
    assert len(truth_index) == 10
    sha = sha256_bytes(fixture_pdfs[0].read_bytes())
    assert truth_index.lookup(sha) is not None
    assert truth_index.lookup("0" * 64) is None
    assert truth_index.lookup_name(fixture_pdfs[0].name) is not None
    assert TruthIndex([Path("/nonexistent")]).lookup(sha) is None


def test_mock_is_deterministic(truth_index: TruthIndex) -> None:
    pdf = fixture_path("invoice_02")
    a = MockProvider(truth_index).extract(request_for(pdf))
    b = MockProvider(truth_index).extract(request_for(pdf))
    assert a == b


def test_mock_injects_one_low_and_one_amber_field(truth_index: TruthIndex) -> None:
    for pdf in sorted(FIXTURES.glob("*.pdf")):
        result = MockProvider(truth_index).extract(request_for(pdf))
        low = [path for path, f in result.iter_fields() if f.confidence < 0.66]
        noisy = [p for p in low if p in NOISY_FIELDS]
        assert len(noisy) == 1, pdf.name
        truth = truth_for(pdf)
        wrong = [p for p, f in result.iter_fields() if f.value != truth.get_field(p).value]
        assert set(wrong) <= set(noisy)


def test_mock_without_noise_returns_truth(truth_index: TruthIndex) -> None:
    pdf = fixture_path("invoice_03")
    result = MockProvider(truth_index, noise=False).extract(request_for(pdf))
    truth = truth_for(pdf)
    assert [f.value for _, f in result.iter_fields()] == [f.value for _, f in truth.iter_fields()]
    assert result.total.bbox == truth.total.bbox


def test_mock_matches_by_filename_when_bytes_differ(truth_index: TruthIndex) -> None:
    pdf = fixture_path("invoice_01")
    req = request_for(pdf, data=pdf.read_bytes() + b"\n%trailing")
    assert (
        MockProvider(truth_index).extract(req).vendor_name.value == truth_for(pdf).vendor_name.value
    )


def test_mock_falls_back_to_heuristics(truth_index: TruthIndex) -> None:
    pdf = fixture_path("invoice_04")
    provider = MockProvider(truth_index, use_ground_truth=False)
    result = provider.extract(request_for(pdf, name="renamed.pdf"))
    assert result.invoice_number.value == truth_for(pdf).invoice_number.value
    assert result.invoice_number.confidence == pytest.approx(0.72)


def test_missing_due_date_is_flagged_uncertain(truth_index: TruthIndex) -> None:
    result = MockProvider(truth_index, noise=False).extract(
        request_for(fixture_path("missing_due"))
    )
    assert result.due_date.value is None
    assert result.due_date.confidence == pytest.approx(0.62)


@pytest.mark.parametrize("seed", range(20))
def test_corrupt_changes_value(seed: int) -> None:
    rng = random.Random(seed)
    for value in ["INV-2026-0815", "RF18539007547034", "ABC"]:
        assert corrupt(value, rng) != value


def test_apply_examples_reuses_corrections() -> None:
    inv = valid_invoice()
    inv.iban.value = "FI2112345600OOO785"
    inv.iban.confidence = 0.4
    examples = build_fewshot_examples(
        [
            Correction(
                "d1",
                "iban",
                "FI2112345600OOO785",
                "FI2112345600000785",
                datetime(2026, 1, 1, tzinfo=UTC),
            ),
            Correction(
                "d1", "due_date", "2026-03-30", "2026-03-31", datetime(2026, 1, 1, tzinfo=UTC)
            ),
            Correction("d1", "total", 434.5, 434.0, datetime(2026, 1, 1, tzinfo=UTC)),
            Correction("d1", "line_items.7.quantity", 1.0, 2.0, datetime(2026, 1, 1, tzinfo=UTC)),
        ]
    )
    inv.due_date.value = valid_invoice().due_date.value.replace(day=30)  # type: ignore[union-attr]
    inv.total.value = 434.5
    result = apply_examples(inv, examples)
    assert result.iban.value == "FI2112345600000785"
    assert result.iban.confidence == 0.97
    assert result.due_date.value is not None
    assert result.due_date.value.day == 31
    assert result.total.value == 434.0


def test_mock_applies_examples_end_to_end(truth_index: TruthIndex) -> None:
    pdf = fixture_path("invoice_02")
    noisy = MockProvider(truth_index).extract(request_for(pdf))
    noisy_path = next(p for p in NOISY_FIELDS if noisy.get_field(p).confidence < 0.66)
    wrong = noisy.get_field(noisy_path).value
    right = truth_for(pdf).get_field(noisy_path).value
    examples = build_fewshot_examples(
        [Correction("prev", noisy_path, wrong, right, datetime(2026, 1, 1, tzinfo=UTC))]  # type: ignore[arg-type]
    )
    req = request_for(pdf)
    req = ExtractionRequest(**{**req.__dict__, "examples": examples})
    fixed = MockProvider(truth_index).extract(req)
    if wrong != right:
        assert fixed.get_field(noisy_path).value == right
        assert fixed.get_field(noisy_path).confidence == 0.97


def test_empty_ocr_request(truth_index: TruthIndex) -> None:
    req = ExtractionRequest("x.pdf", b"", "application/pdf", "f" * 64, OcrResult([], "none"))
    assert MockProvider(truth_index).extract(req).total.value is None

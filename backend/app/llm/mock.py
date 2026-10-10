"""Deterministic mock LLM provider — the default, needs no API key.

* If the document matches a generated fixture (by SHA-256, then file name) it returns the
  ground truth with seeded noise: one field gets a low confidence and possibly an OCR-style
  error, another gets an amber confidence. That gives the review UI something real to show.
* Otherwise it falls back to regex heuristics over the OCR text.
* Few-shot examples from reviewer corrections are applied deterministically: if the
  extracted value equals a previously corrected wrong value, the correction is reused.
"""

import random
from datetime import date

from app.domain.fewshot import FewShotExample, known_fixes
from app.domain.schema import HEADER_FIELDS, AnyField, DateField, InvoiceExtraction, NumberField
from app.llm.base import ExtractionRequest
from app.llm.heuristics import heuristic_extract
from app.llm.truth import TruthIndex, truth_to_extraction

NOISY_FIELDS: tuple[str, ...] = ("invoice_number", "payment_reference", "iban", "vendor_vat_id")
OCR_CONFUSIONS: dict[str, str] = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}
LEARNED_CONFIDENCE = 0.97


def corrupt(value: str, rng: random.Random) -> str:
    """Introduce a single realistic OCR error (digit/letter confusion or transposition)."""
    positions = [i for i, ch in enumerate(value) if ch in OCR_CONFUSIONS]
    if positions and rng.random() < 0.7:
        i = rng.choice(positions)
        return value[:i] + OCR_CONFUSIONS[value[i]] + value[i + 1 :]
    digits = [i for i in range(len(value) - 1) if value[i].isdigit() and value[i + 1].isdigit()
              and value[i] != value[i + 1]]  # fmt: skip
    if digits:
        i = rng.choice(digits)
        return value[:i] + value[i + 1] + value[i] + value[i + 2 :]
    return value + "1"


class MockProvider:
    name = "mock"

    def __init__(
        self,
        truth: TruthIndex,
        seed: int = 42,
        noise: bool = True,
        use_ground_truth: bool = True,
    ) -> None:
        self.truth = truth
        self.seed = seed
        self.noise = noise
        self.use_ground_truth = use_ground_truth

    def extract(self, request: ExtractionRequest) -> InvoiceExtraction:
        truth = None
        if self.use_ground_truth:
            truth = self.truth.lookup(request.sha256) or self.truth.lookup_name(request.filename)
        if truth is None:
            result = heuristic_extract(request.ocr)
        else:
            rng = random.Random(f"{self.seed}:{request.sha256}")
            result = truth_to_extraction(truth)
            for _, fld in result.iter_fields():
                fld.confidence = round(rng.uniform(0.88, 0.99), 2)
            if truth["fields"]["due_date"]["value"] is None:
                result.due_date.confidence = 0.62  # unsure whether it is truly absent
            if self.noise:
                self._inject_noise(result, rng)
        return apply_examples(result, request.examples)

    @staticmethod
    def _inject_noise(inv: InvoiceExtraction, rng: random.Random) -> None:
        noisy_name = rng.choice(NOISY_FIELDS)
        noisy = inv.get_field(noisy_name)
        noisy.confidence = round(rng.uniform(0.35, 0.65), 2)
        if isinstance(noisy.value, str) and rng.random() < 0.6:
            noisy.value = corrupt(noisy.value, rng)
        amber_name = rng.choice([n for n in HEADER_FIELDS if n != noisy_name])
        amber = inv.get_field(amber_name)
        amber.confidence = round(rng.uniform(0.62, 0.78), 2)


def apply_examples(inv: InvoiceExtraction, examples: list[FewShotExample]) -> InvoiceExtraction:
    """Re-apply reviewer fixes for this vendor where the same wrong value shows up again."""
    for path, fix in known_fixes(examples).items():
        try:
            fld = inv.get_field(path)
        except KeyError:
            continue
        if _as_json(fld) == fix.extracted and fix.corrected is not None:
            _set_value(fld, fix.corrected)
            fld.confidence = LEARNED_CONFIDENCE
    return inv


def _as_json(fld: AnyField) -> str | float | None:
    value = fld.value
    return value.isoformat() if isinstance(value, date) else value


def _set_value(fld: AnyField, value: str | float) -> None:
    if isinstance(fld, DateField):
        fld.value = date.fromisoformat(str(value))
    elif isinstance(fld, NumberField):
        fld.value = float(value)
    else:
        fld.value = str(value)

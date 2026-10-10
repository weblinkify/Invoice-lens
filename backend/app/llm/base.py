"""LLM provider protocol shared by the mock and real providers."""

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.fewshot import FewShotExample
from app.domain.schema import InvoiceExtraction
from app.ocr.base import OcrResult


class ProviderError(RuntimeError):
    """Raised when a provider cannot produce a valid extraction."""


@dataclass(frozen=True)
class ExtractionRequest:
    filename: str
    data: bytes
    content_type: str
    sha256: str
    ocr: OcrResult
    examples: list[FewShotExample] = field(default_factory=list)
    vendor_hint: str | None = None


class LLMProvider(Protocol):
    name: str

    def extract(self, request: ExtractionRequest) -> InvoiceExtraction: ...

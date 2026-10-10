"""OCR abstraction. Engines turn document bytes into page text plus word boxes."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

OcrMethod = Literal["pdf_text", "tesseract", "none"]

PDF_TYPES = frozenset({"application/pdf"})
IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/tiff", "image/webp"})
SUPPORTED_TYPES = PDF_TYPES | IMAGE_TYPES


@dataclass(frozen=True)
class OcrWord:
    text: str
    bbox: tuple[float, float, float, float]  # normalized 0..1, top-left origin


@dataclass(frozen=True)
class OcrPage:
    number: int
    width: float
    height: float
    text: str
    words: list[OcrWord] = field(default_factory=list)


@dataclass(frozen=True)
class OcrResult:
    pages: list[OcrPage]
    method: OcrMethod

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)

    @property
    def page_count(self) -> int:
        return len(self.pages)


class OcrEngine(Protocol):
    def extract(self, data: bytes, content_type: str) -> OcrResult: ...

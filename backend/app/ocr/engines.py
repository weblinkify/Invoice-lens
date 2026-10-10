"""Concrete OCR engines: pdfplumber text layer with a pytesseract fallback for scans."""

import io
import logging
from collections.abc import Callable
from typing import Any

import pdfplumber
from PIL import Image

from app.ocr.base import IMAGE_TYPES, PDF_TYPES, OcrEngine, OcrPage, OcrResult, OcrWord

log = logging.getLogger(__name__)

MIN_TEXT_CHARS = 20
RASTER_DPI = 200


def _box(
    x0: float, top: float, x1: float, bottom: float, w: float, h: float
) -> tuple[float, float, float, float]:
    return (round(x0 / w, 4), round(top / h, 4), round(x1 / w, 4), round(bottom / h, 4))


class PdfTextEngine:
    """Reads the embedded text layer of digital PDFs."""

    def extract(self, data: bytes, content_type: str) -> OcrResult:
        if content_type not in PDF_TYPES:
            return OcrResult(pages=[], method="none")
        pages: list[OcrPage] = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for number, page in enumerate(pdf.pages, start=1):
                w, h = float(page.width), float(page.height)
                words = [
                    OcrWord(
                        text=str(word["text"]),
                        bbox=_box(word["x0"], word["top"], word["x1"], word["bottom"], w, h),
                    )
                    for word in page.extract_words()
                ]
                pages.append(
                    OcrPage(
                        number=number,
                        width=w,
                        height=h,
                        text=page.extract_text() or "",
                        words=words,
                    )
                )
        return OcrResult(pages=pages, method="pdf_text")


ImageToData = Callable[..., dict[str, list[Any]]]


class TesseractEngine:
    """OCR for images and image-only PDFs. ``image_to_data`` is injectable for tests."""

    def __init__(self, image_to_data: ImageToData | None = None, tesseract_cmd: str | None = None):
        self._image_to_data = image_to_data
        self._tesseract_cmd = tesseract_cmd

    def _ocr_fn(self) -> ImageToData:
        if self._image_to_data is not None:
            return self._image_to_data
        import pytesseract

        if self._tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd
        fn: ImageToData = pytesseract.image_to_data
        return fn

    def _images(self, data: bytes, content_type: str) -> list[Image.Image]:
        if content_type in IMAGE_TYPES:
            return [Image.open(io.BytesIO(data)).convert("RGB")]
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return [p.to_image(resolution=RASTER_DPI).original.convert("RGB") for p in pdf.pages]

    def extract(self, data: bytes, content_type: str) -> OcrResult:
        try:
            ocr = self._ocr_fn()
            images = self._images(data, content_type)
            pages = [self._page(n, img, ocr) for n, img in enumerate(images, start=1)]
        except Exception as exc:  # tesseract missing / unreadable image: degrade, don't crash
            log.warning("tesseract OCR unavailable or failed", extra={"error": str(exc)})
            return OcrResult(pages=[], method="none")
        return OcrResult(pages=pages, method="tesseract")

    @staticmethod
    def _page(number: int, image: Image.Image, ocr: ImageToData) -> OcrPage:
        w, h = image.size
        data = ocr(image, output_type="dict")
        words: list[OcrWord] = []
        lines: dict[tuple[int, int, int], list[str]] = {}
        for i, raw in enumerate(data["text"]):
            text = str(raw).strip()
            if not text or float(data["conf"][i]) < 0:
                continue
            left, top = float(data["left"][i]), float(data["top"][i])
            width, height = float(data["width"][i]), float(data["height"][i])
            words.append(OcrWord(text=text, bbox=_box(left, top, left + width, top + height, w, h)))
            key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
            lines.setdefault(key, []).append(text)
        text = "\n".join(" ".join(tokens) for _, tokens in sorted(lines.items()))
        return OcrPage(number=number, width=float(w), height=float(h), text=text, words=words)


class AutoEngine:
    """Text layer first; fall back to tesseract when a PDF has (almost) no text or for images."""

    def __init__(self, pdf: OcrEngine | None = None, tesseract: OcrEngine | None = None) -> None:
        self.pdf = pdf or PdfTextEngine()
        self.tesseract = tesseract or TesseractEngine()

    def extract(self, data: bytes, content_type: str) -> OcrResult:
        if content_type in IMAGE_TYPES:
            return self.tesseract.extract(data, content_type)
        result = self.pdf.extract(data, content_type)
        if len(result.text.strip()) >= MIN_TEXT_CHARS:
            return result
        log.info("pdf has no text layer, falling back to tesseract")
        scanned = self.tesseract.extract(data, content_type)
        return scanned if scanned.pages else result


class NullEngine:
    def extract(self, data: bytes, content_type: str) -> OcrResult:
        return OcrResult(pages=[], method="none")


def build_ocr_engine(kind: str, tesseract_cmd: str | None = None) -> OcrEngine:
    if kind == "none":
        return NullEngine()
    if kind == "pdf":
        return PdfTextEngine()
    return AutoEngine(tesseract=TesseractEngine(tesseract_cmd=tesseract_cmd))

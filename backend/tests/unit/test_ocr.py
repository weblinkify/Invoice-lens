import io
from typing import Any

from PIL import Image

from app.ocr.base import OcrPage, OcrResult
from app.ocr.engines import (
    AutoEngine,
    NullEngine,
    PdfTextEngine,
    TesseractEngine,
    build_ocr_engine,
)
from tests.conftest import fixture_path


def fake_tesseract(image: Image.Image, output_type: str = "dict") -> dict[str, list[Any]]:
    assert output_type == "dict"
    return {
        "text": ["Invoice", "number:", "INV-1", "", "Total", "10,00"],
        "conf": [95, 90, 88, -1, 92, 91],
        "left": [10, 80, 160, 0, 10, 80],
        "top": [10, 10, 10, 0, 40, 40],
        "width": [60, 70, 50, 0, 40, 50],
        "height": [12, 12, 12, 0, 12, 12],
        "block_num": [1, 1, 1, 1, 2, 2],
        "par_num": [1, 1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 1, 1, 1],
    }


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(buf, "PNG")
    return buf.getvalue()


def test_pdf_text_engine_reads_text_layer_and_words() -> None:
    data = fixture_path("invoice_01").read_bytes()
    result = PdfTextEngine().extract(data, "application/pdf")
    assert result.method == "pdf_text"
    assert result.page_count == 1
    assert "Invoice number" in result.text
    word = result.pages[0].words[0]
    assert all(0 <= v <= 1 for v in word.bbox)


def test_pdf_text_engine_ignores_images() -> None:
    assert PdfTextEngine().extract(png_bytes(), "image/png").method == "none"


def test_scanned_pdf_has_no_text_layer() -> None:
    data = fixture_path("rotated_scan").read_bytes()
    assert PdfTextEngine().extract(data, "application/pdf").text.strip() == ""


def test_tesseract_engine_builds_lines_and_boxes() -> None:
    result = TesseractEngine(image_to_data=fake_tesseract).extract(png_bytes(), "image/png")
    assert result.method == "tesseract"
    assert result.pages[0].text == "Invoice number: INV-1\nTotal 10,00"
    assert result.pages[0].words[0].bbox == (0.05, 0.1, 0.35, 0.22)


def test_tesseract_engine_rasterizes_pdfs() -> None:
    data = fixture_path("rotated_scan").read_bytes()
    result = TesseractEngine(image_to_data=fake_tesseract).extract(data, "application/pdf")
    assert result.page_count == 1


def test_tesseract_failure_degrades_to_empty() -> None:
    def broken(image: Image.Image, output_type: str = "dict") -> dict[str, list[Any]]:
        raise RuntimeError("tesseract is not installed")

    result = TesseractEngine(image_to_data=broken).extract(png_bytes(), "image/png")
    assert result == OcrResult(pages=[], method="none")


class StubEngine:
    def __init__(self, result: OcrResult) -> None:
        self.result = result
        self.calls = 0

    def extract(self, data: bytes, content_type: str) -> OcrResult:
        self.calls += 1
        return self.result


def page(text: str) -> OcrPage:
    return OcrPage(number=1, width=1, height=1, text=text)


def test_auto_engine_prefers_text_layer() -> None:
    tess = StubEngine(OcrResult([page("ocr")], "tesseract"))
    auto = AutoEngine(pdf=StubEngine(OcrResult([page("x" * 50)], "pdf_text")), tesseract=tess)
    assert auto.extract(b"", "application/pdf").method == "pdf_text"
    assert tess.calls == 0


def test_auto_engine_falls_back_to_tesseract() -> None:
    tess = StubEngine(OcrResult([page("ocr text")], "tesseract"))
    auto = AutoEngine(pdf=StubEngine(OcrResult([page("")], "pdf_text")), tesseract=tess)
    assert auto.extract(b"", "application/pdf").method == "tesseract"
    assert auto.extract(b"", "image/png").method == "tesseract"


def test_auto_engine_keeps_pdf_result_when_tesseract_unavailable() -> None:
    empty_pdf = OcrResult([page("")], "pdf_text")
    auto = AutoEngine(pdf=StubEngine(empty_pdf), tesseract=StubEngine(OcrResult([], "none")))
    assert auto.extract(b"", "application/pdf") is empty_pdf


def test_build_ocr_engine() -> None:
    assert isinstance(build_ocr_engine("none"), NullEngine)
    assert isinstance(build_ocr_engine("pdf"), PdfTextEngine)
    assert isinstance(build_ocr_engine("auto"), AutoEngine)
    assert NullEngine().extract(b"", "application/pdf").pages == []

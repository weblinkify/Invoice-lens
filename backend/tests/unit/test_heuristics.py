from datetime import date

import pytest

from app.llm.heuristics import heuristic_extract, parse_amount, parse_date
from app.ocr.base import OcrPage, OcrResult, OcrWord
from app.ocr.engines import PdfTextEngine
from tests.conftest import fixture_path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 234,56", 1234.56),
        ("1.234,56", 1234.56),
        ("1,234.56", 1234.56),
        ("1\u00a0234,56 EUR", 1234.56),
        ("131,45", 131.45),
        ("25.5", 25.5),
        ("1.234", 1234.0),
        ("1,234", 1234.0),
        ("€ 99", 99.0),
        ("-12,50", -12.5),
        ("abc", None),
        ("", None),
        ("1.2.3,4.5", None),
    ],
)
def test_parse_amount(raw: str, expected: float | None) -> None:
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-03-05", date(2026, 3, 5)),
        ("05.03.2026", date(2026, 3, 5)),
        ("05/03/2026", date(2026, 3, 5)),
        ("05 Mar 2026", date(2026, 3, 5)),
        ("5 March 2026", date(2026, 3, 5)),
        ("Mar 5, 2026", date(2026, 3, 5)),
        ("31.02.2026", None),
        ("soon", None),
    ],
)
def test_parse_date(raw: str, expected: date | None) -> None:
    assert parse_date(raw) == expected


@pytest.mark.parametrize("fragment", ["classic", "modern", "minimal", "multi_page"])
def test_heuristics_on_each_template(fragment: str) -> None:
    pdf = fixture_path(fragment)
    inv = heuristic_extract(PdfTextEngine().extract(pdf.read_bytes(), "application/pdf"))
    assert inv.vendor_name.value
    assert inv.invoice_number.value
    assert inv.invoice_date.value is not None
    assert inv.total.value is not None
    assert inv.iban.confidence >= 0.85  # checksum-validated
    assert inv.line_items
    assert inv.total.bbox is not None
    assert inv.total.source_page is not None


def test_heuristics_on_plain_text_without_labels() -> None:
    text = (
        "INVOICE\nACME Ltd\nPaid by bank\nIBAN FI21 1234 5600 0007 86\n"
        "price 10 €\nVAT ID SE556036079401"
    )
    ocr = OcrResult(
        pages=[OcrPage(1, 100, 100, text, [OcrWord("ACME", (0.1, 0.1, 0.2, 0.15))])],
        method="tesseract",
    )
    inv = heuristic_extract(ocr)
    assert inv.vendor_name.value == "ACME Ltd"
    assert inv.iban.value == "FI2112345600000786"
    assert inv.iban.confidence < 0.5  # failed checksum → guess
    assert inv.vendor_vat_id.confidence < 0.5
    assert inv.currency.value == "EUR"
    assert inv.invoice_number.value is None
    assert inv.invoice_number.confidence == 0.0


def test_heuristics_on_empty_ocr() -> None:
    inv = heuristic_extract(OcrResult(pages=[], method="none"))
    assert inv.vendor_name.value is None
    assert inv.currency.value is None
    assert inv.line_items == []


def test_currency_from_code_mentions() -> None:
    ocr = OcrResult([OcrPage(1, 1, 1, "Total 10,00 SEK\nShipping 5,00 SEK")], "pdf_text")
    assert heuristic_extract(ocr).currency.value == "SEK"

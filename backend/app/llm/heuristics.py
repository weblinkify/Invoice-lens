"""Regex heuristics over OCR text. Used by MockProvider when no ground truth matches."""

import re
from collections.abc import Callable
from datetime import date, datetime

from app.domain.schema import (
    DateField,
    InvoiceExtraction,
    LineItem,
    NumberField,
    StringField,
)
from app.domain.validators import ISO_4217, is_valid_iban, is_valid_vat_id, normalize_iban
from app.ocr.base import OcrResult

LABEL_CONFIDENCE = 0.72
GUESS_CONFIDENCE = 0.45
VALIDATED_CONFIDENCE = 0.85
NBSP = "\N{NO-BREAK SPACE}"

_AMOUNT = r"-?\d{1,3}(?:[ .,\xa0]\d{3})*(?:[.,]\d{2})|-?\d+(?:[.,]\d{2})?"
IBAN_PATTERN = r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?"
_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y")
_DATE = r"\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{4}|\d{1,2} [A-Za-z]{3,9} \d{4}"

LABELS: dict[str, str] = {
    "invoice_number": (
        r"invoice\s*(?:number|no\.?|#)|rechnungsnummer|fakturanummer|laskun numero|^no\."
    ),
    "invoice_date": r"invoice date|issued|rechnungsdatum|fakturadatum|^date",
    "due_date": r"due date|payment due|f[aä]lligkeit|f[oö]rfallodatum|er[aä]p[aä]iv[aä]|^due",
    "subtotal": r"subtotal|net amount|sum excl\.? vat|zwischensumme|netto",
    "vat_total": r"vat total|^vat\b|^tax\b|mwst|moms|alv",
    "total": r"amount due|total to pay|grand total|^total\b|gesamtbetrag|att betala",
    "payment_reference": r"payment reference|reference|^ref\b|viite|referens|verwendungszweck",
}


def parse_amount(raw: str) -> float | None:
    s = re.sub(r"[^\d,.\-]", "", raw.replace(NBSP, " ").replace(" ", ""))
    if not s or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", ".") if re.search(r",\d{2}$", s) else s.replace(",", "")
    elif s.count(".") > 1 or re.search(r"\.\d{3}$", s):
        s = s.replace(".", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse_date(raw: str) -> date | None:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _labelled(lines: list[str], label: str, value_re: str) -> tuple[str, int] | None:
    pattern = re.compile(rf"(?:{label})\s*[:#]?\s*({value_re})", re.IGNORECASE)
    for idx, line in enumerate(lines):
        match = pattern.search(line.strip())
        if match:
            return match.group(1), idx
    return None


class _Locator:
    """Finds the page + bbox of a value by matching OCR words."""

    def __init__(self, ocr: OcrResult) -> None:
        self.ocr = ocr

    def find(self, value: str) -> tuple[int | None, list[float] | None]:
        tokens = value.split()
        if not tokens:
            return None, None
        for page in self.ocr.pages:
            words = page.words
            for i in range(len(words)):
                if not words[i].text.endswith(tokens[0]) and tokens[0] not in words[i].text:
                    continue
                span = words[i : i + len(tokens)]
                if " ".join(w.text for w in span).find(value) == -1 and len(tokens) > 1:
                    continue
                x0 = min(w.bbox[0] for w in span)
                y0 = min(w.bbox[1] for w in span)
                x1 = max(w.bbox[2] for w in span)
                y1 = max(w.bbox[3] for w in span)
                return page.number, [x0, y0, x1, y1]
        return (self.ocr.pages[0].number if self.ocr.pages else None), None


def heuristic_extract(ocr: OcrResult) -> InvoiceExtraction:
    text = ocr.text
    lines = [line for line in text.splitlines() if line.strip()]
    loc = _Locator(ocr)

    def sfield(value: str | None, conf: float) -> StringField:
        if value is None:
            return StringField(value=None, confidence=0.0)
        page, bbox = loc.find(value)
        return StringField(value=value, confidence=conf, source_page=page, bbox=bbox)

    def nfield(raw: str | None, conf: float) -> NumberField:
        value = parse_amount(raw) if raw else None
        if value is None or raw is None:
            return NumberField(value=None, confidence=0.0)
        page, bbox = loc.find(raw.strip())
        return NumberField(value=value, confidence=conf, source_page=page, bbox=bbox)

    def dfield(raw: str | None, conf: float) -> DateField:
        value = parse_date(raw) if raw else None
        if value is None or raw is None:
            return DateField(value=None, confidence=0.0)
        page, bbox = loc.find(raw.strip())
        return DateField(value=value, confidence=conf, source_page=page, bbox=bbox)

    def grab(name: str, value_re: str) -> str | None:
        hit = _labelled(lines, LABELS[name], value_re)
        return hit[0].strip() if hit else None

    inv = InvoiceExtraction()
    inv.vendor_name = sfield(_vendor_name(lines), GUESS_CONFIDENCE + 0.15)
    inv.invoice_number = sfield(
        grab("invoice_number", r"[A-Z0-9][A-Z0-9\-/]{2,}"), LABEL_CONFIDENCE
    )
    inv.invoice_date = dfield(grab("invoice_date", _DATE), LABEL_CONFIDENCE)
    inv.due_date = dfield(grab("due_date", _DATE), LABEL_CONFIDENCE)
    inv.subtotal = nfield(grab("subtotal", _AMOUNT), LABEL_CONFIDENCE)
    inv.vat_total = nfield(grab("vat_total", _AMOUNT), LABEL_CONFIDENCE)
    inv.total = nfield(grab("total", _AMOUNT), LABEL_CONFIDENCE)
    inv.payment_reference = sfield(
        grab("payment_reference", r"RF\d{2}[0-9A-Z]+|\d{4,}"), LABEL_CONFIDENCE
    )
    inv.currency = sfield(*_currency(text))
    inv.iban = sfield(
        *_find_validated(text, IBAN_PATTERN, lambda v: is_valid_iban(v), normalize_iban)
    )
    inv.vendor_vat_id = sfield(
        *_find_validated(text, r"(?:FI|SE|DE)\d{8,12}", is_valid_vat_id, lambda v: v)
    )
    inv.line_items = _line_items(lines, loc)
    return inv


def _vendor_name(lines: list[str]) -> str | None:
    skip = re.compile(r"^(?:tax\s+)?invoice$|^lasku$|^faktura$|^rechnung$", re.IGNORECASE)
    for line in lines[:4]:
        candidate = line.strip()
        if candidate and not skip.match(candidate) and not re.search(r"\d{3,}", candidate):
            return candidate
    return None


def _currency(text: str) -> tuple[str | None, float]:
    labelled = re.search(r"currency\s*:?\s*([A-Z]{3})", text, re.IGNORECASE)
    if labelled and labelled.group(1).upper() in ISO_4217:
        return labelled.group(1).upper(), VALIDATED_CONFIDENCE
    codes = re.findall(r"\b(EUR|SEK|USD|GBP|NOK|DKK)\b", text)
    if codes:
        return max(set(codes), key=codes.count), LABEL_CONFIDENCE
    for symbol, code in (("€", "EUR"), ("$", "USD"), ("kr", "SEK")):
        if symbol in text:
            return code, GUESS_CONFIDENCE
    return None, 0.0


def _find_validated(
    text: str, pattern: str, valid: Callable[[str], bool], normalize: Callable[[str], str]
) -> tuple[str | None, float]:
    candidates = re.findall(pattern, text)
    for cand in candidates:
        if valid(cand):
            return normalize(cand), VALIDATED_CONFIDENCE
    if candidates:
        return normalize(candidates[0]), GUESS_CONFIDENCE
    return None, 0.0


_LINE_RE = re.compile(
    rf"^(?P<desc>.+?)\s+(?P<qty>\d+(?:[.,]\d+)?)\s+(?P<price>{_AMOUNT})\s+"
    rf"(?P<vat>\d+(?:[.,]\d+)?)\s*%\s+(?P<total>{_AMOUNT})$"
)


def _line_items(lines: list[str], loc: _Locator) -> list[LineItem]:
    items: list[LineItem] = []
    for line in lines:
        match = _LINE_RE.match(line.strip())
        if not match:
            continue
        desc = match.group("desc").strip()
        page, bbox = loc.find(desc)

        def num(raw: str, page: int | None = page) -> NumberField:
            return NumberField(
                value=parse_amount(raw), confidence=LABEL_CONFIDENCE, source_page=page
            )

        items.append(
            LineItem(
                description=StringField(
                    value=desc, confidence=LABEL_CONFIDENCE, source_page=page, bbox=bbox
                ),
                quantity=num(match.group("qty")),
                unit_price=num(match.group("price")),
                vat_rate=num(match.group("vat")),
                line_total=num(match.group("total")),
            )
        )
    return items


def attach_bboxes(inv: InvoiceExtraction, ocr: OcrResult) -> InvoiceExtraction:
    """Fill in missing bboxes for string values by locating them among OCR words."""
    if not ocr.pages:
        return inv
    loc = _Locator(ocr)
    for _, fld in inv.iter_fields():
        if fld.bbox is None and isinstance(fld, StringField) and fld.value:
            page, bbox = loc.find(fld.value)
            if bbox is not None:
                fld.bbox = bbox
                fld.source_page = fld.source_page or page
    return inv

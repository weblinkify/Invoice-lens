"""Generate realistic mock invoice PDFs with matching ``*.truth.json`` ground truth.

Usage::

    uv run python -m scripts.generate_invoices --count 10 --out tests/fixtures/invoices

Three layout templates, EUR/SEK/USD, Finnish/Swedish/German vendors, plus deliberate edge
cases (totals mismatch, missing due date, rotated image-only scan, multi-page invoice).
Bounding boxes are recorded while drawing, normalized to 0..1 with a top-left origin.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import shutil
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pdfplumber
from faker import Faker
from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from app.domain.validators import (
    de_vat_check_digit,
    fi_vat_check_digit,
    iban_checksum,
    luhn_check_digit,
)

PAGE_W, PAGE_H = A4
EDGE_CASES = {4: "totals_mismatch", 5: "missing_due_date", 6: "rotated_scan", 7: "multi_page"}

PRODUCTS = [
    ("Cloud hosting - monthly plan", 49.0, 349.0),
    ("Software license (per seat)", 19.0, 129.0),
    ("Consulting services (hours)", 85.0, 165.0),
    ("Office chairs, ergonomic", 189.0, 459.0),
    ("Printer toner cartridge", 39.0, 99.0),
    ("Website maintenance", 250.0, 900.0),
    ("Data migration project", 1200.0, 4800.0),
    ("Support retainer", 300.0, 1500.0),
    ("Laptop docking station", 129.0, 289.0),
    ("Training workshop (per person)", 220.0, 640.0),
    ("Shipping and handling", 12.0, 45.0),
    ("Security audit", 900.0, 3600.0),
]


# ---------------------------------------------------------------------------- vendors


@dataclass(frozen=True)
class Vendor:
    country: str
    name: str
    street: str
    city: str
    vat_id: str
    iban: str
    vat_rate: float
    currency: str
    number_style: str  # "fi" -> 1 234,56 | "de" -> 1.234,56 | "en" -> 1,234.56


def _digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(n))


def make_fi_vat(rng: random.Random) -> str:
    while True:
        base = _digits(rng, 7)
        check = fi_vat_check_digit(base)
        if check is not None:
            return f"FI{base}{check}"


def make_se_vat(rng: random.Random) -> str:
    base = "55" + _digits(rng, 7)
    return f"SE{base}{luhn_check_digit(base)}01"


def make_de_vat(rng: random.Random) -> str:
    base = str(rng.randint(1, 9)) + _digits(rng, 7)
    return f"DE{base}{de_vat_check_digit(base)}"


def make_iban(rng: random.Random, country: str) -> str:
    bban = {"FI": 14, "SE": 20, "DE": 18}[country]
    body = _digits(rng, bban)
    return f"{country}{iban_checksum(country, body)}{body}"


def make_rf_reference(rng: random.Random) -> str:
    ref = _digits(rng, rng.randint(8, 14))
    return f"RF{iban_checksum('RF', ref)}{ref}"


def make_vendors(rng: random.Random) -> list[Vendor]:
    specs = [
        ("FI", "fi_FI", " Oy", 25.5, "EUR", "fi"),
        ("SE", "sv_SE", " AB", 25.0, "SEK", "fi"),
        ("DE", "de_DE", " GmbH", 19.0, "EUR", "de"),
        ("FI", "fi_FI", " Oy", 25.5, "EUR", "fi"),
        ("DE", "de_DE", " GmbH", 19.0, "EUR", "de"),
    ]
    vendors = []
    for country, locale, suffix, rate, currency, style in specs:
        fake = Faker(locale)
        fake.seed_instance(rng.randint(0, 10**9))
        vat = {"FI": make_fi_vat, "SE": make_se_vat, "DE": make_de_vat}[country](rng)
        base_name = fake.last_name() + rng.choice([" Solutions", " Systems", " Trading", " Tech"])
        vendors.append(
            Vendor(
                country=country,
                name=base_name + suffix,
                street=fake.street_address(),
                city=f"{fake.postcode()} {fake.city()}",
                vat_id=vat,
                iban=make_iban(rng, country),
                vat_rate=rate,
                currency=currency,
                number_style=style,
            )
        )
    return vendors


# ---------------------------------------------------------------------------- invoice data


@dataclass
class LineItemData:
    description: str
    quantity: float
    unit_price: float
    vat_rate: float

    @property
    def line_total(self) -> float:
        return round(self.quantity * self.unit_price, 2)


@dataclass
class InvoiceData:
    vendor: Vendor
    customer_name: str
    customer_address: str
    invoice_number: str
    invoice_date: date
    due_date: date | None
    currency: str
    items: list[LineItemData]
    payment_reference: str
    total_offset: float = 0.0
    edge_cases: list[str] = field(default_factory=list)

    @property
    def subtotal(self) -> float:
        return round(sum(i.line_total for i in self.items), 2)

    @property
    def vat_total(self) -> float:
        return round(sum(round(i.line_total * i.vat_rate / 100, 2) for i in self.items), 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.vat_total + self.total_offset, 2)


def fmt_amount(value: float, style: str) -> str:
    whole, frac = f"{value:,.2f}".split(".")
    if style == "en":
        return f"{whole}.{frac}"
    sep = " " if style == "fi" else "."
    return f"{whole.replace(',', sep)},{frac}"


def fmt_qty(value: float) -> str:
    return f"{value:g}"


def build_invoice(index: int, rng: random.Random, vendors: list[Vendor]) -> InvoiceData:
    vendor = vendors[index % len(vendors)]
    currency = "USD" if index in (3, 8) else vendor.currency
    if currency == "USD":
        vendor = Vendor(**{**vendor.__dict__, "number_style": "en", "currency": "USD"})
    fake = Faker("en_US")
    fake.seed_instance(rng.randint(0, 10**9))
    edge = EDGE_CASES.get(index)
    n_items = 34 if edge == "multi_page" else rng.randint(2, 6)
    picks = [rng.choice(PRODUCTS) for _ in range(n_items)]
    items = [
        LineItemData(
            description=desc,
            quantity=float(rng.choice([1, 1, 2, 3, 4, 5, 8, 10, 12])),
            unit_price=round(rng.uniform(lo, hi), 2),
            vat_rate=vendor.vat_rate,
        )
        for desc, lo, hi in picks
    ]
    issued = date(2026, 1, 5) + timedelta(days=rng.randint(0, 240))
    due: date | None = issued + timedelta(days=rng.choice([14, 21, 30]))
    if edge == "missing_due_date":
        due = None
    return InvoiceData(
        vendor=vendor,
        customer_name=fake.company(),
        customer_address=f"{fake.street_address()}, {fake.city()}",
        invoice_number=f"{vendor.country}-{issued.year}-{rng.randint(1000, 99999):05d}",
        invoice_date=issued,
        due_date=due,
        currency=currency,
        items=items,
        payment_reference=make_rf_reference(rng),
        total_offset=10.0 if edge == "totals_mismatch" else 0.0,
        edge_cases=[edge] if edge else [],
    )


# ---------------------------------------------------------------------------- templates


@dataclass(frozen=True)
class Template:
    name: str
    font: str
    bold: str
    date_fmt: str
    labels: dict[str, str]
    accent: str
    rows_per_page: int


TEMPLATES = [
    Template(
        name="classic",
        font="Helvetica",
        bold="Helvetica-Bold",
        date_fmt="%Y-%m-%d",
        labels={
            "title": "INVOICE",
            "invoice_number": "Invoice number:",
            "invoice_date": "Invoice date:",
            "due_date": "Due date:",
            "vat_id": "VAT ID:",
            "subtotal": "Subtotal",
            "vat_total": "VAT",
            "total": "Total",
            "iban": "IBAN:",
            "reference": "Reference:",
            "currency": "Currency:",
        },
        accent="#1f2937",
        rows_per_page=22,
    ),
    Template(
        name="modern",
        font="Helvetica",
        bold="Helvetica-Bold",
        date_fmt="%d.%m.%Y",
        labels={
            "title": "Invoice",
            "invoice_number": "Invoice #",
            "invoice_date": "Issued",
            "due_date": "Due",
            "vat_id": "Business ID / VAT",
            "subtotal": "Net amount",
            "vat_total": "Tax",
            "total": "Amount due",
            "iban": "Bank account (IBAN)",
            "reference": "Payment reference",
            "currency": "Currency",
        },
        accent="#4f46e5",
        rows_per_page=20,
    ),
    Template(
        name="minimal",
        font="Courier",
        bold="Courier-Bold",
        date_fmt="%d %b %Y",
        labels={
            "title": "TAX INVOICE",
            "invoice_number": "No.",
            "invoice_date": "Date",
            "due_date": "Payment due",
            "vat_id": "VAT reg.",
            "subtotal": "Sum excl. VAT",
            "vat_total": "VAT total",
            "total": "Total to pay",
            "iban": "IBAN",
            "reference": "Ref",
            "currency": "Currency",
        },
        accent="#0f766e",
        rows_per_page=24,
    ),
]


class Recorder:
    """Draws strings and remembers where each tracked field landed."""

    def __init__(self, canvas: Canvas) -> None:
        self.c = canvas
        self.page = 1
        self.boxes: dict[str, tuple[int, list[float]]] = {}

    def text(
        self,
        x: float,
        y: float,
        value: str,
        *,
        font: str,
        size: float,
        key: str | None = None,
        align: str = "left",
    ) -> None:
        width = stringWidth(value, font, size)
        if align == "right":
            x -= width
        self.c.setFont(font, size)
        self.c.drawString(x, y, value)
        if key:
            top = PAGE_H - (y + size * 0.9)
            bottom = PAGE_H - (y - size * 0.25)
            self.boxes[key] = (
                self.page,
                [
                    round(x / PAGE_W, 4),
                    round(top / PAGE_H, 4),
                    round((x + width) / PAGE_W, 4),
                    round(bottom / PAGE_H, 4),
                ],
            )

    def new_page(self) -> None:
        self.c.showPage()
        self.page += 1


def render(inv: InvoiceData, tpl: Template, path: Path) -> dict[str, tuple[int, list[float]]]:
    canvas = Canvas(str(path), pagesize=A4, invariant=1)
    canvas.setTitle(f"Invoice {inv.invoice_number}")
    canvas.setAuthor(inv.vendor.name)
    rec = Recorder(canvas)
    lab = tpl.labels
    v = inv.vendor

    def money(amount: float) -> str:
        return fmt_amount(amount, v.number_style)

    f, b = tpl.font, tpl.bold
    accent = HexColor(tpl.accent)

    # ---- header
    if tpl.name == "modern":
        canvas.setFillColor(accent)
        canvas.rect(0, PAGE_H - 70, PAGE_W, 70, stroke=0, fill=1)
        canvas.setFillColor(HexColor("#ffffff"))
        rec.text(40, PAGE_H - 45, v.name, font=b, size=20, key="vendor_name")
        rec.text(PAGE_W - 40, PAGE_H - 45, lab["title"], font=b, size=16, align="right")
        canvas.setFillColor(HexColor("#111827"))
        y = PAGE_H - 100
    elif tpl.name == "minimal":
        rec.text(PAGE_W / 2 - 120, PAGE_H - 60, v.name, font=b, size=16, key="vendor_name")
        rec.text(PAGE_W / 2 - 120, PAGE_H - 80, lab["title"], font=f, size=11)
        y = PAGE_H - 110
    else:
        canvas.setFillColor(accent)
        rec.text(40, PAGE_H - 60, v.name, font=b, size=18, key="vendor_name")
        rec.text(PAGE_W - 40, PAGE_H - 60, lab["title"], font=b, size=22, align="right")
        canvas.setFillColor(HexColor("#111827"))
        y = PAGE_H - 95

    # ---- vendor + meta block (label/value pairs each on their own line)
    rec.text(40, y, v.street, font=f, size=9)
    rec.text(40, y - 12, v.city, font=f, size=9)
    rec.text(40, y - 24, lab["vat_id"], font=f, size=9)
    rec.text(
        40 + stringWidth(lab["vat_id"] + " ", f, 9),
        y - 24,
        v.vat_id,
        font=f,
        size=9,
        key="vendor_vat_id",
    )

    meta = [
        ("invoice_number", inv.invoice_number),
        ("invoice_date", inv.invoice_date.strftime(tpl.date_fmt)),
    ]
    if inv.due_date is not None:
        meta.append(("due_date", inv.due_date.strftime(tpl.date_fmt)))
    meta.append(("currency", inv.currency))
    my = y - 50
    for key, value in meta:
        label = lab[key]
        rec.text(40, my, label, font=b, size=10)
        rec.text(150, my, value, font=f, size=10, key=key)
        my -= 14

    rec.text(330, y - 50, "Bill to:", font=b, size=10)
    rec.text(330, y - 64, inv.customer_name, font=f, size=10)
    rec.text(330, y - 78, inv.customer_address, font=f, size=9)

    # ---- line items table
    cols = [40, 300, 350, 430, 475]  # description, qty, unit price, vat, total (right edge 555)
    ty = my - 20

    def table_header(top: float) -> float:
        canvas.setFillColor(HexColor("#e5e7eb") if tpl.name != "minimal" else HexColor("#ffffff"))
        canvas.rect(35, top - 5, PAGE_W - 70, 17, stroke=0, fill=1)
        canvas.setFillColor(HexColor("#111827"))
        rec.text(cols[0], top, "Description", font=b, size=9)
        rec.text(cols[1] + 30, top, "Qty", font=b, size=9, align="right")
        rec.text(cols[2] + 70, top, "Unit price", font=b, size=9, align="right")
        rec.text(cols[3] + 35, top, "VAT", font=b, size=9, align="right")
        rec.text(555, top, "Line total", font=b, size=9, align="right")
        return top - 18

    ty = table_header(ty)
    for idx, item in enumerate(inv.items):
        if idx and idx % tpl.rows_per_page == 0:
            rec.text(555, 40, "Continued on next page", font=f, size=8, align="right")
            rec.new_page()
            ty = table_header(PAGE_H - 60)
        p = f"line_items.{idx}."
        rec.text(cols[0], ty, item.description, font=f, size=9, key=p + "description")
        rec.text(
            cols[1] + 30,
            ty,
            fmt_qty(item.quantity),
            font=f,
            size=9,
            key=p + "quantity",
            align="right",
        )
        rec.text(
            cols[2] + 70,
            ty,
            money(item.unit_price),
            font=f,
            size=9,
            key=p + "unit_price",
            align="right",
        )
        rec.text(
            cols[3] + 35,
            ty,
            f"{item.vat_rate:g}%",
            font=f,
            size=9,
            key=p + "vat_rate",
            align="right",
        )
        rec.text(
            555, ty, money(item.line_total), font=f, size=9, key=p + "line_total", align="right"
        )
        if tpl.name == "classic":
            canvas.setStrokeColor(HexColor("#d1d5db"))
            canvas.line(35, ty - 5, PAGE_W - 35, ty - 5)
        ty -= 16

    # ---- totals
    if ty < 200:
        rec.new_page()
        ty = PAGE_H - 80
    ty -= 10
    for key, amount, font in [
        ("subtotal", inv.subtotal, f),
        ("vat_total", inv.vat_total, f),
        ("total", inv.total, b),
    ]:
        size = 11 if key == "total" else 10
        number = money(amount)
        rec.text(380, ty, lab[key], font=font, size=size)
        # draw "<number> <currency>" right-aligned, but track the bbox of the number only
        x0 = 555 - stringWidth(f"{number} {inv.currency}", font, size)
        rec.text(x0, ty, number, font=font, size=size, key=key)
        rec.text(x0 + stringWidth(f"{number} ", font, size), ty, inv.currency, font=font, size=size)
        ty -= 16

    # ---- payment details
    ty -= 20
    for key, label_key, value in [
        ("iban", "iban", inv.vendor.iban),
        ("payment_reference", "reference", inv.payment_reference),
    ]:
        rec.text(40, ty, lab[label_key], font=b, size=10)
        rec.text(170, ty, value, font=f, size=10, key=key)
        ty -= 14
    rec.text(40, 40, f"{v.name} - {v.street}, {v.city} - {v.vat_id}", font=f, size=7)
    canvas.save()
    return rec.boxes


def rasterize_as_scan(path: Path, rng: random.Random) -> None:
    """Replace a text PDF with a slightly rotated, noisy, image-only version of itself."""
    resolution = 110
    with pdfplumber.open(path) as pdf:
        pages = [p.to_image(resolution=resolution).original.convert("L") for p in pdf.pages]
    scanned: list[Image.Image] = []
    for page in pages:
        angle = rng.uniform(1.2, 2.2) * rng.choice([-1, 1])
        rotated = page.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
        draw = ImageDraw.Draw(rotated)
        width, height = rotated.size
        for _ in range(2500):  # seeded scanner speckle
            x, y = rng.randrange(width), rng.randrange(height)
            draw.point((x, y), fill=rng.randint(90, 200))
        scanned.append(rotated.filter(ImageFilter.SMOOTH).convert("RGB"))
    buf = io.BytesIO()
    fixed = time.gmtime(1767225600)  # 2026-01-01, keeps output byte-identical
    scanned[0].save(
        buf,
        "PDF",
        resolution=float(resolution),
        save_all=True,
        append_images=scanned[1:],
        creationDate=fixed,
        modDate=fixed,
    )
    path.write_bytes(buf.getvalue())


def truth_payload(
    inv: InvoiceData, tpl: Template, boxes: dict[str, tuple[int, list[float]]], file_name: str
) -> dict[str, Any]:
    def fld(key: str, value: object) -> dict[str, Any]:
        page, box = boxes.get(key, (None, None))
        return {"value": value, "source_page": page, "bbox": box}

    header: dict[str, Any] = {
        "vendor_name": fld("vendor_name", inv.vendor.name),
        "vendor_vat_id": fld("vendor_vat_id", inv.vendor.vat_id),
        "invoice_number": fld("invoice_number", inv.invoice_number),
        "invoice_date": fld("invoice_date", inv.invoice_date.isoformat()),
        "due_date": fld("due_date", inv.due_date.isoformat() if inv.due_date else None),
        "currency": fld("currency", inv.currency),
        "subtotal": fld("subtotal", inv.subtotal),
        "vat_total": fld("vat_total", inv.vat_total),
        "total": fld("total", inv.total),
        "iban": fld("iban", inv.vendor.iban),
        "payment_reference": fld("payment_reference", inv.payment_reference),
    }
    header["line_items"] = [
        {
            name: fld(f"line_items.{i}.{name}", value)
            for name, value in [
                ("description", item.description),
                ("quantity", item.quantity),
                ("unit_price", item.unit_price),
                ("vat_rate", item.vat_rate),
                ("line_total", item.line_total),
            ]
        }
        for i, item in enumerate(inv.items)
    ]
    return {
        "file": file_name,
        "template": tpl.name,
        "vendor_country": inv.vendor.country,
        "edge_cases": inv.edge_cases,
        "fields": header,
    }


def generate(count: int, out: Path, seed: int = 2026) -> list[Path]:
    rng = random.Random(seed)
    Faker.seed(seed)
    vendors = make_vendors(rng)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index in range(count):
        inv = build_invoice(index, rng, vendors)
        tpl = TEMPLATES[index % len(TEMPLATES)]
        name = f"invoice_{index + 1:02d}_{tpl.name}_{inv.vendor.country.lower()}"
        if inv.edge_cases:
            name += "_" + inv.edge_cases[0]
        pdf_path = out / f"{name}.pdf"
        boxes = render(inv, tpl, pdf_path)
        if "rotated_scan" in inv.edge_cases:
            rasterize_as_scan(pdf_path, rng)
        truth = truth_payload(inv, tpl, boxes, pdf_path.name)
        (out / f"{name}.truth.json").write_text(json.dumps(truth, indent=2) + "\n")
        written.append(pdf_path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/invoices"))
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--copy-to", type=Path, default=None, help="also copy output here")
    args = parser.parse_args()
    for stale in [*args.out.glob("*.pdf"), *args.out.glob("*.truth.json")]:
        stale.unlink()
    written = generate(args.count, args.out, args.seed)
    if args.copy_to:
        args.copy_to.mkdir(parents=True, exist_ok=True)
        for stale in [*args.copy_to.glob("*.pdf"), *args.copy_to.glob("*.truth.json")]:
            stale.unlink()
        for pdf in written:
            shutil.copy2(pdf, args.copy_to / pdf.name)
            truth = pdf.with_suffix("").with_suffix(".truth.json")
            shutil.copy2(truth, args.copy_to / truth.name)
    print(f"Wrote {len(written)} invoices to {args.out}")


if __name__ == "__main__":
    main()

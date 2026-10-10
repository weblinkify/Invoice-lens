from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

API = "/api/v1"


def upload(client: TestClient, pdf: Path, name: str | None = None) -> str:
    with pdf.open("rb") as fh:
        res = client.post(
            f"{API}/documents", files={"file": (name or pdf.name, fh, "application/pdf")}
        )
    assert res.status_code == 202, res.text
    doc_id: str = res.json()["id"]
    return doc_id


def extraction(client: TestClient, doc_id: str) -> dict[str, Any]:
    res = client.get(f"{API}/documents/{doc_id}/extraction")
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


def low_confidence_fields(data: dict[str, Any], threshold: float = 0.8) -> list[str]:
    names = [
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
    ]
    return [n for n in names if data[n]["confidence"] < threshold]

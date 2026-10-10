import io
import json

import pytest
from fastapi.testclient import TestClient

from app.db.models import FieldCorrection
from app.llm.base import ExtractionRequest, ProviderError
from app.llm.truth import load_truth
from app.services.container import Services
from tests.conftest import FIXTURES, ClientFactory, fixture_path
from tests.integration.helpers import API, extraction, low_confidence_fields, upload

pytestmark = pytest.mark.integration


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "provider": "mock", "version": "0.1.0"}
    assert client.get(f"{API}/health").status_code == 200


def test_upload_processes_in_background(client: TestClient) -> None:
    doc_id = upload(client, fixture_path("invoice_01"))
    doc = client.get(f"{API}/documents/{doc_id}").json()
    assert doc["status"] in {"needs_review", "extracted"}
    assert doc["ocr_method"] == "pdf_text"
    assert doc["page_count"] == 1
    assert doc["vendor_name"]
    assert doc["min_confidence"] < 0.8
    body = extraction(client, doc_id)
    assert body["provider"] == "mock"
    assert body["threshold"] == 0.8
    assert body["data"]["needs_review"] is True
    assert body["data"]["total"]["bbox"]


def test_file_download(client: TestClient) -> None:
    pdf = fixture_path("invoice_02")
    doc_id = upload(client, pdf)
    res = client.get(f"{API}/documents/{doc_id}/file")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content == pdf.read_bytes()


def test_upload_validation(client_factory: ClientFactory) -> None:
    client = client_factory(max_upload_bytes=1000)
    res = client.post(f"{API}/documents", files={"file": ("a.pdf", b"", "application/pdf")})
    assert res.status_code == 422
    assert res.headers["content-type"] == "application/problem+json"
    assert res.json()["type"].endswith("empty-file")

    res = client.post(f"{API}/documents", files={"file": ("a.pdf", b"%PDF" + b"0" * 2000)})
    assert res.status_code == 413
    assert "limit is" in res.json()["detail"]

    res = client.post(
        f"{API}/documents", files={"file": ("a.pdf", b"hello world", "application/pdf")}
    )
    assert res.status_code == 415
    assert "(application/pdf)" in res.json()["detail"]

    res = client.post(
        f"{API}/documents", files={"file": ("x.exe", b"MZ....", "application/x-msdownload")}
    )
    assert res.status_code == 415

    res = client.post(f"{API}/documents")
    assert res.status_code == 422
    assert res.json()["errors"][0]["loc"] == ["body", "file"]


def test_problem_json_for_missing_resources(client: TestClient) -> None:
    res = client.get(f"{API}/documents/nope")
    assert res.status_code == 404
    body = res.json()
    assert body == {
        "type": "https://invoicelens.dev/problems/not-found",
        "title": "Not Found",
        "status": 404,
        "detail": "Document nope was not found",
        "instance": "/api/v1/documents/nope",
    }
    assert client.get("/api/v1/does-not-exist").json()["status"] == 404


def test_list_filters_and_pagination(client: TestClient) -> None:
    ids = [upload(client, p) for p in sorted(FIXTURES.glob("*.pdf"))[:4]]
    res = client.get(f"{API}/documents", params={"page_size": 3}).json()
    assert res["total"] == 4
    assert len(res["items"]) == 3
    assert client.get(f"{API}/documents", params={"page": 2, "page_size": 3}).json()["items"]

    client.post(f"{API}/documents/{ids[0]}/approve")
    approved = client.get(f"{API}/documents", params={"status": "approved"}).json()
    assert [d["id"] for d in approved["items"]] == [ids[0]]

    review = client.get(f"{API}/documents", params={"needs_review": True}).json()
    assert review["total"] >= 1
    assert all(d["needs_review"] for d in review["items"])

    vendor = client.get(f"{API}/documents/{ids[1]}").json()["vendor_name"]
    by_vendor = client.get(f"{API}/documents", params={"vendor": vendor[:5]}).json()
    assert ids[1] in [d["id"] for d in by_vendor["items"]]

    by_q = client.get(f"{API}/documents", params={"q": "invoice_03"}).json()
    assert [d["filename"] for d in by_q["items"]] == ["invoice_03_minimal_de.pdf"]

    assert client.get(f"{API}/documents", params={"status": "bogus"}).status_code == 422


def test_correct_and_approve_flow(client: TestClient, services: Services) -> None:
    pdf = fixture_path("invoice_02")
    truth = load_truth(pdf.with_name(pdf.stem + ".truth.json"))["fields"]
    doc_id = upload(client, pdf)
    data = extraction(client, doc_id)["data"]
    low = low_confidence_fields(data)
    assert low, "mock provider should flag at least one field"

    corrections = [{"field": f, "value": truth[f]["value"]} for f in low]
    res = client.patch(f"{API}/documents/{doc_id}/extraction", json={"corrections": corrections})
    assert res.status_code == 200, res.text
    body = res.json()
    assert sorted(body["corrected_fields"]) == sorted(low)
    for f in low:
        assert body["data"][f]["confidence"] == 1.0
        assert body["data"][f]["value"] == truth[f]["value"]
    assert body["data"]["needs_review"] is False
    assert client.get(f"{API}/documents/{doc_id}").json()["status"] == "extracted"

    # correcting a line item number
    res = client.patch(
        f"{API}/documents/{doc_id}/extraction",
        json={"corrections": [{"field": "line_items.0.quantity", "value": "3"}]},
    )
    item = res.json()["data"]["line_items"][0]
    assert item["quantity"]["value"] == 3.0
    assert {i["code"] for i in res.json()["data"]["validation_issues"]} >= {"line_item_arithmetic"}

    approved = client.post(f"{API}/documents/{doc_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_at"].startswith("2026-10-01T12:00")

    assert client.post(f"{API}/documents/{doc_id}/approve").status_code == 409
    locked = client.patch(
        f"{API}/documents/{doc_id}/extraction",
        json={"corrections": [{"field": "currency", "value": "EUR"}]},
    )
    assert locked.status_code == 409

    with services.session_factory() as session:
        rows = session.query(FieldCorrection).filter_by(document_id=doc_id).all()
        assert {r.field_path for r in rows} >= {"line_items.0.quantity"}
        assert all(r.vendor_id is not None for r in rows)


@pytest.mark.parametrize(
    ("field", "value", "status"),
    [
        ("total", "abc", 422),
        ("invoice_date", "31.12.2026", 422),
        ("nope", "x", 422),
        ("line_items.99.quantity", 1, 422),
        ("due_date", "", 200),
        ("total", 12.5, 200),
    ],
)
def test_correction_validation(client: TestClient, field: str, value: object, status: int) -> None:
    doc_id = upload(client, fixture_path("invoice_01"))
    res = client.patch(
        f"{API}/documents/{doc_id}/extraction",
        json={"corrections": [{"field": field, "value": value}]},
    )
    assert res.status_code == status, res.text


def test_fewshot_corrections_are_reused_for_same_vendor(client: TestClient) -> None:
    """Correct a corrupted value once; the next invoice from that vendor gets it right."""
    for pdf in sorted(FIXTURES.glob("*.pdf")):
        if "rotated" in pdf.name:
            continue  # no text layer → vendor cannot be detected without tesseract
        truth = load_truth(pdf.with_name(pdf.stem + ".truth.json"))["fields"]
        doc_id = upload(client, pdf)
        data = extraction(client, doc_id)["data"]
        wrong = [f for f in low_confidence_fields(data) if data[f]["value"] != truth[f]["value"]]
        if wrong:
            break
    else:
        pytest.fail("no fixture produced a corrupted value")
    field = wrong[0]
    client.patch(
        f"{API}/documents/{doc_id}/extraction",
        json={"corrections": [{"field": field, "value": truth[field]["value"]}]},
    )
    again = extraction(client, upload(client, pdf, name="again.pdf"))["data"]
    assert again[field]["value"] == truth[field]["value"]
    assert again[field]["confidence"] == 0.97


def test_approve_requires_extraction(client: TestClient, services: Services) -> None:
    class Failing:
        name = "failing"

        def extract(self, request: ExtractionRequest) -> None:
            raise ProviderError("LLM is down")

    services.provider = Failing()  # type: ignore[assignment]
    doc_id = upload(client, fixture_path("invoice_01"))
    doc = client.get(f"{API}/documents/{doc_id}").json()
    assert doc["status"] == "failed"
    assert doc["error"] == "LLM is down"
    assert client.post(f"{API}/documents/{doc_id}/approve").status_code == 409
    assert client.get(f"{API}/documents/{doc_id}/extraction").status_code == 409
    assert (
        client.patch(
            f"{API}/documents/{doc_id}/extraction",
            json={"corrections": [{"field": "total", "value": 1}]},
        ).status_code
        == 409
    )


def test_reprocess_and_delete(client: TestClient, services: Services) -> None:
    doc_id = upload(client, fixture_path("invoice_03"))
    client.patch(
        f"{API}/documents/{doc_id}/extraction",
        json={"corrections": [{"field": "currency", "value": "SEK"}]},
    )
    res = client.post(f"{API}/documents/{doc_id}/reprocess")
    assert res.status_code == 202
    assert extraction(client, doc_id)["corrected_fields"] == []

    client.post(f"{API}/documents/{doc_id}/approve")
    assert client.post(f"{API}/documents/{doc_id}/reprocess").status_code == 409

    assert client.delete(f"{API}/documents/{doc_id}").status_code == 204
    assert client.get(f"{API}/documents/{doc_id}").status_code == 404
    assert services.storage.blobs == {}  # type: ignore[attr-defined]


def test_png_upload_without_tesseract(client: TestClient) -> None:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(buf, "PNG")
    res = client.post(f"{API}/documents", files={"file": ("scan.png", buf.getvalue(), "image/png")})
    doc = client.get(f"{API}/documents/{res.json()['id']}").json()
    assert doc["content_type"] == "image/png"
    assert doc["status"] == "needs_review"  # heuristics found nothing


def test_settings_threshold_rescores(client: TestClient) -> None:
    doc_id = upload(client, fixture_path("invoice_03"))  # noise without validation issues
    assert client.get(f"{API}/settings").json() == {
        "confidence_threshold": 0.8,
        "llm_provider": "mock",
        "demo_mode": True,
        "max_upload_bytes": 10 * 1024 * 1024,
    }
    assert client.get(f"{API}/documents/{doc_id}").json()["status"] == "needs_review"
    res = client.put(f"{API}/settings", json={"confidence_threshold": 0.1})
    assert res.json()["confidence_threshold"] == 0.1
    assert client.get(f"{API}/documents/{doc_id}").json()["status"] == "extracted"
    assert extraction(client, doc_id)["threshold"] == 0.1
    assert client.put(f"{API}/settings", json={"confidence_threshold": 2}).status_code == 422


def test_samples(client: TestClient) -> None:
    samples = client.get(f"{API}/samples").json()
    assert len(samples) == 10
    scan = next(s for s in samples if "rotated" in s["name"])
    assert scan["edge_cases"] == ["rotated_scan"]
    res = client.post(f"{API}/samples/{samples[0]['name']}")
    assert res.status_code == 202
    assert client.get(res.json()["status_url"]).json()["status"] in {"needs_review", "extracted"}
    assert client.post(f"{API}/samples/../../etc/passwd").status_code == 404
    assert client.post(f"{API}/samples/nope.pdf").status_code == 404


def test_samples_dir_missing(client_factory: ClientFactory, tmp_path: object) -> None:
    client = client_factory(sample_data_dir="/nonexistent")
    assert client.get(f"{API}/samples").json() == []


def test_accuracy_metrics(client: TestClient) -> None:
    report = client.get(f"{API}/metrics/accuracy").json()
    assert report["provider"] == "mock"
    assert report["documents"] == 10
    assert report["accuracy"] >= 0.95
    assert {f["field"] for f in report["per_field"]} >= {"total", "line_items.quantity"}
    json.dumps(report)


def test_api_key_auth(client_factory: ClientFactory) -> None:
    client = client_factory(demo_mode=False, api_key="s3cret-key")
    assert client.get("/health").status_code == 200
    res = client.get(f"{API}/documents")
    assert res.status_code == 401
    assert res.headers["content-type"] == "application/problem+json"
    assert client.get(f"{API}/documents", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get(f"{API}/documents", headers={"X-API-Key": "s3cret-key"}).status_code == 200
    locked = client_factory(demo_mode=False, api_key=None)
    assert locked.get(f"{API}/documents", headers={"X-API-Key": ""}).status_code == 401


def test_unhandled_errors_become_problem_json(client: TestClient, services: Services) -> None:
    class Broken:
        def read(self, key: str) -> bytes:
            raise RuntimeError("disk on fire")

    doc_id = upload(client, fixture_path("invoice_01"))
    services.storage = Broken()  # type: ignore[assignment]
    client_no_raise = TestClient(client.app, raise_server_exceptions=False)
    res = client_no_raise.get(f"{API}/documents/{doc_id}/file")
    assert res.status_code == 500
    assert res.json()["detail"] == "An unexpected error occurred"

import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from mock_erp.main import create_app, verify

SECRET = "test-secret-123"


def signed(body: bytes, secret: str = SECRET, ts: int | None = None) -> dict[str, str]:
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {
        "X-InvoiceLens-Signature": f"t={ts},v1={sig}",
        "X-InvoiceLens-Event": "invoice.approved",
        "X-InvoiceLens-Delivery": "1",
        "Content-Type": "application/json",
    }


def test_accepts_valid_signature() -> None:
    client = TestClient(create_app(SECRET))
    body = json.dumps({"event": "invoice.approved", "data": {"id": "x"}}).encode()
    assert client.post("/webhooks/invoices", content=body, headers=signed(body)).status_code == 200
    got = client.get("/received").json()
    assert got["count"] == 1
    assert got["items"][0]["payload"]["data"] == {"id": "x"}
    assert got["items"][0]["signature_valid"] is True
    assert client.get("/received", params={"event": "ping"}).json()["count"] == 0


def test_rejects_bad_signature() -> None:
    client = TestClient(create_app(SECRET))
    body = b'{"a":1}'
    assert (
        client.post("/webhooks/invoices", content=body, headers=signed(body, "wrong")).status_code
        == 401
    )
    assert client.post("/webhooks/invoices", content=body).status_code == 401
    assert client.get("/received").json() == {
        "count": 0,
        "rejected": 2,
        "forced_failures": 0,
        "items": [],
    }


def test_fail_next_and_reset() -> None:
    client = TestClient(create_app(SECRET))
    body = b'{"a":1}'
    assert client.post("/fail-next", params={"count": 2}).json() == {"fail_next": 2}
    codes = [
        client.post("/webhooks/invoices", content=body, headers=signed(body)).status_code
        for _ in range(3)
    ]
    assert codes == [500, 500, 200]
    got = client.get("/received").json()
    assert got["forced_failures"] == 2
    assert got["items"][0]["attempt_number"] == 3
    assert client.delete("/received").status_code == 204
    assert client.get("/received").json()["count"] == 0
    assert client.get("/health").json() == {"status": "ok"}


def test_verify_edge_cases() -> None:
    body = b"{}"
    old = int(time.time()) - 3600
    assert not verify(SECRET, signed(body, ts=old)["X-InvoiceLens-Signature"], body)
    assert not verify(SECRET, "garbage", body)
    assert not verify(SECRET, "t=abc,v1=00", body)

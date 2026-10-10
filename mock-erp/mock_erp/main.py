"""Mock ERP / accounting system that receives InvoiceLens webhooks.

POST /webhooks/invoices   verify HMAC signature, store the payload
GET  /received            list what was received (E2E tests assert on this)
DELETE /received          reset
POST /fail-next?count=N   make the next N deliveries return 500 (exercise retries)
"""

import hashlib
import hmac
import json
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Query, Request, Response
from pydantic import BaseModel

SIGNATURE_HEADER = "X-InvoiceLens-Signature"


class Received(BaseModel):
    received_at: datetime
    event: str | None
    delivery_id: str | None
    signature_valid: bool
    attempt_number: int
    payload: dict[str, Any]


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.received: list[Received] = []
        self.fail_next = 0
        self.attempts: dict[str, int] = {}
        self.rejected = 0
        self.forced_failures = 0


def verify(secret: str, header: str, body: bytes, tolerance: int = 300) -> bool:
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - timestamp) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return hmac.compare_digest(parts.get("v1", ""), expected.hexdigest())


def create_app(secret: str | None = None) -> FastAPI:
    app = FastAPI(title="Mock ERP", version="0.1.0")
    state = State()
    shared_secret = secret or os.environ.get("MOCK_ERP_SECRET", "demo-webhook-secret")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/invoices")
    async def receive(request: Request) -> Response:
        body = await request.body()
        delivery_id = request.headers.get("X-InvoiceLens-Delivery")
        with state.lock:
            key = delivery_id or "unknown"
            state.attempts[key] = state.attempts.get(key, 0) + 1
            attempt = state.attempts[key]
            if state.fail_next > 0:
                state.fail_next -= 1
                state.forced_failures += 1
                return Response('{"error":"simulated outage"}', 500, media_type="application/json")
        valid = verify(shared_secret, request.headers.get(SIGNATURE_HEADER, ""), body)
        if not valid:
            with state.lock:
                state.rejected += 1
            return Response('{"error":"invalid signature"}', 401, media_type="application/json")
        data = json.loads(body)
        with state.lock:
            state.received.append(
                Received(
                    received_at=datetime.now(UTC),
                    event=request.headers.get("X-InvoiceLens-Event"),
                    delivery_id=delivery_id,
                    signature_valid=True,
                    attempt_number=attempt,
                    payload=data,
                )
            )
        return Response('{"status":"accepted"}', 200, media_type="application/json")

    @app.get("/received")
    def received(event: str | None = Query(default=None)) -> dict[str, Any]:
        with state.lock:
            items = [r for r in state.received if event is None or r.event == event]
            return {
                "count": len(items),
                "rejected": state.rejected,
                "forced_failures": state.forced_failures,
                "items": [r.model_dump(mode="json") for r in items],
            }

    @app.delete("/received", status_code=204)
    def reset() -> None:
        with state.lock:
            state.received.clear()
            state.attempts.clear()
            state.rejected = state.forced_failures = state.fail_next = 0

    @app.post("/fail-next")
    def fail_next(count: int = Query(default=1, ge=1, le=10)) -> dict[str, int]:
        with state.lock:
            state.fail_next += count
            return {"fail_next": state.fail_next}

    return app


app = create_app()

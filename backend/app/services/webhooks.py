"""Outbound webhooks: HMAC-SHA256 signed payloads with exponential-backoff retries.

Signature header (Stripe-style)::

    X-InvoiceLens-Signature: t=<unix seconds>,v1=<hex hmac_sha256(secret, f"{t}.{body}")>
"""

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DeliveryStatus, WebhookDelivery, WebhookEndpoint
from app.db.session import SessionFactory

log = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-InvoiceLens-Signature"
EVENT_HEADER = "X-InvoiceLens-Event"
DELIVERY_HEADER = "X-InvoiceLens-Delivery"
MAX_BACKOFF_SECONDS = 60.0


def encode_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str).encode()


def sign(secret: str, timestamp: int, body: bytes) -> str:
    message = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signature_header(secret: str, timestamp: int, body: bytes) -> str:
    return f"t={timestamp},v1={sign(secret, timestamp, body)}"


def verify_signature(
    secret: str, header: str, body: bytes, now: float, tolerance: int = 300
) -> bool:
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
        candidate = parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs(now - timestamp) > tolerance:
        return False
    return hmac.compare_digest(candidate, sign(secret, timestamp, body))


def backoff_delay(attempt: int, base: float) -> float:
    """Delay before retry number ``attempt`` (1-based): base, 2*base, 4*base, ... capped."""
    return float(min(base * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS))


def is_retryable(status_code: int | None) -> bool:
    return status_code is None or status_code >= 500 or status_code in (408, 429)


@dataclass
class WebhookDispatcher:
    session_factory: SessionFactory
    client_factory: Callable[[], httpx.Client]
    clock: Callable[[], datetime]
    sleep: Callable[[float], None] = time.sleep
    max_attempts: int = 5
    backoff_base: float = 0.5

    def enqueue(
        self,
        session: Session,
        event: str,
        payload: dict[str, Any],
        document_id: str | None = None,
        endpoint_ids: list[int] | None = None,
    ) -> list[int]:
        stmt = select(WebhookEndpoint).where(WebhookEndpoint.active.is_(True))
        if endpoint_ids is not None:
            stmt = select(WebhookEndpoint).where(WebhookEndpoint.id.in_(endpoint_ids))
        deliveries = [
            WebhookDelivery(
                endpoint_id=ep.id, document_id=document_id, event=event, payload=payload
            )
            for ep in session.scalars(stmt).all()
        ]
        session.add_all(deliveries)
        session.flush()
        return [d.id for d in deliveries]

    def deliver_many(self, delivery_ids: list[int]) -> None:
        for delivery_id in delivery_ids:
            self.deliver(delivery_id)

    def deliver(self, delivery_id: int) -> str:
        with self.session_factory() as session:
            delivery = session.get(WebhookDelivery, delivery_id)
            if delivery is None:
                return DeliveryStatus.FAILED
            endpoint = delivery.endpoint
            body = encode_body({"event": delivery.event, "data": delivery.payload})
            with self.client_factory() as client:
                while delivery.attempts < self.max_attempts:
                    if delivery.attempts:
                        self.sleep(backoff_delay(delivery.attempts, self.backoff_base))
                    delivery.attempts += 1
                    code, error = self._send(client, endpoint, delivery, body)
                    delivery.last_status_code = code
                    delivery.last_error = error
                    session.commit()
                    if code is not None and 200 <= code < 300:
                        delivery.status = DeliveryStatus.SUCCEEDED
                        delivery.delivered_at = self.clock()
                        break
                    if not is_retryable(code):
                        delivery.status = DeliveryStatus.FAILED
                        break
                else:
                    delivery.status = DeliveryStatus.FAILED
            session.commit()
            log.info(
                "webhook delivery finished",
                extra={
                    "delivery_id": delivery.id,
                    "endpoint_id": endpoint.id,
                    "status": delivery.status,
                    "attempts": delivery.attempts,
                    "last_status_code": delivery.last_status_code,
                },
            )
            return delivery.status

    def _send(
        self,
        client: httpx.Client,
        endpoint: WebhookEndpoint,
        delivery: WebhookDelivery,
        body: bytes,
    ) -> tuple[int | None, str | None]:
        timestamp = int(self.clock().timestamp())
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "InvoiceLens-Webhooks/1.0",
            EVENT_HEADER: delivery.event,
            DELIVERY_HEADER: str(delivery.id),
            SIGNATURE_HEADER: signature_header(endpoint.secret, timestamp, body),
        }
        try:
            response = client.post(endpoint.url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            return None, f"{type(exc).__name__}: {exc}"[:500]
        error = None if response.is_success else response.text[:500] or response.reason_phrase
        return response.status_code, error

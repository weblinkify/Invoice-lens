import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import WebhookDelivery, WebhookEndpoint
from app.db.session import SessionFactory, make_engine, make_session_factory
from app.services.webhooks import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    WebhookDispatcher,
    backoff_delay,
    encode_body,
    is_retryable,
    sign,
    signature_header,
    verify_signature,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
URL = "https://erp.example.com/hooks"
SECRET = "whsec_test_123"


def test_sign_matches_stdlib_hmac() -> None:
    expected = hmac.new(b"key", b"1.{}", hashlib.sha256).hexdigest()
    assert sign("key", 1, b"{}") == expected


def test_signature_roundtrip() -> None:
    body = encode_body({"b": 1, "a": [1, 2]})
    assert body == b'{"a":[1,2],"b":1}'
    header = signature_header(SECRET, 1_800_000_000, body)
    assert header.startswith("t=1800000000,v1=")
    assert verify_signature(SECRET, header, body, now=1_800_000_010)
    assert not verify_signature("other", header, body, now=1_800_000_010)
    assert not verify_signature(SECRET, header, body + b" ", now=1_800_000_010)
    assert not verify_signature(SECRET, header, body, now=1_800_000_000 + 301)
    assert not verify_signature(SECRET, "nonsense", body, now=0)
    assert not verify_signature(SECRET, "t=x,v1=y", body, now=0)


@pytest.mark.parametrize(
    ("attempt", "base", "expected"), [(1, 0.5, 0.5), (2, 0.5, 1.0), (3, 0.5, 2.0), (10, 1.0, 60.0)]
)
def test_backoff_delay(attempt: int, base: float, expected: float) -> None:
    assert backoff_delay(attempt, base) == expected


@pytest.mark.parametrize(
    ("code", "retry"),
    [
        (None, True),
        (500, True),
        (503, True),
        (429, True),
        (408, True),
        (400, False),
        (401, False),
        (404, False),
        (200, False),
    ],
)
def test_is_retryable(code: int | None, retry: bool) -> None:
    assert is_retryable(code) is retry


@pytest.fixture
def factory() -> SessionFactory:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def setup_delivery(
    factory: SessionFactory, active: bool = True
) -> tuple[WebhookDispatcher, list[float], int]:
    sleeps: list[float] = []
    dispatcher = WebhookDispatcher(
        session_factory=factory,
        client_factory=lambda: httpx.Client(timeout=1),
        clock=lambda: NOW,
        sleep=sleeps.append,
        max_attempts=4,
        backoff_base=0.5,
    )
    with factory() as session:
        session.add(WebhookEndpoint(url=URL, secret=SECRET, active=active))
        session.add(WebhookEndpoint(url=URL + "/inactive", secret=SECRET, active=False))
        session.commit()
        ids = dispatcher.enqueue(session, "invoice.approved", {"invoice": {"total": 10.0}}, "doc-1")
        session.commit()
    return dispatcher, sleeps, ids[0] if ids else -1


def get_delivery(factory: SessionFactory, delivery_id: int) -> WebhookDelivery:
    with factory() as session:
        d = session.get(WebhookDelivery, delivery_id)
        assert d is not None
        return d


@respx.mock
def test_successful_delivery_is_signed(factory: SessionFactory) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(200))
    dispatcher, sleeps, delivery_id = setup_delivery(factory)
    assert dispatcher.deliver(delivery_id) == "succeeded"
    request = route.calls.last.request
    assert request.headers[EVENT_HEADER] == "invoice.approved"
    assert request.headers[DELIVERY_HEADER] == str(delivery_id)
    assert verify_signature(
        SECRET, request.headers[SIGNATURE_HEADER], request.content, NOW.timestamp()
    )
    assert json.loads(request.content) == {
        "event": "invoice.approved",
        "data": {"invoice": {"total": 10.0}},
    }
    delivery = get_delivery(factory, delivery_id)
    assert (delivery.attempts, delivery.last_status_code, sleeps) == (1, 200, [])
    assert delivery.delivered_at is not None


@respx.mock
def test_retries_with_exponential_backoff(factory: SessionFactory) -> None:
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(500),
            httpx.ConnectError("down"),
            httpx.Response(503),
            httpx.Response(202),
        ]
    )
    dispatcher, sleeps, delivery_id = setup_delivery(factory)
    assert dispatcher.deliver(delivery_id) == "succeeded"
    assert route.call_count == 4
    assert sleeps == [0.5, 1.0, 2.0]


@respx.mock
def test_gives_up_after_max_attempts(factory: SessionFactory) -> None:
    respx.post(URL).mock(return_value=httpx.Response(500, text="boom"))
    dispatcher, sleeps, delivery_id = setup_delivery(factory)
    assert dispatcher.deliver(delivery_id) == "failed"
    delivery = get_delivery(factory, delivery_id)
    assert delivery.attempts == 4
    assert delivery.last_error == "boom"
    assert len(sleeps) == 3


@respx.mock
def test_client_errors_are_not_retried(factory: SessionFactory) -> None:
    route = respx.post(URL).mock(return_value=httpx.Response(401))
    dispatcher, _sleeps, delivery_id = setup_delivery(factory)
    assert dispatcher.deliver(delivery_id) == "failed"
    assert route.call_count == 1
    assert get_delivery(factory, delivery_id).last_error == "Unauthorized"


@respx.mock
def test_network_errors_recorded(factory: SessionFactory) -> None:
    respx.post(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    dispatcher, _, delivery_id = setup_delivery(factory)
    dispatcher.deliver_many([delivery_id, 9999])
    delivery = get_delivery(factory, delivery_id)
    assert delivery.status == "failed"
    assert delivery.last_status_code is None
    assert delivery.last_error is not None
    assert "ConnectTimeout" in delivery.last_error


def test_enqueue_only_targets_active_endpoints(factory: SessionFactory) -> None:
    _, _, delivery_id = setup_delivery(factory, active=False)
    assert delivery_id == -1
    with factory() as session:
        assert isinstance(session, Session)
        assert session.query(WebhookDelivery).count() == 0

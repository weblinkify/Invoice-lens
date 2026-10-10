from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ServicesDep, SessionDep
from app.api.schemas import (
    WebhookDeliveryOut,
    WebhookEndpointIn,
    WebhookEndpointOut,
    WebhookEndpointUpdate,
)
from app.core.errors import NotFoundError
from app.db.models import WebhookDelivery, WebhookEndpoint

router = APIRouter(prefix="/webhook-endpoints", tags=["webhooks"])


def _out(ep: WebhookEndpoint) -> WebhookEndpointOut:
    return WebhookEndpointOut(
        id=ep.id,
        url=ep.url,
        description=ep.description,
        active=ep.active,
        created_at=ep.created_at,
        secret_hint=f"••••{ep.secret[-4:]}",
    )


def _get(session: Session, endpoint_id: int) -> WebhookEndpoint:
    ep = session.get(WebhookEndpoint, endpoint_id)
    if ep is None:
        raise NotFoundError("Webhook endpoint", endpoint_id)
    return ep


@router.get("", response_model=list[WebhookEndpointOut])
def list_webhook_endpoints(session: SessionDep) -> list[WebhookEndpointOut]:
    return [
        _out(ep) for ep in session.scalars(select(WebhookEndpoint).order_by(WebhookEndpoint.id))
    ]


@router.post("", response_model=WebhookEndpointOut, status_code=status.HTTP_201_CREATED)
def create_webhook_endpoint(session: SessionDep, body: WebhookEndpointIn) -> WebhookEndpointOut:
    ep = WebhookEndpoint(
        url=str(body.url), secret=body.secret, description=body.description, active=body.active
    )
    session.add(ep)
    session.commit()
    return _out(ep)


@router.get("/{endpoint_id}", response_model=WebhookEndpointOut)
def get_webhook_endpoint(session: SessionDep, endpoint_id: int) -> WebhookEndpointOut:
    return _out(_get(session, endpoint_id))


@router.patch("/{endpoint_id}", response_model=WebhookEndpointOut)
def update_webhook_endpoint(
    session: SessionDep, endpoint_id: int, body: WebhookEndpointUpdate
) -> WebhookEndpointOut:
    ep = _get(session, endpoint_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is not None or key == "description":
            setattr(ep, key, str(value) if key == "url" else value)
    session.commit()
    return _out(ep)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook_endpoint(session: SessionDep, endpoint_id: int) -> None:
    session.delete(_get(session, endpoint_id))
    session.commit()


@router.post("/{endpoint_id}/test", response_model=WebhookDeliveryOut)
def test_webhook_endpoint(
    services: ServicesDep, session: SessionDep, endpoint_id: int
) -> WebhookDeliveryOut:
    """Send a signed ``ping`` event synchronously and report the outcome."""
    _get(session, endpoint_id)
    payload = {"message": "Hello from InvoiceLens", "sent_at": services.clock().isoformat()}
    dispatcher = services.webhooks
    (delivery_id,) = dispatcher.enqueue(session, "ping", payload, endpoint_ids=[endpoint_id])
    session.commit()
    dispatcher.deliver(delivery_id)
    session.expire_all()
    return WebhookDeliveryOut.model_validate(session.get(WebhookDelivery, delivery_id))


@router.get("/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryOut])
def list_webhook_deliveries(session: SessionDep, endpoint_id: int) -> list[WebhookDeliveryOut]:
    _get(session, endpoint_id)
    rows = session.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == endpoint_id)
        .order_by(WebhookDelivery.id.desc())
        .limit(50)
    )
    return [WebhookDeliveryOut.model_validate(r) for r in rows]

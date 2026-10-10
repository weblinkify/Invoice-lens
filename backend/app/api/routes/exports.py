from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import ServicesDep, SessionDep
from app.core.errors import AppError
from app.db.models import Document, DocumentStatus
from app.services.exports import to_csv, to_xlsx

router = APIRouter(tags=["exports"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/exports",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}, XLSX: {}}}},
)
def export_documents(
    services: ServicesDep,
    session: SessionDep,
    format: Annotated[Literal["csv", "xlsx"], Query()] = "csv",
    ids: Annotated[
        str | None, Query(description="Comma-separated document ids; default: all approved")
    ] = None,
) -> Response:
    stmt = select(Document).options(selectinload(Document.extraction))
    if ids:
        wanted = [i.strip() for i in ids.split(",") if i.strip()]
        stmt = stmt.where(Document.id.in_(wanted))
    else:
        stmt = stmt.where(Document.status == DocumentStatus.APPROVED)
    docs = [d for d in session.scalars(stmt.order_by(Document.created_at)).all() if d.extraction]
    if ids and not docs:
        raise AppError(404, "None of the requested documents have extractions", code="not-found")
    stamp = services.clock().strftime("%Y%m%d-%H%M%S")
    if format == "xlsx":
        content, media_type = to_xlsx(docs), XLSX
    else:
        content, media_type = to_csv(docs), "text/csv; charset=utf-8"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="invoicelens-{stamp}.{format}"'},
    )

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import ServicesDep, SessionDep
from app.api.schemas import (
    CorrectionRequest,
    DocumentList,
    DocumentOut,
    ExtractionOut,
    UploadAccepted,
)
from app.core.errors import AppError, NotFoundError
from app.db.models import Document, DocumentStatus, Extraction
from app.domain.schema import InvoiceExtraction
from app.services.app_settings import get_threshold
from app.services.documents import create_document
from app.services.extractions import apply_corrections

router = APIRouter(prefix="/documents", tags=["documents"])


def load_document(session: Session, document_id: str) -> Document:
    doc = session.get(Document, document_id, options=[selectinload(Document.extraction)])
    if doc is None:
        raise NotFoundError("Document", document_id)
    return doc


def to_out(doc: Document) -> DocumentOut:
    out = DocumentOut.model_validate(doc)
    ext = doc.extraction
    if ext is not None:
        out.vendor_name = ext.vendor_name
        out.invoice_number = ext.invoice_number
        out.total = ext.total
        out.currency = ext.currency
        out.needs_review = ext.needs_review
        out.min_confidence = ext.min_confidence
    return out


def extraction_out(doc: Document, threshold: float) -> ExtractionOut:
    ext = doc.extraction
    if ext is None:
        raise AppError(409, f"Document is {doc.status}; no extraction yet", code="not-extracted")
    return ExtractionOut(
        document_id=doc.id,
        provider=ext.provider,
        threshold=threshold,
        data=InvoiceExtraction.model_validate(ext.data),
        corrected_fields=sorted((ext.overrides or {}).keys()),
        updated_at=ext.updated_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=UploadAccepted)
async def upload_document(
    services: ServicesDep,
    session: SessionDep,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File(description="Invoice PDF or image, max 10 MB")],
) -> UploadAccepted:
    data = await file.read(services.settings.max_upload_bytes + 1)
    doc = create_document(
        session,
        services.storage,
        filename=file.filename or "upload",
        declared_type=file.content_type,
        data=data,
        max_bytes=services.settings.max_upload_bytes,
    )
    background.add_task(services.pipeline.process, doc.id)
    return UploadAccepted(id=doc.id, status=doc.status, status_url=f"/api/v1/documents/{doc.id}")


@router.get("", response_model=DocumentList)
def list_documents(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    vendor: Annotated[str | None, Query(max_length=100)] = None,
    needs_review: bool | None = None,
    q: Annotated[str | None, Query(max_length=100, description="filename / invoice number")] = None,
) -> DocumentList:
    stmt = select(Document).outerjoin(Extraction)
    if status_filter is not None:
        stmt = stmt.where(Document.status == status_filter)
    if vendor:
        stmt = stmt.where(Extraction.vendor_name.ilike(f"%{vendor}%"))
    if needs_review is not None:
        stmt = stmt.where(Extraction.needs_review.is_(needs_review))
    if q:
        stmt = stmt.where(
            or_(Document.filename.ilike(f"%{q}%"), Extraction.invoice_number.ilike(f"%{q}%"))
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.scalars(
        stmt.options(selectinload(Document.extraction))
        .order_by(Document.created_at.desc(), Document.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return DocumentList(
        items=[to_out(d) for d in rows], total=total, page=page, page_size=page_size
    )


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(session: SessionDep, document_id: str) -> DocumentOut:
    return to_out(load_document(session, document_id))


@router.get(
    "/{document_id}/file",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}, "image/*": {}}}},
)
def get_document_file(services: ServicesDep, session: SessionDep, document_id: str) -> Response:
    doc = load_document(session, document_id)
    data = services.storage.read(doc.storage_key)
    return Response(
        content=data,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{doc.filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(services: ServicesDep, session: SessionDep, document_id: str) -> None:
    doc = load_document(session, document_id)
    services.storage.delete(doc.storage_key)
    session.delete(doc)
    session.commit()


@router.post(
    "/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED, response_model=UploadAccepted
)
def reprocess_document(
    services: ServicesDep, session: SessionDep, background: BackgroundTasks, document_id: str
) -> UploadAccepted:
    doc = load_document(session, document_id)
    if doc.status in (DocumentStatus.APPROVED, DocumentStatus.PROCESSING):
        raise AppError(409, f"Cannot reprocess a document that is {doc.status}", code="conflict")
    doc.status = DocumentStatus.QUEUED
    session.commit()
    background.add_task(services.pipeline.process, doc.id)
    return UploadAccepted(id=doc.id, status=doc.status, status_url=f"/api/v1/documents/{doc.id}")


@router.get("/{document_id}/extraction", response_model=ExtractionOut)
def get_extraction(services: ServicesDep, session: SessionDep, document_id: str) -> ExtractionOut:
    doc = load_document(session, document_id)
    return extraction_out(doc, get_threshold(session, services.settings.confidence_threshold))


@router.patch("/{document_id}/extraction", response_model=ExtractionOut)
def correct_extraction(
    services: ServicesDep, session: SessionDep, document_id: str, body: CorrectionRequest
) -> ExtractionOut:
    doc = load_document(session, document_id)
    if doc.status == DocumentStatus.APPROVED:
        raise AppError(409, "Approved documents are locked", code="document-locked")
    threshold = get_threshold(session, services.settings.confidence_threshold)
    inv = apply_corrections(session, doc, [(c.field, c.value) for c in body.corrections], threshold)
    doc.status = DocumentStatus.NEEDS_REVIEW if inv.needs_review else DocumentStatus.EXTRACTED
    session.commit()
    return extraction_out(doc, threshold)


@router.post("/{document_id}/approve", response_model=DocumentOut)
def approve_document(
    services: ServicesDep, session: SessionDep, background: BackgroundTasks, document_id: str
) -> DocumentOut:
    doc = load_document(session, document_id)
    if doc.status == DocumentStatus.APPROVED:
        raise AppError(409, "Document is already approved", code="already-approved")
    if doc.extraction is None or doc.status not in (
        DocumentStatus.NEEDS_REVIEW,
        DocumentStatus.EXTRACTED,
    ):
        raise AppError(
            409, f"Document is {doc.status} and cannot be approved", code="not-extracted"
        )
    doc.status = DocumentStatus.APPROVED
    doc.approved_at = services.clock()
    session.commit()
    return to_out(doc)

"""Extraction pipeline: storage → OCR → vendor few-shot → LLM → validation → persist."""

import logging
from dataclasses import dataclass

from app.core.config import Settings
from app.db.models import Document, DocumentStatus, Extraction
from app.db.session import SessionFactory
from app.llm.base import ExtractionRequest, LLMProvider
from app.llm.heuristics import attach_bboxes
from app.ocr.base import OcrEngine
from app.services.app_settings import get_threshold
from app.services.extractions import materialize, store
from app.services.storage import Storage
from app.services.vendors import detect_vendor, examples_for_vendor, upsert_vendor

log = logging.getLogger(__name__)


@dataclass
class ExtractionPipeline:
    settings: Settings
    session_factory: SessionFactory
    storage: Storage
    ocr: OcrEngine
    provider: LLMProvider

    def process(self, document_id: str) -> None:
        with self.session_factory() as session:
            doc = session.get(Document, document_id)
            if doc is None:
                log.warning(
                    "document vanished before processing", extra={"document_id": document_id}
                )
                return
            doc.status = DocumentStatus.PROCESSING
            doc.error = None
            session.commit()
            try:
                data = self.storage.read(doc.storage_key)
                ocr = self.ocr.extract(data, doc.content_type)
                doc.ocr_method = ocr.method
                doc.page_count = ocr.page_count or None
                known = detect_vendor(session, ocr.text)
                examples = (
                    examples_for_vendor(
                        session, known.id, doc.id, self.settings.fewshot_max_examples
                    )
                    if known
                    else []
                )
                raw = self.provider.extract(
                    ExtractionRequest(
                        filename=doc.filename,
                        data=data,
                        content_type=doc.content_type,
                        sha256=doc.sha256,
                        ocr=ocr,
                        examples=examples,
                        vendor_hint=known.name if known else None,
                    )
                )
                attach_bboxes(raw, ocr)
                threshold = get_threshold(session, self.settings.confidence_threshold)
                vendor = upsert_vendor(session, raw)
                doc.vendor_id = vendor.id if vendor else None
                extraction = doc.extraction or Extraction(document_id=doc.id)
                extraction.provider = self.provider.name
                extraction.raw = raw.model_dump(mode="json")
                extraction.overrides = {}
                inv = materialize(extraction.raw, {}, threshold)
                store(extraction, inv)
                if doc.extraction is None:
                    session.add(extraction)
                doc.status = (
                    DocumentStatus.NEEDS_REVIEW if inv.needs_review else DocumentStatus.EXTRACTED
                )
                session.commit()
                log.info(
                    "document extracted",
                    extra={
                        "document_id": doc.id,
                        "provider": self.provider.name,
                        "ocr": ocr.method,
                        "needs_review": inv.needs_review,
                        "fewshot_examples": len(examples),
                    },
                )
            except Exception as exc:
                session.rollback()
                doc = session.get(Document, document_id)
                if doc is not None:
                    doc.status = DocumentStatus.FAILED
                    doc.error = str(exc)[:2000]
                    session.commit()
                log.exception("extraction failed", extra={"document_id": document_id})

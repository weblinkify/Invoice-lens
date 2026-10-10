"""Service container: every side-effecting dependency lives here so tests can swap it."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app.core.config import Settings
from app.db.base import utcnow
from app.db.session import SessionFactory, make_engine, make_session_factory
from app.llm.base import LLMProvider
from app.llm.factory import build_provider
from app.llm.truth import TruthIndex
from app.ocr.base import OcrEngine
from app.ocr.engines import build_ocr_engine
from app.services.pipeline import ExtractionPipeline
from app.services.storage import LocalStorage, Storage
from app.services.webhooks import WebhookDispatcher


@dataclass
class Services:
    settings: Settings
    session_factory: SessionFactory
    storage: Storage
    ocr: OcrEngine
    provider: LLMProvider
    truth: TruthIndex
    clock: Callable[[], datetime] = field(default=utcnow)
    http_client_factory: Callable[[], httpx.Client] | None = None
    sleep: Callable[[float], None] = time.sleep

    @property
    def pipeline(self) -> ExtractionPipeline:
        return ExtractionPipeline(
            self.settings, self.session_factory, self.storage, self.ocr, self.provider
        )

    @property
    def webhooks(self) -> WebhookDispatcher:
        timeout = self.settings.webhook_timeout_seconds
        return WebhookDispatcher(
            session_factory=self.session_factory,
            client_factory=self.http_client_factory or (lambda: httpx.Client(timeout=timeout)),
            clock=self.clock,
            sleep=self.sleep,
            max_attempts=self.settings.webhook_max_attempts,
            backoff_base=self.settings.webhook_backoff_base_seconds,
        )


def build_services(settings: Settings) -> Services:
    truth = TruthIndex(settings.fixtures_dirs)
    return Services(
        settings=settings,
        session_factory=make_session_factory(make_engine(settings.database_url)),
        storage=LocalStorage(settings.storage_dir),
        ocr=build_ocr_engine(settings.ocr_engine, settings.tesseract_cmd),
        provider=build_provider(settings, truth),
        truth=truth,
    )

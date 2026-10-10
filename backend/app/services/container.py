"""Service container: every side-effecting dependency lives here so tests can swap it."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

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


@dataclass
class Services:
    settings: Settings
    session_factory: SessionFactory
    storage: Storage
    ocr: OcrEngine
    provider: LLMProvider
    truth: TruthIndex
    clock: Callable[[], datetime] = field(default=utcnow)

    @property
    def pipeline(self) -> ExtractionPipeline:
        return ExtractionPipeline(
            self.settings, self.session_factory, self.storage, self.ocr, self.provider
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

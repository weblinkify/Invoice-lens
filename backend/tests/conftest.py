from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.db.session import make_engine, make_session_factory
from app.llm.base import LLMProvider
from app.llm.mock import MockProvider
from app.llm.truth import TruthIndex
from app.main import create_app
from app.ocr.engines import PdfTextEngine
from app.services.container import Services
from app.services.storage import MemoryStorage

FIXTURES = Path(__file__).parent / "fixtures" / "invoices"
FIXED_NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def fixture_pdfs() -> list[Path]:
    return sorted(FIXTURES.glob("*.pdf"))


@pytest.fixture(scope="session")
def truth_index() -> TruthIndex:
    return TruthIndex([FIXTURES])


def fixture_path(fragment: str) -> Path:
    return next(p for p in sorted(FIXTURES.glob("*.pdf")) if fragment in p.name)


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "database_url": "sqlite://",
        "log_json": False,
        "log_level": "WARNING",
        "fixtures_dirs": [FIXTURES],
        "sample_data_dir": FIXTURES,
        "webhook_backoff_base_seconds": 0.0,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def make_services(
    settings: Settings, truth: TruthIndex, provider: LLMProvider | None = None
) -> Services:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return Services(
        settings=settings,
        session_factory=make_session_factory(engine),
        storage=MemoryStorage(),
        ocr=PdfTextEngine(),
        provider=provider or MockProvider(truth, seed=settings.mock_seed),
        truth=truth,
        clock=lambda: FIXED_NOW,
    )


ClientFactory = Callable[..., TestClient]


@pytest.fixture
def client_factory(truth_index: TruthIndex) -> Iterator[ClientFactory]:
    clients: list[TestClient] = []

    def factory(provider: LLMProvider | None = None, **overrides: object) -> TestClient:
        services = make_services(make_settings(**overrides), truth_index, provider)
        client = TestClient(create_app(services=services))
        clients.append(client)
        return client

    yield factory
    for c in clients:
        c.close()


@pytest.fixture
def client(client_factory: ClientFactory) -> TestClient:
    return client_factory()


@pytest.fixture
def services(client: TestClient) -> Services:
    svc: Services = client.app.state.services  # type: ignore[attr-defined]
    return svc

from pathlib import Path

import pytest

from app.llm.truth import TruthIndex

FIXTURES = Path(__file__).parent / "fixtures" / "invoices"


@pytest.fixture(scope="session")
def fixture_pdfs() -> list[Path]:
    return sorted(FIXTURES.glob("*.pdf"))


@pytest.fixture(scope="session")
def truth_index() -> TruthIndex:
    return TruthIndex([FIXTURES])


def fixture_path(fragment: str) -> Path:
    return next(p for p in sorted(FIXTURES.glob("*.pdf")) if fragment in p.name)

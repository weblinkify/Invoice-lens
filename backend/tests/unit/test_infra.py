import json
import logging
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from app.core.config import BACKEND_DIR
from app.core.logging import JsonFormatter, configure_logging
from app.db.session import make_engine
from app.services.container import build_services
from app.services.storage import LocalStorage
from tests.conftest import make_settings


def test_alembic_upgrade_and_downgrade(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    tables = set(inspect(make_engine(url)).get_table_names())
    assert {
        "documents",
        "extractions",
        "field_corrections",
        "vendors",
        "webhook_endpoints",
        "webhook_deliveries",
        "app_settings",
    } <= tables
    command.check(cfg)  # models and migrations agree
    command.downgrade(cfg, "base")
    assert "documents" not in inspect(make_engine(url)).get_table_names()


def test_local_storage(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "blobs")
    storage.save("ab/doc.pdf", b"data")
    assert storage.read("ab/doc.pdf") == b"data"
    storage.delete("ab/doc.pdf")
    storage.delete("ab/doc.pdf")
    with pytest.raises(ValueError, match="invalid storage key"):
        storage.save("../escape", b"x")


def test_build_services(tmp_path: Path) -> None:
    settings = make_settings(
        database_url=f"sqlite:///{tmp_path / 'x.db'}", storage_dir=tmp_path / "s"
    )
    services = build_services(settings)
    assert services.provider.name == "mock"
    assert services.pipeline.provider is services.provider


def test_json_logging(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_output=True)
    try:
        raise ValueError("bad")
    except ValueError:
        logging.getLogger("t").exception("boom", extra={"document_id": "d1"})
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["msg"] == "boom"
    assert line["document_id"] == "d1"
    assert "ValueError" in line["exc"]
    configure_logging("WARNING", json_output=False)
    assert isinstance(JsonFormatter().format(logging.makeLogRecord({"msg": "x"})), str)

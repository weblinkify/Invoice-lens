"""Application settings. Every runtime knob comes from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "InvoiceLens"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = f"sqlite:///{BACKEND_DIR / 'invoicelens.db'}"
    storage_dir: Path = BACKEND_DIR / "storage"
    max_upload_bytes: int = 10 * 1024 * 1024

    demo_mode: bool = True
    api_key: str | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    llm_provider: Literal["mock", "anthropic", "openai"] = "mock"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0

    ocr_engine: Literal["auto", "pdf", "none"] = "auto"
    tesseract_cmd: str | None = None

    confidence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    fewshot_max_examples: int = 3

    mock_seed: int = 42
    fixtures_dirs: list[Path] = Field(
        default_factory=lambda: [
            BACKEND_DIR / "tests" / "fixtures" / "invoices",
            REPO_DIR / "sample-data",
        ]
    )
    sample_data_dir: Path = REPO_DIR / "sample-data"

    webhook_max_attempts: int = 5
    webhook_backoff_base_seconds: float = 0.5
    webhook_timeout_seconds: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

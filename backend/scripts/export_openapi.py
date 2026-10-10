"""Write the FastAPI OpenAPI schema to a file (input for the frontend type generator).

Usage: ``uv run python -m scripts.export_openapi ../frontend/openapi.json``
"""

import json
import sys
import tempfile
from pathlib import Path

from app.core.config import Settings
from app.main import create_app


def export(path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            database_url="sqlite://", storage_dir=Path(tmp), log_json=False, log_level="WARNING"
        )
        schema = create_app(settings).openapi()
    path.write_text(json.dumps(schema, indent=2, sort_keys=False) + "\n")


if __name__ == "__main__":
    export(Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json"))

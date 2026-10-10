"""Ground-truth lookup for generated mock invoices (``*.truth.json`` next to each PDF)."""

import hashlib
import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.domain.schema import (
    HEADER_FIELDS,
    LINE_ITEM_FIELDS,
    InvoiceExtraction,
    LineItem,
    field_kind,
)

log = logging.getLogger(__name__)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def truth_path_for(pdf: Path) -> Path:
    return pdf.with_name(pdf.stem + ".truth.json")


class TruthIndex:
    """Maps document SHA-256 (and file name) to ground truth. Built lazily, then cached."""

    def __init__(self, dirs: Iterable[Path]) -> None:
        self._dirs = [Path(d) for d in dirs]
        self._by_hash: dict[str, Path] | None = None
        self._by_name: dict[str, Path] = {}

    def _build(self) -> dict[str, Path]:
        if self._by_hash is None:
            self._by_hash = {}
            for directory in self._dirs:
                if not directory.is_dir():
                    continue
                for pdf in sorted(directory.glob("*.pdf")):
                    truth = truth_path_for(pdf)
                    if truth.exists():
                        self._by_hash.setdefault(sha256_bytes(pdf.read_bytes()), truth)
                        self._by_name.setdefault(pdf.name, truth)
            log.info("truth index built", extra={"documents": len(self._by_hash)})
        return self._by_hash

    def lookup(self, sha256: str) -> dict[str, Any] | None:
        path = self._build().get(sha256)
        return load_truth(path) if path else None

    def lookup_name(self, filename: str) -> dict[str, Any] | None:
        self._build()
        path = self._by_name.get(filename)
        return load_truth(path) if path else None

    def __len__(self) -> int:
        return len(self._build())


def load_truth(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def truth_to_extraction(truth: dict[str, Any], confidence: float = 1.0) -> InvoiceExtraction:
    """Convert a truth file into a schema object with a uniform confidence."""
    fields: dict[str, Any] = truth["fields"]

    def build(path: str, raw: dict[str, Any]) -> Any:
        kind = field_kind(path)
        return kind.model_validate({**raw, "confidence": confidence})

    inv = InvoiceExtraction(**{name: build(name, fields[name]) for name in HEADER_FIELDS})
    inv.line_items = [
        LineItem(**{name: build(f"line_items.0.{name}", item[name]) for name in LINE_ITEM_FIELDS})
        for item in fields.get("line_items", [])
    ]
    return inv

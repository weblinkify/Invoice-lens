"""Document blob storage. Local filesystem now; swap for S3 behind the same protocol."""

from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"invalid storage key: {key}")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class MemoryStorage:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> None:
        self.blobs[key] = data

    def read(self, key: str) -> bytes:
        return self.blobs[key]

    def delete(self, key: str) -> None:
        self.blobs.pop(key, None)

"""Object storage abstraction.

V1 ships a local-filesystem backend; the interface mirrors the small subset
of S3 semantics we need (put/get with content-addressed keys). Swapping in an
S3-compatible backend later must not require changes outside this module.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from app.config import settings


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> str:
        """Stores bytes; returns the abstract URI of the artifact."""
        ...

    def get(self, key: str) -> bytes: ...
    def path_of(self, key: str) -> Path: ...


class LocalFilesystemStore:
    """Development backend under `storage_dir`.

    Keys are content-addressed (`raw/<sha256>.xml`) and returned URIs use the
    `storage:` scheme so stored `raw_artifact_uri` values never leak the
    physical filesystem layout.
    """

    def __init__(self, root: Path | None = None, prefix: str | None = None):
        self.root = Path(root or settings.storage_dir)
        self.prefix = prefix or settings.raw_prefix
        self._allowed = ("raw", "exports")
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        head, _, rest = key.partition("/")
        if head not in self._allowed or not rest or "/" in rest or ".." in key:
            raise ValueError(f"invalid storage key: {key!r}")
        return self.root / head / rest

    def put(self, key: str, data: bytes) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        return f"storage://{key}"

    def get(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def path_of(self, key: str) -> Path:
        return self._resolve(key)

    @staticmethod
    def content_key(data: bytes, extension: str = "xml") -> str:
        digest = hashlib.sha256(data).hexdigest()
        return f"raw/{digest}.{extension}"

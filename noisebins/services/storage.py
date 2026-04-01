from __future__ import annotations

import uuid
from pathlib import Path

from noisebins.config import get_settings


class BlobStorage:
    def store_bytes(self, data: bytes, content_type: str | None) -> str:  # noqa: ARG002
        raise NotImplementedError

    def public_url(self, key: str) -> str:
        raise NotImplementedError

    def get_path(self, key: str) -> Path | None:
        return None


class LocalBlobStorage(BlobStorage):
    def __init__(self, root: Path, public_base: str) -> None:
        self.root = root
        self.public_base = public_base.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def store_bytes(self, data: bytes, content_type: str | None) -> str:  # noqa: ARG002
        key = f"{uuid.uuid4().hex}"
        path = self.root / key
        path.write_bytes(data)
        return key

    def public_url(self, key: str) -> str:
        return f"{self.public_base}/media/{key}"

    def get_path(self, key: str) -> Path:
        return self.root / key


def get_storage() -> BlobStorage:
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalBlobStorage(Path(settings.local_storage_path), settings.public_base_url)
    raise NotImplementedError(f"Unknown storage backend: {settings.storage_backend}")

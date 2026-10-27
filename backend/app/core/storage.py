"""File storage addressed by relative keys (never absolute paths or public URLs).

LocalStorage keeps files under a storage root (development, tests, single-server deployments).
BlobStorage keeps them in a private Vercel Blob store (serverless deployments); every read goes
through the API so ownership checks always apply.
"""
import shutil
from pathlib import Path, PurePosixPath
from typing import Protocol

from app.core.config import get_settings


def check_key(key: str) -> str:
    parts = PurePosixPath(key.replace("\\", "/")).parts
    if not parts or key.startswith(("/", "\\")) or ".." in parts or ":" in key:
        raise ValueError("storage key escapes the storage root")
    return "/".join(parts)


class StorageBackend(Protocol):
    def save_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    def read_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def delete_tree(self, prefix: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path | None = None) -> None:
        self._root_override = root

    @property
    def root(self) -> Path:
        return Path(self._root_override or get_settings().storage_root).resolve()

    def path(self, key: str) -> Path:
        target = (self.root / check_key(key)).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("storage key escapes the storage root")
        return target

    def save_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)
        return key

    def read_bytes(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def exists(self, key: str) -> bool:
        p = self.path(key)
        return p.is_file() and p.stat().st_size > 0

    def delete(self, key: str) -> None:
        p = self.path(key)
        if p.is_file():
            p.unlink()

    def delete_tree(self, prefix: str) -> None:
        p = self.path(prefix)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


class BlobStorage:
    """Private Vercel Blob store. Credentials come from the environment (OIDC + BLOB_STORE_ID, or token)."""

    def save_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        from vercel.blob.sync import put_blob

        put_blob(check_key(key), data, access="private", content_type=content_type, allow_overwrite=True)
        return key

    def read_bytes(self, key: str) -> bytes:
        from vercel.blob.sync import get_blob

        try:
            return get_blob(check_key(key), access="private").body
        except Exception as exc:
            if type(exc).__name__ == "BlobNotFoundError":
                raise FileNotFoundError(key) from exc
            raise

    def exists(self, key: str) -> bool:
        from vercel.blob.sync import head_blob

        try:
            head_blob(check_key(key))
            return True
        except Exception as exc:
            if type(exc).__name__ == "BlobNotFoundError":
                return False
            raise

    def delete(self, key: str) -> None:
        from vercel.blob.sync import delete_blob

        delete_blob(check_key(key))

    def delete_tree(self, prefix: str) -> None:
        from vercel.blob.sync import delete_blob, query_blobs

        names = [b.pathname for b in query_blobs(prefix=check_key(prefix).rstrip("/") + "/")]
        for i in range(0, len(names), 100):
            delete_blob(names[i : i + 100])


class _Storage:
    """Picks the backend from settings on each call, so tests and config changes take effect."""

    _local = LocalStorage()
    _blob = BlobStorage()

    @property
    def backend(self) -> StorageBackend:
        return self._blob if get_settings().use_blob else self._local

    @property
    def root(self) -> Path:  # local backend only (tests, dev tooling)
        return self._local.root

    def save_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        return self.backend.save_bytes(key, data, content_type)

    def read_bytes(self, key: str) -> bytes:
        return self.backend.read_bytes(key)

    def exists(self, key: str) -> bool:
        return self.backend.exists(key)

    def delete(self, key: str) -> None:
        self.backend.delete(key)

    def delete_tree(self, prefix: str) -> None:
        self.backend.delete_tree(prefix)

    def path(self, key: str) -> Path:  # local backend only
        return self._local.path(key)


storage = _Storage()

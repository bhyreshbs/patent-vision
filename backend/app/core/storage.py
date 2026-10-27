import shutil
from pathlib import Path

from app.core.config import get_settings


class Storage:
    """File storage addressed by keys relative to a storage root (never absolute paths)."""

    def __init__(self, root: Path | None = None) -> None:
        self._root_override = root

    @property
    def root(self) -> Path:
        root = self._root_override or get_settings().storage_root
        return Path(root).resolve()

    def path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("storage key escapes the storage root")
        return target

    def save_bytes(self, key: str, data: bytes) -> str:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)
        return key

    def exists(self, key: str) -> bool:
        p = self.path(key)
        return p.is_file() and p.stat().st_size > 0

    def read_bytes(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def delete(self, key: str) -> None:
        p = self.path(key)
        if p.is_file():
            p.unlink()

    def delete_tree(self, prefix: str) -> None:
        p = self.path(prefix)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


storage = Storage()

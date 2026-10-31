"""Content-addressed local blob store (development + single-node deployment).

Keys are ``<sha256[0:2]>/<sha256>`` under a configured root; the root itself is
never derived from client input. Writes go to a temporary file first and are
atomically published, so a crash cannot leave a truncated blob under the final
key.
"""
from __future__ import annotations

import os
from pathlib import Path


class LocalBlobStore:
    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        candidate = (self._root / storage_key).resolve()
        if not str(candidate).startswith(str(self._root.resolve())):
            raise ValueError("storage key escapes the blob root")
        return candidate

    async def put(self, data: bytes, sha256: str) -> str:
        key = f"{sha256[:2]}/{sha256}"
        target = self._path(key)
        if target.exists():
            return key  # content-addressed: identical bytes are already stored
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, target)
        return key

    async def get(self, storage_key: str) -> bytes:
        return self._path(storage_key).read_bytes()

    def exists(self, storage_key: str) -> bool:
        return self._path(storage_key).exists()

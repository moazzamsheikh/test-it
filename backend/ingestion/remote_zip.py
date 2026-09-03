"""Read individual entries out of a large remote ZIP via HTTP range requests,
without downloading the whole archive (see DECISIONS.md: the real PAG
datasets are 400MB-2GB, but the GML/DOCX entries we actually need are a few
KB-MB each). Only works efficiently when the ZIP's entries are stored
uncompressed (`compress_type == ZIP_STORED`) — verified true for both real
PAG datasets ingested here; falls back to a normal (slower, full-entry)
read otherwise, since Python's zipfile still handles that correctly, just
by pulling the whole compressed entry regardless of range efficiency.
"""

from __future__ import annotations

import zipfile

import httpx


class RemoteZipFile:
    """A read-only, seekable file-like object over a remote URL, backed by
    HTTP range requests — enough for `zipfile.ZipFile` to open it directly."""

    def __init__(self, url: str, user_agent: str) -> None:
        self._url = url
        self._client = httpx.Client(headers={"User-Agent": user_agent}, timeout=60)
        head = self._client.head(url, follow_redirects=True)
        head.raise_for_status()
        self._size = int(head.headers["content-length"])
        self._pos = 0

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._size + offset
        return self._pos

    def tell(self) -> int:
        return self._pos

    def read(self, n: int = -1) -> bytes:
        end = self._size - 1 if n == -1 else min(self._pos + n - 1, self._size - 1)
        if self._pos > end:
            return b""
        response = self._client.get(
            self._url, headers={"Range": f"bytes={self._pos}-{end}"}, follow_redirects=True
        )
        response.raise_for_status()
        data = response.content
        self._pos += len(data)
        return data

    def close(self) -> None:
        self._client.close()


def open_remote_zip(url: str, user_agent: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(RemoteZipFile(url, user_agent))

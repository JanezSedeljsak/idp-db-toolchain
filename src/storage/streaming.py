from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import IO, cast

import zstandard as zstd

CHUNK_SIZE = 64 * 1024


class IterReader:
    """Minimal file-like reader over an iterator of byte chunks (for zstd stream_reader)."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._iter = iter(chunks)
        self._buf = b""

    def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        if size < 0:
            parts = [self._buf, *self._iter]
            self._buf = b""
            return b"".join(parts)
        while len(self._buf) < size:
            try:
                self._buf += next(self._iter)
            except StopIteration:
                break
        out, self._buf = self._buf[:size], self._buf[size:]
        return out


class _HashingWriter:
    def __init__(self, fh) -> None:
        self._fh = fh
        self._hasher = hashlib.sha256()
        self.size = 0

    def write(self, data: bytes) -> int:
        self._hasher.update(data)
        self.size += len(data)
        written = self._fh.write(data)
        return int(written)

    def flush(self) -> None:
        self._fh.flush()

    @property
    def digest(self) -> str:
        return self._hasher.hexdigest()


def compress_chunks_to_file(chunks: Iterator[bytes], path: Path, *, level: int) -> tuple[int, str]:
    with path.open("wb") as raw_fh:
        hasher = _HashingWriter(raw_fh)
        compressor = zstd.ZstdCompressor(level=level)
        with compressor.stream_writer(cast(IO[bytes], hasher)) as writer:
            for chunk in chunks:
                writer.write(chunk)
    return hasher.size, hasher.digest


def hash_file(path: Path, *, chunk_size: int = CHUNK_SIZE) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk_size)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()


def iter_decompressed_file(path: Path, *, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
    with path.open("rb") as fh:
        reader = zstd.ZstdDecompressor().stream_reader(fh)
        while True:
            block = reader.read(chunk_size)
            if not block:
                break
            yield block


def iter_decompressed_chunks(
    chunks: Iterator[bytes], *, chunk_size: int = CHUNK_SIZE
) -> Iterator[bytes]:
    reader = zstd.ZstdDecompressor().stream_reader(cast(IO[bytes], IterReader(chunks)))
    while True:
        block = reader.read(chunk_size)
        if not block:
            break
        yield block

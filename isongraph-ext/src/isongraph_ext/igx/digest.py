"""Digest framing (17 §2.1). Everything IGX/1 hashes goes through here so the framing has one home."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_hex(data: bytes | str) -> str:
    """sha256 of exactly these bytes; a str is UTF-8 encoded as given (no normalisation)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_hex(Path(path).read_bytes())


def normalize_newlines(data: bytes) -> bytes:
    """CRLF -> LF. Used only by V0 (module source identity); never for artifacts or bindings."""
    return data.replace(b"\r\n", b"\n")


def corpus_digest(root: Path) -> str:
    """Core's scripts/corpus_digest.py algorithm, reproduced so the pin can be re-derived here."""
    root = Path(root)
    h = hashlib.sha256()
    files = sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix())
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        h.update(rel + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()

"""Shared CLI helpers: bounded input reads and atomic output writes."""

from __future__ import annotations

import os
from pathlib import Path


def read_capped(path: Path, limit: int) -> bytes:
    """At most ``limit + 1`` bytes of ``path``: one byte past the budget is enough for the library to refuse it with its own budget error."""
    with open(path, "rb") as fh:
        return fh.read(limit + 1)


def write_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to a sibling temp file, then rename it over ``path``: a reader never sees a half-written file."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

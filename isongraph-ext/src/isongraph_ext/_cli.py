"""Shared CLI input helper: read a file within a byte budget instead of loading it whole first."""

from __future__ import annotations

from pathlib import Path


def read_capped(path: Path, limit: int) -> bytes:
    """At most ``limit + 1`` bytes of ``path``: one byte past the budget is enough for the library to refuse it with its own budget error."""
    with open(path, "rb") as fh:
        return fh.read(limit + 1)

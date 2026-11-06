"""Capability version ranges (17 §2): =X.Y.Z | ^X[.Y[.Z]] | ~X.Y[.Z] | >=X.Y.Z with conventional SemVer meaning."""

from __future__ import annotations

import re
from dataclasses import dataclass

Version = tuple[int, int, int]
_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_RANGE = re.compile(r"^(=|>=|\^|~)((?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){0,2})$")


def parse_version(text: str) -> Version:
    m = _VERSION.fullmatch(text)   # fullmatch: `$` alone would accept a trailing newline
    if not m:
        raise ValueError(f"not a version X.Y.Z: {text!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


@dataclass(frozen=True)
class Range:
    op: str
    parts: tuple[int, ...]


def parse_range(text: str) -> Range:
    m = _RANGE.fullmatch(text)
    if not m:
        raise ValueError(f"not a version range: {text!r}")
    op, parts = m.group(1), tuple(int(p) for p in m.group(2).split("."))
    if op in ("=", ">=") and len(parts) != 3:
        raise ValueError(f"{op} needs X.Y.Z: {text!r}")
    if op == "~" and len(parts) < 2:
        raise ValueError(f"~ needs X.Y[.Z]: {text!r}")
    return Range(op, parts)


def _pad(parts: tuple[int, ...]) -> Version:
    padded = tuple(parts) + (0, 0, 0)
    return (padded[0], padded[1], padded[2])


def _caret_upper(parts: tuple[int, ...]) -> Version:
    """Conventional SemVer caret: bump the left-most non-zero component; if all given are zero, bump the last given."""
    p = list(parts)
    for i, value in enumerate(p):
        if value != 0:
            return _pad(tuple(p[:i] + [value + 1]))
    return _pad(tuple(p[:-1] + [p[-1] + 1]))


def range_admits(r: Range, v: Version) -> bool:
    lo = _pad(r.parts)
    if r.op == "=":
        return v == lo
    if r.op == ">=":
        return v >= lo
    if r.op == "^":
        return lo <= v < _caret_upper(r.parts)
    return lo <= v < (r.parts[0], r.parts[1] + 1, 0)  # "~"

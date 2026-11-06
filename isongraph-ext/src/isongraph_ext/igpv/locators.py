"""Source locators (18 §2): shape rule (P1) and verification posture (P5). Posture is derived, never stored."""

from __future__ import annotations

from . import records as R
from .errors import IGPVError


def line_count(data: bytes) -> int:
    """LF-delimited lines; a CR before the LF belongs to the line; a final line needs no LF; b'' has none."""
    n = data.count(b"\n")
    if data and not data.endswith(b"\n"):
        n += 1
    return n


def check_locator_shape(loc: R.Locator | None, size: int, where: str) -> None:
    def bad(col: str, detail: str) -> None:
        raise IGPVError("MALFORMED_PROVENANCE", f"{where}.{col}", detail, "P1")

    if loc is None:
        return
    t = loc.type
    if not R.is_str(t):
        bad("locator_type", "null, bytes/1, lines/1 or x-<name>/<n>")
    if t in R.LOCATOR_SPAN_TYPES:
        if loc.text is not None:
            bad("locator_text", f"must be null for {t}")
        if not (R.is_int(loc.start) and R.is_int(loc.end)):
            bad("locator_start", f"{t} needs integer start and end")
        lo = 0 if t == "bytes/1" else 1
        if not (lo <= loc.start <= loc.end <= size):
            bad("locator_end", f"{t} needs {lo} <= start <= end <= size ({size}); got [{loc.start}, {loc.end}]")
    elif R.X_LOCATOR.fullmatch(t):
        if loc.start is not None or loc.end is not None:
            bad("locator_start", "must be null for x-* locators")
        if not (R.is_str(loc.text) and loc.text != ""):
            bad("locator_text", "non-empty string required for x-* locators")
    else:
        bad("locator_type", "null, bytes/1, lines/1 or x-<name>/<n>")


def locator_posture(loc: R.Locator, data: bytes | None, where: str, *, line_total: int | None = None) -> str:
    """P5. `data` is the artifact's bytes when supplied (already digest/size-checked by the caller), else None.
    `line_total` lets the caller cache line_count(data) across the attributions of one artifact."""
    if data is None or loc.type not in R.LOCATOR_SPAN_TYPES:
        return "UNVERIFIED"
    limit = len(data) if loc.type == "bytes/1" else (line_count(data) if line_total is None else line_total)
    if loc.end > limit:
        raise IGPVError("LOCATOR_INVALID", f"{where}.locator_end", f"{loc.type} end {loc.end} > {limit}", "P5")
    return "VERIFIED"

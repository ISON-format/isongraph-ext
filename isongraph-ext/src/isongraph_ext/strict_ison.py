"""Strict canonical-ISON reader shared by IGDC/1 (26 §4, C0-C1) and IGAR/1 (25 §3, R0-R1).

ison-py parses more than these contracts allow, and what it accepts is not always visible afterwards (probed against ison-py 1.2.0):
a repeated column header is kept in ``Block.fields`` while the row dict silently keeps the LAST value; a short row is padded with
``None``; ``---`` summary lines, ``name:int`` / ``name:computed`` column declarations and ``:ref`` cells parse without error, and
the canonical writer re-emits all of them unchanged. So a byte-for-byte re-emission check alone does not prove a document has the
shape a contract names. This module is that shape check, written once, with the byte budget applied BEFORE any parsing.

It knows nothing about IGDC or IGAR vocabularies; callers pass the exact blocks and columns they allow.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ison_parser import dumps_canonical, loads

_SCALARS = (str, int, float, bool, type(None))      # exact types only: ison-py's Reference (":user:7") is none of them


class StrictError(Exception):
    """``stage`` is "bytes" (C0/R0) or "shape" (C1/R1); ``kind`` is "malformed" or "limit"."""

    def __init__(self, stage: str, kind: str, field: str, detail: str) -> None:
        super().__init__(f"{stage} {kind} {field}: {detail}")
        self.stage, self.kind, self.field, self.detail = stage, kind, field, detail


@dataclass(frozen=True)
class BlockShape:
    kind: str                       # "meta" | "table"
    name: str
    fields: tuple[str, ...]         # the exact column set; declared order is irrelevant here (the canonical writer sorts)
    single_row: bool = False        # meta blocks: exactly one row


def _bytes_fail(kind: str, field: str, detail: str) -> StrictError:
    return StrictError("bytes", kind, field, detail)


def _shape_fail(field: str, detail: str) -> StrictError:
    return StrictError("shape", "malformed", field, detail)


def read_canonical(data: bytes | str, shapes: Sequence[BlockShape], *, max_bytes: int, max_rows: int) -> tuple[str, dict[tuple[str, str], list[dict]]]:
    """Return ``(text, rows_by_block)`` for a document that is canonical AND has exactly the allowed shape, or raise StrictError.

    Order, first failure wins: byte budget (before any decoding or parsing) -> UTF-8 -> CR / BOM -> parse -> canonical re-emission
    -> block set -> column declarations -> summary / typed columns -> row budget and cardinality -> cell types.
    """
    if isinstance(data, str):
        try:
            raw = data.encode("utf-8")
        except UnicodeEncodeError as e:
            raise _bytes_fail("malformed", "document", f"text is not UTF-8-encodable: {e}") from None
    elif isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    else:
        raise TypeError(f"data must be bytes or str, got {type(data).__name__}")
    if len(raw) > max_bytes:                                                    # budget first: nothing below runs on oversize input
        raise _bytes_fail("limit", "size", f"{len(raw)} bytes > {max_bytes}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise _bytes_fail("malformed", "document", f"not UTF-8: {e}") from None
    if text.startswith("\ufeff"):
        raise _bytes_fail("malformed", "canonical_form", "byte-order mark present")
    if "\r" in text:
        raise _bytes_fail("malformed", "canonical_form", "CR bytes present; the canonical writer emits LF only")
    try:
        doc = loads(text)
        again = dumps_canonical(doc)
    except Exception as e:                                                      # any parser or writer fault is "not a document"
        raise _bytes_fail("malformed", "document", f"not ISON: {e}") from None
    if again != text:
        raise _bytes_fail("malformed", "canonical_form", "bytes are not the canonical writer's output")

    allowed = {(s.kind, s.name): s for s in shapes}
    found: dict[tuple[str, str], object] = {}
    for b in doc.blocks:
        key = (b.kind, b.name)
        if key not in allowed:
            raise _shape_fail(f"{b.kind}.{b.name}", "unexpected block")
        if key in found:
            raise _shape_fail(f"{b.kind}.{b.name}", "duplicate block")
        found[key] = b
    out: dict[tuple[str, str], list[dict]] = {}
    for key, shape in allowed.items():
        b = found.get(key)
        where = f"{key[0]}.{key[1]}"
        if b is None:
            raise _shape_fail(where, "missing block")
        declared = list(b.fields)
        seen: set[str] = set()
        repeated: set[str] = set()
        for name in declared:                                                   # one O(n) pass; list.count per column was O(n^2)
            (repeated if name in seen else seen).add(name)
        if repeated:
            first = next(name for name in declared if name in repeated)         # first declared name that is repeated, as before
            raise _shape_fail(f"{where}.{first}", "column declared more than once")
        if set(declared) != set(shape.fields):
            missing, extra = sorted(set(shape.fields) - set(declared)), sorted(set(declared) - set(shape.fields))
            raise _shape_fail(where, f"columns differ from the contract (missing {missing}, unexpected {extra})")
        if getattr(b, "summary", None) is not None:
            raise _shape_fail(where, "summary row (---) is not part of this contract")
        for fi in b.field_info:
            if fi.type is not None or fi.is_computed:
                raise _shape_fail(f"{where}.{fi.name}", "typed or computed column declaration is not part of this contract")
        if len(b.rows) > max_rows:
            raise StrictError("shape", "limit", "max_rows_per_table", f"{where} has {len(b.rows)} rows > {max_rows}")
        if shape.single_row and len(b.rows) != 1:
            raise _shape_fail(where, "exactly one row required")
        for row in b.rows:
            if set(row) != set(shape.fields):
                raise _shape_fail(where, "a row does not carry exactly the declared columns")
            for col, v in row.items():
                if type(v) not in _SCALARS:
                    raise _shape_fail(f"{where}.{col}", f"cell is not a scalar ({type(v).__name__})")
                if isinstance(v, float) and not math.isfinite(v):
                    raise _shape_fail(f"{where}.{col}", "non-finite number")
        out[key] = [dict(r) for r in b.rows]
    return text, out

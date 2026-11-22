# isongraph-ext/src/isongraph_ext/igdc/address.py
"""Typed-address mapping into igs-addr/1 (26 §1). Reads the TYPE of a value, never its spelling."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..igpv.records import INT64_MAX, INT64_MIN, EdgeAddress, NodeRef, is_identifier, is_int, is_str
from ..igpv.resolve import canonical_endpoints, node_ref_key
from .errors import IGDCError

_INT64_DECIMAL = re.compile(r"0|-?[1-9][0-9]*")      # ASCII digits only; no -0, +5, leading zeros
_ORDINAL = re.compile(r"0|[1-9][0-9]*")


def _bad(field: str, detail: str) -> IGDCError:
    return IGDCError("INVALID_ADDRESS", field, detail, "C2")


def _utf8_ok(s: str) -> bool:
    try:
        s.encode("utf-8")
        return True
    except UnicodeEncodeError:
        return False


def tag_id(v: int | str) -> str:
    if is_int(v):
        if not INT64_MIN <= v <= INT64_MAX:
            raise _bad("node_id", f"integer {v} lies outside INT64")
        return f"i:{v}"
    if is_str(v):
        if not _utf8_ok(v):
            raise _bad("node_id", "string is not UTF-8-encodable (lone surrogate)")
        return f"s:{v}"
    raise _bad("node_id", "id must be an INT64 integer or a string (booleans, floats, null, bytes are not ids)")


def parse_id(tag: str) -> int | str:
    if not is_str(tag) or tag[:2] not in ("i:", "s:"):
        raise _bad("node_id", "a tagged id starts with 'i:' or 's:'; a bare value is not an identity")
    body = tag[2:]
    if tag[0] == "s":
        if not _utf8_ok(body):
            raise _bad("node_id", "string is not UTF-8-encodable (lone surrogate)")
        return body
    if _INT64_DECIMAL.fullmatch(body) is None:
        raise _bad("node_id", f"{body!r} is not a canonical INT64 decimal")
    n = int(body)
    if not INT64_MIN <= n <= INT64_MAX:
        raise _bad("node_id", f"integer {n} lies outside INT64")
    return n


def semantic_key(node_type: str, tagged_id: str) -> tuple:
    return node_ref_key(NodeRef(node_type, parse_id(tagged_id)))


@dataclass(frozen=True)
class TypedNode:
    node_type: str
    node_id: str


@dataclass(frozen=True)
class TypedEdge:
    source: TypedNode
    relation: str
    target: TypedNode
    ordinal: str


def node_address(ref: NodeRef) -> TypedNode:
    if not is_identifier(ref.node_type):
        raise _bad("node_type", 'must be a Core identifier (non-empty, no whitespace, none of : | " \\)')
    return TypedNode(ref.node_type, tag_id(ref.node_id))


def edge_address(e: EdgeAddress, *, directed: bool, multigraph: bool) -> TypedEdge:
    if not is_identifier(e.relation):
        raise _bad("relation", 'must be a Core identifier (non-empty, no whitespace, none of : | " \\)')
    if not (is_str(e.ordinal) and _ORDINAL.fullmatch(e.ordinal)):
        raise _bad("ordinal", "canonical decimal string 0|[1-9][0-9]*")
    if not multigraph and e.ordinal != "0":
        raise _bad("ordinal", 'a simple graph carries ordinal "0"')
    src, tgt = node_address(e.source), node_address(e.target)
    if not directed and canonical_endpoints(e.source, e.target) != (e.source, e.target):
        raise _bad("source_id", "endpoints are not in canonical semantic order for an undirected graph")
    return TypedEdge(src, e.relation, tgt, e.ordinal)


def edge_semantic_key(e: TypedEdge) -> tuple:
    """Edge order (26 §1.3): source, relation bytes, target, ordinal bytes ("10" sorts before "2")."""
    return (semantic_key(e.source.node_type, e.source.node_id), e.relation.encode("utf-8"),
            semantic_key(e.target.node_type, e.target.node_id), e.ordinal.encode("ascii"))


class TwinGuard:
    """ID-TWIN-INVARIANT (26 §1.4, inherited from IGDM/1 D1): within one node_type, i:<d> and s:<d> never both occur."""

    def __init__(self) -> None:
        self._ints: dict[tuple[str, str], str] = {}
        self._strs: dict[tuple[str, str], str] = {}

    def see(self, ref: NodeRef, field: str) -> None:
        if is_int(ref.node_id):
            k = (ref.node_type, str(ref.node_id))
            if k in self._strs:
                raise IGDCError("TWIN_IDS", field, f"INT64 id {ref.node_id} is a twin of the STRING id at {self._strs[k]}", "C2")
            self._ints.setdefault(k, field)
        else:
            k = (ref.node_type, ref.node_id)
            if k in self._ints:
                raise IGDCError("TWIN_IDS", field, f"STRING id {ref.node_id!r} is a twin of the INT64 id at {self._ints[k]}", "C2")
            self._strs.setdefault(k, field)

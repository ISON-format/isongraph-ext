"""Policy wire format and Q0 rules (21 §1, §4.1). Canonical by construction; digest = sha256(file bytes)."""

from __future__ import annotations

from typing import Any

from ison_parser import Block, Document, dumps_canonical, loads

from ..igpv.records import INT64_MAX, INT64_MIN, NodeRef, is_identifier, is_int, is_str
from ..igx.digest import sha256_hex
from . import records as R
from .errors import IGPError
from .records import Limits, Policy

TABLES = ("anchors", "mandatory", "node_types", "relations")
_ADDR_FIELDS = ("node_id", "node_type")
_FIELDS = {"anchors": _ADDR_FIELDS, "mandatory": _ADDR_FIELDS, "node_types": ("node_type",), "relations": ("relation",)}


def _err(field: str, detail: str) -> IGPError:
    return IGPError("POLICY_MALFORMED", field, detail, "Q0")


def _limit(name: str, detail: str) -> IGPError:
    return IGPError("PROJECTION_LIMIT_EXCEEDED", name, detail, "Q0")


def _need(cond: bool, field: str, detail: str) -> None:
    if not cond:
        raise _err(field, detail)


def _utf8_ok(s: str) -> bool:
    try:
        s.encode("utf-8")
        return True
    except UnicodeEncodeError:
        return False


def _check_ref(ref: Any, table: str) -> None:
    _need(isinstance(ref, NodeRef), f"table.{table}", "NodeRef required")
    where = f"table.{table}.{ref.node_type}:{ref.node_id}"
    _need(is_str(ref.node_type) and _utf8_ok(ref.node_type), f"{where}.node_type", "string is not UTF-8-encodable (lone surrogate)")
    _need(is_identifier(ref.node_type), f"{where}.node_type", 'Core identifier (non-empty, no whitespace, none of : | " \\)')
    if is_int(ref.node_id):
        _need(INT64_MIN <= ref.node_id <= INT64_MAX, f"{where}.node_id", "integer id must lie within INT64")
    else:
        _need(is_str(ref.node_id) and _utf8_ok(ref.node_id), f"{where}.node_id", "id must be an INT64 integer or a UTF-8 string")


def check(p: Policy, limits: Limits = R.DEFAULT_LIMITS) -> None:
    _need(p.direction in R.DIRECTIONS, "meta.igp.direction", f"not one of {R.DIRECTIONS}")
    _need(is_int(p.depth) and 0 <= p.depth <= min(R.DEPTH_MAX, limits.max_depth), "meta.igp.depth", f"INT64 in [0, {min(R.DEPTH_MAX, limits.max_depth)}]")
    _need(p.max_nodes is None or (is_int(p.max_nodes) and 1 <= p.max_nodes <= INT64_MAX), "meta.igp.max_nodes", "null or INT64 >= 1")
    _need(p.max_edges is None or (is_int(p.max_edges) and 0 <= p.max_edges <= INT64_MAX), "meta.igp.max_edges", "null or INT64 >= 0")
    _need(len(p.anchors) >= 1, "table.anchors", "at least one anchor required")
    for table, rows in (("anchors", p.anchors), ("mandatory", p.mandatory), ("node_types", p.node_types), ("relations", p.relations)):
        if len(rows) > limits.max_rows_per_table:
            raise _limit("max_rows_per_table", f"table.{table} has {len(rows)} rows > {limits.max_rows_per_table}")
    for table, rows in (("anchors", p.anchors), ("mandatory", p.mandatory)):
        seen: set = set()
        for ref in rows:
            _check_ref(ref, table)
            k = (ref.node_type, is_int(ref.node_id), ref.node_id)
            _need(k not in seen, f"table.{table}.{ref.node_type}:{ref.node_id}.node_id", "duplicate address")
            seen.add(k)
    ints, strs = {}, {}                      # ID-TWIN-INVARIANT across anchors and mandatory together (18 §1.2)
    for ref in p.anchors + p.mandatory:
        if is_int(ref.node_id):
            _need((ref.node_type, str(ref.node_id)) not in strs, f"table.anchors.{ref.node_type}:{ref.node_id}.node_id",
                  "INT64 id is a twin of a STRING id in the policy (ID-TWIN-INVARIANT)")
            ints[(ref.node_type, str(ref.node_id))] = True
        else:
            _need((ref.node_type, ref.node_id) not in ints, f"table.anchors.{ref.node_type}:{ref.node_id}.node_id",
                  "STRING id is a twin of an INT64 id in the policy (ID-TWIN-INVARIANT)")
            strs[(ref.node_type, ref.node_id)] = True
    for table, col, rows in (("node_types", "node_type", p.node_types), ("relations", "relation", p.relations)):
        seen2: set = set()
        for v in rows:
            _need(is_str(v) and _utf8_ok(v), f"table.{table}.{v}.{col}", "string is not UTF-8-encodable (lone surrogate)")
            _need(is_identifier(v), f"table.{table}.{v}.{col}", "Core identifier")
            _need(v not in seen2, f"table.{table}.{v}.{col}", "duplicate entry")
            seen2.add(v)


def to_document(p: Policy) -> Document:
    def addr(table, rows):
        return Block("table", table, list(_ADDR_FIELDS), [{"node_type": r.node_type, "node_id": r.node_id} for r in rows])
    meta = {"policy_spec": R.IGP_SPEC, "direction": p.direction, "depth": p.depth, "max_nodes": p.max_nodes, "max_edges": p.max_edges}
    return Document(blocks=[
        Block("meta", "igp", list(R.META_FIELDS), [meta]),
        addr("anchors", p.anchors), addr("mandatory", p.mandatory),
        Block("table", "node_types", ["node_type"], [{"node_type": v} for v in p.node_types]),
        Block("table", "relations", ["relation"], [{"relation": v} for v in p.relations]),
    ])


def to_ison(p: Policy, limits: Limits = R.DEFAULT_LIMITS) -> str:
    """Canonical text. Field rules, row budgets and the canonical byte budget (max_policy_bytes) apply to in-memory policies too."""
    check(p, limits)
    text = dumps_canonical(to_document(p))
    size = len(text.encode("utf-8"))
    if size > limits.max_policy_bytes:
        raise _limit("max_policy_bytes", f"canonical policy is {size} bytes > {limits.max_policy_bytes}")
    return text


def digest(p: Policy) -> str:
    return sha256_hex(to_ison(p))


def from_ison(text: str | bytes, *, limits: Limits = R.DEFAULT_LIMITS) -> Policy:
    if isinstance(text, bytes):
        data = text
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise _err("document", f"not UTF-8: {e}") from None
    else:
        try:
            data = text.encode("utf-8")
        except UnicodeEncodeError as e:
            raise _err("document", f"text is not UTF-8-encodable: {e}") from None
    if len(data) > limits.max_policy_bytes:
        raise _limit("max_policy_bytes", f"{len(data)} > {limits.max_policy_bytes}")
    if "\r" in text:
        raise _err("canonical_form", "CR bytes present; the canonical writer emits LF only")
    try:
        doc = loads(text)
    except Exception as e:
        raise _err("document", f"not ISON: {e}") from None
    required = {("meta", "igp")} | {("table", t) for t in TABLES}
    blocks: dict[tuple[str, str], Block] = {}
    for b in doc.blocks:
        key = (b.kind, b.name)
        _need(key in required, f"{b.kind}.{b.name}", "unexpected block")
        _need(key not in blocks, f"{b.kind}.{b.name}", "duplicate block")
        blocks[key] = b
    for key in sorted(required - set(blocks)):
        raise _err(f"{key[0]}.{key[1]}", "missing block")
    meta_b = blocks[("meta", "igp")]
    _need(set(meta_b.fields) == set(R.META_FIELDS) and len(meta_b.rows) == 1, "meta.igp", f"exactly one row with fields {sorted(R.META_FIELDS)}")
    meta = meta_b.rows[0]
    if meta["policy_spec"] != R.IGP_SPEC:
        raise IGPError("POLICY_VERSION_UNSUPPORTED", "meta.igp.policy_spec", f"must be {R.IGP_SPEC}", "Q0")
    rows: dict[str, list[dict]] = {}
    for t in TABLES:
        b = blocks[("table", t)]
        _need(set(b.fields) == set(_FIELDS[t]), f"table.{t}", f"fields {sorted(b.fields)} != {sorted(_FIELDS[t])}")
        if len(b.rows) > limits.max_rows_per_table:
            raise _limit("max_rows_per_table", f"table.{t} has {len(b.rows)} rows > {limits.max_rows_per_table}")
        rows[t] = b.rows
    p = Policy(
        anchors=tuple(NodeRef(r["node_type"], r["node_id"]) for r in rows["anchors"]),
        mandatory=tuple(NodeRef(r["node_type"], r["node_id"]) for r in rows["mandatory"]),
        node_types=tuple(r["node_type"] for r in rows["node_types"]), relations=tuple(r["relation"] for r in rows["relations"]),
        direction=meta["direction"], depth=meta["depth"], max_nodes=meta["max_nodes"], max_edges=meta["max_edges"])
    if to_ison(p, limits) != text:          # to_ison() runs check() first
        raise _err("canonical_form", "policy bytes are not the canonical writer's output for this document")
    return p

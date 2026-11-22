# isongraph-ext/src/isongraph_ext/igdc/hints.py
"""IGDC/1 hint document: model, canonical wire (26 §2) and consumer checks C0-C3 (26 §4).

Reading goes through `strict_ison.read_canonical` (budget, canonical form, exact blocks, unique columns, no summary or typed
columns, scalar cells). Field vocabularies are IGDM/1's own: `_vocab`, `_common_hints`, `_untok` and `check_references` are
imported from `igdm.payload` and reused, never copied, so the two contracts cannot drift. Nothing in igdm is modified.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from ison_parser import Block, Document, dumps_canonical

from ..igdm import records as R
from ..igdm.errors import IGDMError
from ..igdm.payload import DatamaticsPayload, _common_hints, _is_hex64, _is_key, _untok, _vocab, check_references
from ..igpv.records import EdgeAddress, NodeRef
from ..igx.digest import sha256_hex
from ..strict_ison import BlockShape, StrictError, read_canonical
from .address import TwinGuard, edge_address, node_address, parse_id
from .errors import IGDCError

X_SPLIT = {"nodes": ("role", "ring", "a11y_role", "shape_role"), "edges": ("role", "pattern_role"), "groups": ("role",), "layout": ("family",)}


def _expand(cols: tuple[str, ...], xs: tuple[str, ...]) -> tuple[str, ...]:
    """Insert `<c>_x` right after each x-capable column `c` (26 §2.2)."""
    return tuple(y for c in cols for y in ((c, c + "_x") if c in xs else (c,)))


META_COLUMNS = ("consumption_spec", "address_scheme", "igdm_payload_sha256", "target_artifact_sha256", "target_directed", "target_multigraph",
                "target_serialization_profile")
LAYOUT_COLUMNS = _expand(R.LAYOUT_FIELDS, X_SPLIT["layout"])
NODE_COLUMNS = ("node_type", "node_id") + _expand(R.NODE_HINTS, X_SPLIT["nodes"])
EDGE_COLUMNS = ("source_type", "source_id", "relation", "target_type", "target_id", "ordinal") + _expand(R.EDGE_HINTS, X_SPLIT["edges"])
GROUP_COLUMNS = ("group_id", "intent") + _expand(R.GROUP_FIELDS[2:], X_SPLIT["groups"])
MEMBER_COLUMNS = R.MEMBER_FIELDS

SHAPES = (BlockShape("meta", "igdc", META_COLUMNS, True), BlockShape("meta", "layout", LAYOUT_COLUMNS, True),
          BlockShape("table", "nodes", NODE_COLUMNS), BlockShape("table", "edges", EDGE_COLUMNS),
          BlockShape("table", "groups", GROUP_COLUMNS), BlockShape("table", "members", MEMBER_COLUMNS))


def _c1(field: str, detail: str) -> IGDCError:
    return IGDCError("MALFORMED_CONSUMPTION", field, detail, "C1")


def _from_strict(e: StrictError) -> IGDCError:
    step = "C0" if e.stage == "bytes" else "C1"
    if e.kind == "limit":
        return IGDCError("DATAMATICS_LIMIT_EXCEEDED", "max_payload_bytes" if e.field == "size" else e.field, e.detail, step)
    return IGDCError("MALFORMED_CONSUMPTION", e.field, e.detail, step)


def _need(cond: bool, field: str, detail: str) -> None:
    if not cond:
        raise _c1(field, detail)


def _merged(row: dict, xcols: tuple[str, ...], where: str) -> dict:
    """Fold each `<c>`/`<c>_x` pair back into one `<c>` for IGDM/1's field rules; refuse every §2.2 violation on the way."""
    out = dict(row)
    for c in xcols:
        v, x = out.pop(c), out.pop(c + "_x")
        _need(v is None or x is None, f"{where}.{c}", f"{c} and {c}_x are both set")
        if x is not None:
            _need(isinstance(x, str) and R.X_TOKEN.fullmatch(x) is not None, f"{where}.{c}_x", "an x- token (x-[a-z0-9-]+)")
            out[c] = x
        else:
            _need(not (isinstance(v, str) and R.X_TOKEN.fullmatch(v)), f"{where}.{c}", f"an x- token belongs in {c}_x, not in the closed column")
            out[c] = v
    return out


def _igdm_rules(where: str, row: dict, cols: tuple[str, ...]) -> None:
    try:
        obj = SimpleNamespace(**{c: (_untok(row[c], f"{where}.{c}") if c in R.BOOL_COLUMNS else row[c]) for c in cols})
        _common_hints(obj, where, cols)
    except IGDMError as e:
        raise _c1(e.field, e.detail) from None


@dataclass(frozen=True)
class HintSet:
    meta: dict
    layout: dict
    nodes: tuple[dict, ...] = ()
    edges: tuple[dict, ...] = ()
    groups: tuple[dict, ...] = ()
    members: tuple[dict, ...] = ()

    def to_document(self) -> Document:
        return Document(blocks=[
            Block("meta", "igdc", list(META_COLUMNS), [dict(self.meta)]), Block("meta", "layout", list(LAYOUT_COLUMNS), [dict(self.layout)]),
            Block("table", "nodes", list(NODE_COLUMNS), [dict(r) for r in self.nodes]), Block("table", "edges", list(EDGE_COLUMNS), [dict(r) for r in self.edges]),
            Block("table", "groups", list(GROUP_COLUMNS), [dict(r) for r in self.groups]), Block("table", "members", list(MEMBER_COLUMNS), [dict(r) for r in self.members])])

    def to_ison(self) -> str:
        return dumps_canonical(self.to_document())

    @property
    def digest(self) -> str:
        return sha256_hex(self.to_ison())

    @classmethod
    def from_ison(cls, data: bytes | str, *, limits: R.Limits = R.DEFAULT_LIMITS) -> "HintSet":
        """C0 and C1. The byte budget is `limits.max_payload_bytes`, applied before any parsing (26 §4)."""
        try:
            text, b = read_canonical(data, SHAPES, max_bytes=limits.max_payload_bytes, max_rows=limits.max_rows_per_table)
        except StrictError as e:
            raise _from_strict(e) from None
        h = cls(b[("meta", "igdc")][0], b[("meta", "layout")][0], tuple(b[("table", "nodes")]), tuple(b[("table", "edges")]),
                tuple(b[("table", "groups")]), tuple(b[("table", "members")]))
        h._check_fields()
        if h.to_ison() != text:                                       # the model re-emits what the writer would: a second, independent check
            raise IGDCError("MALFORMED_CONSUMPTION", "canonical_form", "document is not the canonical writer's output for this hint set", "C0")
        return h

    def _check_fields(self) -> None:
        m = self.meta
        _need(m["consumption_spec"] == "IGDC/1", "meta.igdc.consumption_spec", "must be IGDC/1")
        _need(m["address_scheme"] == "igs-addr/1", "meta.igdc.address_scheme", "must be igs-addr/1")
        for col in ("igdm_payload_sha256", "target_artifact_sha256"):
            _need(_is_hex64(m[col]), f"meta.igdc.{col}", "64 lowercase hex")
        _need(m["target_serialization_profile"] in R.PROFILES, "meta.igdc.target_serialization_profile", f"not one of {R.PROFILES}")
        for col in ("target_directed", "target_multigraph"):
            _need(isinstance(m[col], str) and m[col] in ("true", "false"), f"meta.igdc.{col}", 'the string token "true" or "false"')
        lay = _merged(self.layout, X_SPLIT["layout"], "meta.layout")
        try:
            for col in ("family", "direction", "stability"):
                _vocab(lay[col], col, "meta.layout")
        except IGDMError as e:
            raise _c1(e.field, e.detail) from None
        _need(lay["direction"] is None or lay["family"] is not None, "meta.layout.direction", "direction needs a family")
        for r in self.nodes:
            w = f"table.nodes.{r['node_type']}:{r['node_id']}"
            _need(isinstance(r["node_type"], str) and isinstance(r["node_id"], str), w, "node_type and node_id are strings")
            _igdm_rules(w, _merged(r, X_SPLIT["nodes"], w), R.NODE_HINTS)
        for r in self.edges:
            w = f"table.edges.{r['source_type']}:{r['source_id']}/{r['relation']}/{r['target_type']}:{r['target_id']}/{r['ordinal']}"
            for c in ("source_type", "source_id", "relation", "target_type", "target_id", "ordinal"):
                _need(isinstance(r[c], str), f"{w}.{c}", "a string")
            _igdm_rules(w, _merged(r, X_SPLIT["edges"], w), R.EDGE_HINTS)
        for r in self.groups:
            w = f"table.groups.{r['group_id']}"
            g = _merged(r, X_SPLIT["groups"], w)
            _need(_is_key(r["group_id"]), f"{w}.group_id", "key token")
            _need(r["parent_group_id"] is None or _is_key(r["parent_group_id"]), f"{w}.parent_group_id", "null or key token")
            try:
                _vocab(r["intent"], "intent", w)
            except IGDMError as e:
                raise _c1(e.field, e.detail) from None
            _need(r["intent"] is not None, f"{w}.intent", "required")
            _igdm_rules(w, g, ("label", "role", "collapsed", "visibility", "lod_min", "a11y_text"))
        for r in self.members:
            w = f"table.members.{r['group_id']}/{r['node_type']}:{r['node_id']}"
            _need(_is_key(r["group_id"]) and isinstance(r["node_type"], str) and isinstance(r["node_id"], str), w, "group_id key token; node_type and node_id strings")

    def check(self, *, limits: R.Limits = R.DEFAULT_LIMITS) -> None:
        """C2 (addresses) then C3 (references). Needs no target and no Python runtime beyond this package."""
        directed, multigraph = self.meta["target_directed"] == "true", self.meta["target_multigraph"] == "true"
        twins = TwinGuard()

        def parsed(field: str, node_type: str, tagged: str) -> NodeRef:
            try:
                return NodeRef(node_type, parse_id(tagged))
            except IGDCError as e:
                raise IGDCError(e.code, field, e.detail, "C2") from None

        def addressed(w: str, make, *args, **kw):
            """Run a typed-address mapper; a bare column name in its error becomes the row-key path `<w>.<column>` (26 section 4)."""
            try:
                return make(*args, **kw)
            except IGDCError as e:
                raise IGDCError(e.code, f"{w}.{e.field}", e.detail, e.step) from None

        def dup(seen: set, key: Any, field: str, what: str) -> None:
            if key in seen:
                raise IGDCError("INVALID_ADDRESS", field, f"duplicate {what}", "C2")
            seen.add(key)

        seen_n: set = set()
        for r in self.nodes:
            w = f"table.nodes.{r['node_type']}:{r['node_id']}"
            ref = parsed(f"{w}.node_id", r["node_type"], r["node_id"])
            addressed(w, node_address, ref)
            dup(seen_n, ref, f"{w}.node_id", "node row")
            twins.see(ref, f"{w}.node_id")
        seen_e: set = set()
        for r in self.edges:
            w = f"table.edges.{r['source_type']}:{r['source_id']}/{r['relation']}/{r['target_type']}:{r['target_id']}/{r['ordinal']}"
            e = EdgeAddress(parsed(f"{w}.source_id", r["source_type"], r["source_id"]), r["relation"],
                            parsed(f"{w}.target_id", r["target_type"], r["target_id"]), r["ordinal"])
            addressed(w, edge_address, e, directed=directed, multigraph=multigraph)
            dup(seen_e, e, f"{w}.relation", "edge row")
            twins.see(e.source, f"{w}.source_id")
            twins.see(e.target, f"{w}.target_id")
        seen_g: set = set()
        for r in self.groups:
            dup(seen_g, r["group_id"], f"table.groups.{r['group_id']}.group_id", "group id")
        seen_m: set = set()
        members: list[tuple[str, NodeRef]] = []
        for r in self.members:
            w = f"table.members.{r['group_id']}/{r['node_type']}:{r['node_id']}"
            ref = parsed(f"{w}.node_id", r["node_type"], r["node_id"])
            addressed(w, node_address, ref)
            dup(seen_m, (r["group_id"], ref), f"{w}.node_id", "membership")
            twins.see(ref, f"{w}.node_id")
            members.append((r["group_id"], ref))
        # C3: IGDM/1's own D3 over exactly the groups and members this document carries (unknown parent / member group, cycle, depth)
        p = DatamaticsPayload(self.meta["target_artifact_sha256"], self.meta["target_serialization_profile"],
                              groups=tuple(R.Group(g["group_id"], g["intent"], parent_group_id=g["parent_group_id"]) for g in self.groups),
                              members=tuple(R.Member(gid, ref) for gid, ref in members))
        try:
            check_references(p, limits)
        except IGDMError as e:
            raise IGDCError(e.code, e.field, e.detail, "C3") from None

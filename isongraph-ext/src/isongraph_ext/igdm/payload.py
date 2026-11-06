"""IGDM/1 payload: wire model (19 §1), D1 field rules (check). Task 4 adds relation rules, check_references, unrecognized_roles.

Canonical bytes are exactly ison-py's dumps_canonical (blocks by kind.name, fields by name, rows by every column, nulls last).
Booleans are "true"/"false" STRING tokens on the wire and bool | None in records.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from ison_parser import Block, Document, dumps_canonical, loads

from ..igpv import records as PR
from ..igpv.payload import _check_node_ref, _collect_blocks_for, _is_hex64, _is_key, _key_bytes, _one_row, _utf8_ok
from ..igx.digest import sha256_hex
from . import records as R
from .errors import IGDMError

TABLES = (("nodes", R.NODE_FIELDS), ("edges", R.EDGE_FIELDS), ("groups", R.GROUP_FIELDS), ("members", R.MEMBER_FIELDS))
REQUIRED_BLOCKS = {("meta", "igdm"), ("meta", "layout")} | {("table", n) for n, _f in TABLES}
_X_COLUMNS = {"role", "ring", "a11y_role", "shape_role", "pattern_role", "family"}   # the only columns where x- is legal
_VOCAB = {"role": R.ROLES, "ring": R.ROLES, "a11y_role": R.ROLES, "shape_role": R.SHAPE_ROLES, "pattern_role": R.PATTERN_ROLES,
          "emphasis": R.EMPHASIS, "visibility": R.VISIBILITY, "direction_display": R.DIRECTION_DISPLAY,
          "temporal_state": R.TEMPORAL_STATES, "intent": R.INTENTS, "family": R.FAMILIES, "direction": R.DIRECTIONS,
          "stability": R.STABILITY}


def _err(field: str, detail: str) -> IGDMError:
    return IGDMError("MALFORMED_DATAMATICS", field, detail, "D1")


def _limit(name: str, detail: str) -> IGDMError:
    return IGDMError("DATAMATICS_LIMIT_EXCEEDED", name, detail, "D1")


def node_key(ref: PR.NodeRef) -> str:
    return f"{ref.node_type}:{ref.node_id}"


def edge_key(e: PR.EdgeAddress) -> str:
    return f"{node_key(e.source)}-{e.relation}-{node_key(e.target)}#{e.ordinal}"


def _tok(v: bool | None) -> str | None:
    return None if v is None else ("true" if v else "false")


def _node_row(n: R.NodeHints) -> dict:
    row = {"node_type": n.node.node_type, "node_id": n.node.node_id}
    for col in R.NODE_HINTS:
        v = getattr(n, col)
        row[col] = _tok(v) if col in R.BOOL_COLUMNS else v
    return row


def _edge_row(e: R.EdgeHints) -> dict:
    a = e.edge
    row = {"source_type": a.source.node_type, "source_id": a.source.node_id, "relation": a.relation,
           "target_type": a.target.node_type, "target_id": a.target.node_id, "ordinal": a.ordinal}
    for col in R.EDGE_HINTS:
        v = getattr(e, col)
        row[col] = _tok(v) if col in R.BOOL_COLUMNS else v
    return row


def _group_row(g: R.Group) -> dict:
    return {col: (_tok(getattr(g, col)) if col in R.BOOL_COLUMNS else getattr(g, col)) for col in R.GROUP_FIELDS}


def _member_row(m: R.Member) -> dict:
    return {"group_id": m.group_id, "node_type": m.node.node_type, "node_id": m.node.node_id}


def _untok(v: Any, where: str) -> bool | None:
    if v is None:
        return None
    if isinstance(v, str) and v == "true":
        return True
    if isinstance(v, str) and v == "false":
        return False
    raise _err(where, 'boolean columns carry the string tokens "true" / "false"')


def _node_from_row(r: dict) -> R.NodeHints:
    ref = PR.NodeRef(r["node_type"], r["node_id"])
    kw = {col: (_untok(r[col], f"table.nodes.{node_key(ref)}.{col}") if col in R.BOOL_COLUMNS else r[col]) for col in R.NODE_HINTS}
    return R.NodeHints(ref, **kw)


def _edge_from_row(r: dict) -> R.EdgeHints:
    addr = PR.EdgeAddress(PR.NodeRef(r["source_type"], r["source_id"]), r["relation"], PR.NodeRef(r["target_type"], r["target_id"]), r["ordinal"])
    kw = {col: (_untok(r[col], f"table.edges.{edge_key(addr)}.{col}") if col in R.BOOL_COLUMNS else r[col]) for col in R.EDGE_HINTS}
    return R.EdgeHints(addr, **kw)


def _group_from_row(r: dict) -> R.Group:
    kw = {col: (_untok(r[col], f"table.groups.{r['group_id']}.{col}") if col in R.BOOL_COLUMNS else r[col]) for col in R.GROUP_FIELDS}
    return R.Group(**kw)


@dataclass(frozen=True)
class DatamaticsPayload:
    target_artifact_sha256: str
    target_serialization_profile: str
    layout: R.LayoutHints = R.LayoutHints()
    nodes: tuple[R.NodeHints, ...] = ()
    edges: tuple[R.EdgeHints, ...] = ()
    groups: tuple[R.Group, ...] = ()
    members: tuple[R.Member, ...] = ()

    def __post_init__(self) -> None:
        # Records are held in a stable key order so value equality is independent of construction/wire order (as 18).
        def norm(rows, key):
            try:
                return tuple(sorted(rows, key=lambda r: _key_bytes(key(r))))
            except Exception:
                return tuple(rows)
        object.__setattr__(self, "nodes", norm(self.nodes, lambda n: node_key(n.node)))
        object.__setattr__(self, "edges", norm(self.edges, lambda e: edge_key(e.edge)))
        object.__setattr__(self, "groups", norm(self.groups, lambda g: g.group_id))
        object.__setattr__(self, "members", norm(self.members, lambda m: f"{m.group_id}/{node_key(m.node)}"))

    def to_document(self) -> Document:
        return Document(blocks=[
            Block("meta", "igdm", list(R.META_FIELDS), [{"datamatics_spec": R.DATAMATICS_SPEC, "target_artifact_sha256": self.target_artifact_sha256,
                                                          "target_serialization_profile": self.target_serialization_profile}]),
            Block("meta", "layout", list(R.LAYOUT_FIELDS), [{"family": self.layout.family, "direction": self.layout.direction, "stability": self.layout.stability}]),
            Block("table", "nodes", list(R.NODE_FIELDS), [_node_row(n) for n in self.nodes]),
            Block("table", "edges", list(R.EDGE_FIELDS), [_edge_row(e) for e in self.edges]),
            Block("table", "groups", list(R.GROUP_FIELDS), [_group_row(g) for g in self.groups]),
            Block("table", "members", list(R.MEMBER_FIELDS), [_member_row(m) for m in self.members]),
        ])

    def to_ison(self) -> str:
        self.check()
        return dumps_canonical(self.to_document())

    @property
    def digest(self) -> str:
        return sha256_hex(self.to_ison())

    @classmethod
    def from_ison(cls, text: str | bytes, *, limits: R.Limits = R.DEFAULT_LIMITS) -> "DatamaticsPayload":
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
        if len(data) > limits.max_payload_bytes:
            raise _limit("max_payload_bytes", f"{len(data)} > {limits.max_payload_bytes}")
        if "\r" in text:
            raise _err("canonical_form", "CR bytes present; the canonical writer emits LF only")
        try:
            doc = loads(text)
        except Exception as e:
            raise _err("document", f"not ISON: {e}") from None
        blocks = _collect_blocks_for(doc, REQUIRED_BLOCKS, _err)
        meta = _one_row(blocks[("meta", "igdm")], "meta.igdm", R.META_FIELDS, _err)
        if meta["datamatics_spec"] != R.DATAMATICS_SPEC:
            raise _err("meta.igdm.datamatics_spec", f"must be {R.DATAMATICS_SPEC}")
        lay = _one_row(blocks[("meta", "layout")], "meta.layout", R.LAYOUT_FIELDS, _err)
        rows: dict[str, list[dict]] = {}
        for name, fields in TABLES:
            b = blocks[("table", name)]
            if set(b.fields) != set(fields):
                raise _err(f"table.{name}", f"fields {sorted(b.fields)} != {sorted(fields)}")
            if len(b.rows) > limits.max_rows_per_table:
                raise _limit("max_rows_per_table", f"table.{name} has {len(b.rows)} rows > {limits.max_rows_per_table}")
            rows[name] = b.rows
        p = cls(target_artifact_sha256=meta["target_artifact_sha256"], target_serialization_profile=meta["target_serialization_profile"],
                layout=R.LayoutHints(lay["family"], lay["direction"], lay["stability"]),
                nodes=tuple(_node_from_row(r) for r in rows["nodes"]), edges=tuple(_edge_from_row(r) for r in rows["edges"]),
                groups=tuple(_group_from_row(r) for r in rows["groups"]),
                members=tuple(R.Member(r["group_id"], PR.NodeRef(r["node_type"], r["node_id"])) for r in rows["members"]))
        if p.to_ison() != text:
            raise _err("canonical_form", "payload bytes are not the canonical writer's output for this document (row order included)")
        return p

    def check(self) -> None:
        """D1 rules that need no bytes (19 §3.1): field rules, then relation rules."""
        _check_fields(self)
        _check_relations(self)


def _need(cond: bool, field: str, detail: str) -> None:
    if not cond:
        raise _err(field, detail)


def _vocab(v: Any, col: str, where: str) -> None:
    if v is None:
        return
    _need(PR.is_str(v) and _utf8_ok(v), f"{where}.{col}", "string or null")
    if v in _VOCAB[col]:
        return
    if col in _X_COLUMNS and R.X_TOKEN.fullmatch(v):
        return
    _need(False, f"{where}.{col}", f"not one of {_VOCAB[col]}" + (" or an x- token" if col in _X_COLUMNS else ""))


def _opt_text(v: Any, col: str, where: str) -> None:
    _need(v is None or (PR.is_str(v) and v != "" and _utf8_ok(v)), f"{where}.{col}", "null or non-empty string")


def _opt_bool(v: Any, col: str, where: str) -> None:
    _need(v is None or isinstance(v, bool), f"{where}.{col}", 'bool or null in records; "true"/"false" tokens on the wire')


def _opt_int(v: Any, col: str, where: str, lo: int, hi: int) -> None:
    _need(v is None or (PR.is_int(v) and lo <= v <= hi), f"{where}.{col}", f"INT64 in [{lo}, {hi}] or null")


def _common_hints(obj: Any, where: str, cols: tuple[str, ...]) -> None:
    for col in cols:
        v = getattr(obj, col)
        if col in _VOCAB:
            _vocab(v, col, where)
        elif col in ("label", "a11y_text"):
            _opt_text(v, col, where)
        elif col in R.BOOL_COLUMNS:
            _opt_bool(v, col, where)
        elif col == "lod_min":
            _opt_int(v, col, where, 0, R.LOD_MAX)
        elif col in ("temporal_order", "layout_rank"):
            _opt_int(v, col, where, 0, PR.INT64_MAX)
        elif col == "badge":
            _need(v is None or (PR.is_str(v) and _utf8_ok(v) and 1 <= len(v) <= R.BADGE_MAX
                                and not any(unicodedata.category(c) == "Cc" for c in v)),
                  f"{where}.{col}", f"null or 1..{R.BADGE_MAX} Unicode scalar values, none in category Cc (control)")
        elif col == "magnitude":
            _need(v is None or ((PR.is_int(v) or isinstance(v, float)) and 0 <= v <= 1), f"{where}.{col}", "numeric literal in [0, 1] or null")


def _check_fields(p: DatamaticsPayload) -> None:
    _need(_is_hex64(p.target_artifact_sha256), "meta.igdm.target_artifact_sha256", "64 lowercase hex")
    _need(p.target_serialization_profile in R.PROFILES, "meta.igdm.target_serialization_profile", f"not one of {R.PROFILES}")
    _vocab(p.layout.family, "family", "meta.layout")
    _vocab(p.layout.direction, "direction", "meta.layout")
    _vocab(p.layout.stability, "stability", "meta.layout")
    _need(p.layout.direction is None or p.layout.family is not None, "meta.layout.direction", "direction needs a family")
    for n in p.nodes:
        w = f"table.nodes.{node_key(n.node)}"
        _check_node_ref(n.node, w, "node_type", "node_id", _err)
        _common_hints(n, w, R.NODE_HINTS)
    for e in p.edges:
        w = f"table.edges.{edge_key(e.edge)}"
        _check_node_ref(e.edge.source, w, "source_type", "source_id", _err)
        _need(PR.is_identifier(e.edge.relation), f"{w}.relation", "Core identifier")
        _check_node_ref(e.edge.target, w, "target_type", "target_id", _err)
        _need(PR.is_str(e.edge.ordinal) and PR.ORDINAL.fullmatch(e.edge.ordinal) is not None, f"{w}.ordinal", 'canonical decimal string ("0", "1", "10")')
        _common_hints(e, w, R.EDGE_HINTS)
    for g in p.groups:
        w = f"table.groups.{g.group_id}"
        _need(_is_key(g.group_id), f"{w}.group_id", "key token")
        _vocab(g.intent, "intent", w)
        _need(g.intent is not None, f"{w}.intent", "required")
        _need(g.parent_group_id is None or _is_key(g.parent_group_id), f"{w}.parent_group_id", "null or key token")
        _need(g.parent_group_id != g.group_id, f"{w}.parent_group_id", "a group is never its own parent")
        _common_hints(g, w, ("label", "role", "collapsed", "visibility", "lod_min", "a11y_text"))
    for m in p.members:
        w = f"table.members.{m.group_id}/{node_key(m.node)}"
        _need(_is_key(m.group_id), f"{w}.group_id", "key token")
        _check_node_ref(m.node, w, "node_type", "node_id", _err)


def _twin_and_unique(p: DatamaticsPayload) -> None:
    ints: dict[tuple, str] = {}
    strs: dict[tuple, str] = {}

    def see(ref: PR.NodeRef, field: str) -> None:
        if PR.is_int(ref.node_id):
            k = (ref.node_type, str(ref.node_id))
            _need(k not in strs, field, f"INT64 id {ref.node_id} is a twin of a STRING id at {strs.get(k)} (ID-TWIN-INVARIANT)")
            ints.setdefault(k, field)
        else:
            k = (ref.node_type, ref.node_id)
            _need(k not in ints, field, f"STRING id {ref.node_id!r} is a twin of an INT64 id at {ints.get(k)} (ID-TWIN-INVARIANT)")
            strs.setdefault(k, field)

    seen_n: set = set()
    for n in p.nodes:
        w = f"table.nodes.{node_key(n.node)}"
        _need(n.node not in seen_n, f"{w}.node_id", "duplicate node row")
        seen_n.add(n.node)
        see(n.node, f"{w}.node_id")
        _need(any(getattr(n, c) is not None for c in R.NODE_HINTS), f"{w}.node_id", "a row with no hint is noise, not intent")
    seen_e: set = set()
    for e in p.edges:
        w = f"table.edges.{edge_key(e.edge)}"
        _need(e.edge not in seen_e, f"{w}.relation", "duplicate edge row")
        seen_e.add(e.edge)
        see(e.edge.source, f"{w}.source_id")
        see(e.edge.target, f"{w}.target_id")
        _need(any(getattr(e, c) is not None for c in R.EDGE_HINTS), f"{w}.relation", "a row with no hint is noise, not intent")
    seen_g: set = set()
    for g in p.groups:
        _need(g.group_id not in seen_g, f"table.groups.{g.group_id}.group_id", "duplicate group id")
        seen_g.add(g.group_id)
    seen_m: set = set()
    for m in p.members:
        w = f"table.members.{m.group_id}/{node_key(m.node)}"
        _need((m.group_id, m.node) not in seen_m, f"{w}.node_id", "duplicate membership")
        seen_m.add((m.group_id, m.node))
        see(m.node, f"{w}.node_id")


def _ancestry(groups: dict[str, R.Group]) -> tuple[dict[str, frozenset[str]], dict[str, int]]:
    """Ancestor set and depth of every group, computed ONCE with memoised iterative walks: O(G * h) total, never per pair.
    Unknown parents and cycles end a walk (D3 reports them); D1 only needs 'who is above whom'."""
    anc: dict[str, frozenset[str]] = {}
    depth: dict[str, int] = {}
    for start in groups:
        if start in anc:
            continue
        path: list[str] = []
        cur: str | None = start
        seen: set[str] = set()
        while cur is not None and cur in groups and cur not in anc and cur not in seen:
            path.append(cur)
            seen.add(cur)
            cur = groups[cur].parent_group_id
        known = cur is not None and cur in anc
        base: frozenset[str] = (anc[cur] | {cur}) if known else frozenset()
        base_depth = depth[cur] if known else 0
        for gid in reversed(path):                       # from the top of the walk down: ancestors of gid are everything above it
            anc[gid] = base
            depth[gid] = base_depth + 1
            base = base | {gid}
            base_depth += 1
    return anc, depth


def _check_relations(p: DatamaticsPayload) -> None:
    _twin_and_unique(p)
    groups = {g.group_id: g for g in p.groups}
    anc, depth = _ancestry(groups)
    by_node: dict[PR.NodeRef, list[str]] = {}
    for m in p.members:                                  # members are in key order (group_id first), so conflicts report the later one
        by_node.setdefault(m.node, []).append(m.group_id)
    for node, gids in by_node.items():
        excl = [g for g in gids if g in groups and groups[g].intent in ("collapse", "aggregate")]
        if len(excl) > 1:
            _need(False, f"table.members.{excl[1]}/{node_key(node)}.group_id", f"node already belongs to collapse/aggregate group {excl[0]!r}")
        hier = sorted((g for g in gids if g in groups and groups[g].intent == "hierarchy"), key=lambda g: depth[g])
        for shallow, deep in zip(hier, hier[1:]):       # a chain iff each next-deeper group has the previous one as an ancestor
            _need(shallow in anc[deep], f"table.members.{deep}/{node_key(node)}.group_id", f"hierarchy groups {shallow!r} and {deep!r} are not nested")
    with_members = {gid for gids in by_node.values() for gid in gids if gid in groups}
    reachable: set[str] = set(with_members)
    for gid in with_members:
        reachable.update(anc[gid])
    for g in p.groups:
        _need(g.group_id in reachable, f"table.groups.{g.group_id}.group_id", "unreachable: no members and no descendant with members")


def check_references(p: DatamaticsPayload, limits: R.Limits = R.DEFAULT_LIMITS) -> None:
    """D3 (19 §3.1): parents and member groups exist; the parent relation is acyclic and within max_group_depth."""
    groups = {g.group_id: g for g in p.groups}
    for g in p.groups:
        if g.parent_group_id is not None and g.parent_group_id not in groups:
            raise IGDMError("UNRESOLVED_REFERENCE", f"table.groups.{g.group_id}.parent_group_id", f"unknown group {g.parent_group_id!r}", "D3")
    for m in p.members:
        if m.group_id not in groups:
            raise IGDMError("UNRESOLVED_REFERENCE", f"table.members.{m.group_id}/{node_key(m.node)}.group_id", f"unknown group {m.group_id!r}", "D3")
    for g in p.groups:                      # iterative walk: a 10^4-deep chain must never recurse
        seen = {g.group_id}
        depth = 0
        cur = g.parent_group_id
        while cur is not None:
            if cur in seen:
                raise IGDMError("GROUP_CYCLE", f"table.groups.{g.group_id}.parent_group_id", f"group {cur!r} is its own ancestor", "D3")
            depth += 1
            if depth > limits.max_group_depth:
                raise IGDMError("DATAMATICS_LIMIT_EXCEEDED", "max_group_depth", f"group {g.group_id!r} nests deeper than {limits.max_group_depth}", "D3")
            seen.add(cur)
            cur = groups[cur].parent_group_id


def unrecognized_roles(p: DatamaticsPayload) -> tuple[str, ...]:
    found: set[str] = set()

    def look(table: str, obj: Any, cols) -> None:
        for col in cols:
            v = getattr(obj, col)
            if PR.is_str(v) and col in _X_COLUMNS and R.X_TOKEN.fullmatch(v):
                found.add(f"{table}.{col}:{v}")

    look("layout", p.layout, ("family",))
    for n in p.nodes:
        look("nodes", n, ("role", "ring", "a11y_role", "shape_role"))
    for e in p.edges:
        look("edges", e, ("role", "pattern_role"))
    for g in p.groups:
        look("groups", g, ("role",))
    return tuple(sorted(found))

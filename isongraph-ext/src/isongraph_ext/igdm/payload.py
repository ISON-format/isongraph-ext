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


def _check_address_utf8(ref: PR.NodeRef, where: str, type_col: str, id_col: str) -> None:
    """In-memory addresses may hold lone surrogates that have no UTF-8 bytes (and hence no digest): reject them at D1."""
    _need(_utf8_ok(ref.node_type), f"{where}.{type_col}", "string is not UTF-8-encodable (lone surrogate)")
    _need(_utf8_ok(ref.node_id), f"{where}.{id_col}", "string is not UTF-8-encodable (lone surrogate)")


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
        _check_address_utf8(n.node, w, "node_type", "node_id")
        _common_hints(n, w, R.NODE_HINTS)
    for e in p.edges:
        w = f"table.edges.{edge_key(e.edge)}"
        _check_node_ref(e.edge.source, w, "source_type", "source_id", _err)
        _check_address_utf8(e.edge.source, w, "source_type", "source_id")
        _need(PR.is_identifier(e.edge.relation) and _utf8_ok(e.edge.relation), f"{w}.relation", "Core identifier, UTF-8-encodable")
        _check_node_ref(e.edge.target, w, "target_type", "target_id", _err)
        _check_address_utf8(e.edge.target, w, "target_type", "target_id")
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
        _check_address_utf8(m.node, w, "node_type", "node_id")


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


class _Forest:
    """Group forest for D1: parent links that are unknown or cyclic are cut (D3 reports them), every group then has one root.
    Ancestry is answered by Euler-tour intervals (tin/tout) from one iterative DFS: O(G) memory and time, never per-pair
    walks and never materialised ancestor sets (a 10^5-deep chain stays a few MB)."""

    def __init__(self, groups: dict[str, R.Group]) -> None:
        self.parent: dict[str, str | None] = {}
        for gid, g in groups.items():                   # cut unknown parents
            self.parent[gid] = g.parent_group_id if g.parent_group_id in groups else None
        self.cyclic: set[str] = set()                   # groups on a cycle: exempt from the D1 reachability rule, D3 reports them
        state: dict[str, int] = {}                      # 0 = on the current path, 1 = done
        for start in groups:                            # cut cycles: the first group whose walk returns to the path loses its parent
            if start in state:
                continue
            path: list[str] = []
            cur: str | None = start
            while cur is not None and cur not in state:
                state[cur] = 0
                path.append(cur)
                cur = self.parent[cur]
            if cur is not None and state[cur] == 0:     # cycle: `cur` is on the path
                self.cyclic.update(path[path.index(cur):])
                self.parent[cur] = None
            for gid in path:
                state[gid] = 1
        self.children: dict[str, list[str]] = {gid: [] for gid in groups}
        for gid, par in self.parent.items():
            if par is not None:
                self.children[par].append(gid)
        self.tin: dict[str, int] = {}
        self.tout: dict[str, int] = {}
        clock = 0
        for root in groups:
            if self.parent[root] is not None:
                continue
            stack: list[tuple[str, int]] = [(root, 0)]
            while stack:
                gid, i = stack[-1]
                if i == 0:
                    self.tin[gid] = clock
                    clock += 1
                kids = self.children[gid]
                if i < len(kids):
                    stack[-1] = (gid, i + 1)
                    stack.append((kids[i], 0))
                else:
                    self.tout[gid] = clock
                    stack.pop()

    def is_ancestor_or_self(self, a: str, b: str) -> bool:
        return self.tin[a] <= self.tin[b] < self.tout[a]

    def mark_upward(self, starts) -> set[str]:
        """Every group on the path from each start to its root; stops at already-marked groups: O(G)."""
        marked: set[str] = set()
        for gid in starts:
            cur: str | None = gid
            while cur is not None and cur not in marked:
                marked.add(cur)
                cur = self.parent[cur]
        return marked


def _check_relations(p: DatamaticsPayload) -> None:
    _twin_and_unique(p)
    groups = {g.group_id: g for g in p.groups}
    forest = _Forest(groups)
    by_node: dict[PR.NodeRef, list[str]] = {}
    for m in p.members:                                  # members are in key order (group_id first), so conflicts report the later one
        by_node.setdefault(m.node, []).append(m.group_id)
    for node, gids in by_node.items():
        excl = [g for g in gids if g in groups and groups[g].intent in ("collapse", "aggregate")]
        if len(excl) > 1:
            _need(False, f"table.members.{excl[1]}/{node_key(node)}.group_id", f"node already belongs to collapse/aggregate group {excl[0]!r}")
        deepest: str | None = None                      # 19 §1.1: walk memberships in key order, report the first that breaks the chain
        for g in gids:
            if g not in groups or groups[g].intent != "hierarchy":
                continue
            if deepest is None or forest.is_ancestor_or_self(g, deepest):
                deepest = deepest or g
            elif forest.is_ancestor_or_self(deepest, g):
                deepest = g
            else:
                _need(False, f"table.members.{g}/{node_key(node)}.group_id", f"hierarchy groups {deepest!r} and {g!r} are not nested")
    reachable = forest.mark_upward(gid for gids in by_node.values() for gid in gids if gid in groups)
    for g in p.groups:
        _need(g.group_id in reachable or g.group_id in forest.cyclic, f"table.groups.{g.group_id}.group_id",
              "unreachable: no members and no descendant with members")


def check_references(p: DatamaticsPayload, limits: R.Limits = R.DEFAULT_LIMITS) -> None:
    """D3 (19 §3.1): parents and member groups exist; the parent relation is acyclic and within max_group_depth."""
    groups = {g.group_id: g for g in p.groups}
    for g in p.groups:
        if g.parent_group_id is not None and g.parent_group_id not in groups:
            raise IGDMError("UNRESOLVED_REFERENCE", f"table.groups.{g.group_id}.parent_group_id", f"unknown group {g.parent_group_id!r}", "D3")
    for m in p.members:
        if m.group_id not in groups:
            raise IGDMError("UNRESOLVED_REFERENCE", f"table.members.{m.group_id}/{node_key(m.node)}.group_id", f"unknown group {m.group_id!r}", "D3")
    # acyclicity first (19 §3.1 lists it before the depth budget): one memoised colouring walk over all groups, O(G);
    # a cycle is reported at its smallest-key member (groups are in key order).
    state: dict[str, int] = {}                          # 0 = on the current path, 1 = done
    for g in p.groups:
        if g.group_id in state:
            continue
        path: list[str] = []
        cur: str | None = g.group_id
        while cur is not None and cur not in state:
            state[cur] = 0
            path.append(cur)
            cur = groups[cur].parent_group_id
        if cur is not None and state[cur] == 0:
            members = path[path.index(cur):]
            first = min(members, key=lambda s: s.encode("utf-8"))
            raise IGDMError("GROUP_CYCLE", f"table.groups.{first}.parent_group_id", f"group {first!r} is its own ancestor", "D3")
        for gid in path:
            state[gid] = 1
    depth: dict[str, int] = {}                          # then the depth budget, memoised: O(G)
    for g in p.groups:
        path = []
        cur = g.group_id
        while cur is not None and cur not in depth:
            path.append(cur)
            cur = groups[cur].parent_group_id
        d = depth[cur] if cur is not None else -1
        for gid in reversed(path):
            d += 1
            depth[gid] = d
        if depth[g.group_id] > limits.max_group_depth:
            raise IGDMError("DATAMATICS_LIMIT_EXCEEDED", "max_group_depth", f"group {g.group_id!r} nests deeper than {limits.max_group_depth}", "D3")


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

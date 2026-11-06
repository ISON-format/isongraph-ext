"""IGPV/1 payload: wire model (18 §1), P1 field rules (check). Task 5 adds relation rules and P3 reference rules.

Canonical bytes are exactly ison-py's `dumps_canonical`: it orders blocks by kind.name, fields by name ("id" first), and
rows by every column in that field order (nulls last), so the same record set always yields the same bytes and digest.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields as dc_fields
from typing import Any

from ison_parser import Block, Document, dumps_canonical, loads

from ..igx.digest import sha256_hex
from . import records as R
from .errors import IGPVError
from .locators import check_locator_shape

META_FIELDS = ("provenance_spec", "target_artifact_sha256", "target_semantic_digest", "target_semantic_digest_algorithm",
               "target_serialization_profile")
ARTIFACT_FIELDS = ("artifact_id", "artifact_sha256", "kind", "media_type", "revision", "serialization_profile", "size", "uri")
PRODUCER_FIELDS = ("producer_id", "kind", "implementation", "version", "spec", "policy_sha256")
OBJECT_FIELDS = ("object_id", "graph", "kind", "node_type", "node_id", "source_type", "source_id", "relation", "target_type",
                 "target_id", "ordinal")
ATTRIBUTION_FIELDS = ("attribution_id", "object_id", "artifact_id", "producer_id", "locator_type", "locator_start",
                      "locator_end", "locator_text")
DERIVATION_FIELDS = ("derivation_id", "derived_object_id", "origin_object_id", "producer_id", "kind")
TABLES = (("artifacts", ARTIFACT_FIELDS, "artifact_id"), ("producers", PRODUCER_FIELDS, "producer_id"),
          ("objects", OBJECT_FIELDS, "object_id"), ("attributions", ATTRIBUTION_FIELDS, "attribution_id"),
          ("derivations", DERIVATION_FIELDS, "derivation_id"))
_NODE_COLS = ("node_type", "node_id")
_EDGE_COLS = ("source_type", "source_id", "relation", "target_type", "target_id", "ordinal")


def _err(field: str, detail: str) -> IGPVError:
    return IGPVError("MALFORMED_PROVENANCE", field, detail, "P1")


def _limit(name: str, detail: str) -> IGPVError:
    return IGPVError("PROVENANCE_LIMIT_EXCEEDED", name, detail, "P1")


def _key_bytes(value: Any) -> bytes:
    return str(value).encode("utf-8", "surrogatepass")


# ---- records -> rows ----------------------------------------------------------------------------------------

def _artifact_row(a: R.Artifact) -> dict:
    return {"artifact_id": a.artifact_id, "artifact_sha256": a.artifact_sha256, "kind": a.kind, "media_type": a.media_type,
            "revision": a.revision, "serialization_profile": a.serialization_profile, "size": a.size, "uri": a.uri}


def _producer_row(p: R.Producer) -> dict:
    return {"producer_id": p.producer_id, "kind": p.kind, "implementation": p.implementation, "version": p.version,
            "spec": p.spec, "policy_sha256": p.policy_sha256}


def _object_row(o: R.GraphObject) -> dict:
    row: dict[str, Any] = {k: None for k in OBJECT_FIELDS}
    row.update({"object_id": o.object_id, "graph": o.graph, "kind": o.kind})
    if o.node is not None:
        row.update({"node_type": o.node.node_type, "node_id": o.node.node_id})
    if o.edge is not None:
        e = o.edge
        row.update({"source_type": e.source.node_type, "source_id": e.source.node_id, "relation": e.relation,
                    "target_type": e.target.node_type, "target_id": e.target.node_id, "ordinal": e.ordinal})
    return row


def _attribution_row(a: R.Attribution) -> dict:
    loc = a.locator
    return {"attribution_id": a.attribution_id, "object_id": a.object_id, "artifact_id": a.artifact_id,
            "producer_id": a.producer_id, "locator_type": None if loc is None else loc.type,
            "locator_start": None if loc is None else loc.start, "locator_end": None if loc is None else loc.end,
            "locator_text": None if loc is None else loc.text}


def _derivation_row(d: R.Derivation) -> dict:
    return {"derivation_id": d.derivation_id, "derived_object_id": d.derived_object_id, "origin_object_id": d.origin_object_id,
            "producer_id": d.producer_id, "kind": d.kind}


# ---- rows -> records ----------------------------------------------------------------------------------------

def _object_from_row(r: dict) -> R.GraphObject:
    where = f"table.objects.{r['object_id']}"
    kind = r["kind"]
    want = {"node": set(_NODE_COLS), "edge": set(_EDGE_COLS)}.get(kind, set())
    for col in _NODE_COLS + _EDGE_COLS:
        if col not in want and r[col] is not None:
            raise _err(f"{where}.{col}", f"must be null for kind {kind!r}")
    node = R.NodeRef(r["node_type"], r["node_id"]) if kind == "node" else None
    edge = (R.EdgeAddress(R.NodeRef(r["source_type"], r["source_id"]), r["relation"],
                          R.NodeRef(r["target_type"], r["target_id"]), r["ordinal"]) if kind == "edge" else None)
    return R.GraphObject(r["object_id"], kind, r["graph"], node, edge)


def _attribution_from_row(r: dict) -> R.Attribution:
    if r["locator_type"] is None:
        for col in ("locator_start", "locator_end", "locator_text"):
            if r[col] is not None:
                raise _err(f"table.attributions.{r['attribution_id']}.{col}", "must be null when locator_type is null")
        loc = None
    else:
        loc = R.Locator(r["locator_type"], r["locator_start"], r["locator_end"], r["locator_text"])
    return R.Attribution(r["attribution_id"], r["object_id"], r["artifact_id"], r["producer_id"], loc)


@dataclass(frozen=True)
class ProvenancePayload:
    target_artifact_sha256: str
    target_serialization_profile: str
    artifacts: tuple[R.Artifact, ...] = ()
    producers: tuple[R.Producer, ...] = ()
    objects: tuple[R.GraphObject, ...] = ()
    attributions: tuple[R.Attribution, ...] = ()
    derivations: tuple[R.Derivation, ...] = ()

    def __post_init__(self) -> None:
        # Records are held in key order so that value equality is independent of construction or wire order.
        # Wire row order is NOT this: ison-py's canonical writer sorts rows itself (every column, nulls last).
        for name, _fields, key in TABLES:
            rows = getattr(self, name)
            try:
                normalized = tuple(sorted(rows, key=lambda r: _key_bytes(getattr(r, key))))
            except Exception:
                normalized = tuple(rows)      # unsortable junk: check() reports it, equality is not promised
            object.__setattr__(self, name, normalized)

    def to_document(self) -> Document:
        def table(name: str, fields: tuple[str, ...], key: str, rows: list[dict]) -> Block:
            return Block(kind="table", name=name, fields=list(fields), rows=rows)   # row order is the canonical writer's

        meta = {"provenance_spec": R.PROVENANCE_SPEC, "target_artifact_sha256": self.target_artifact_sha256,
                "target_semantic_digest": None, "target_semantic_digest_algorithm": None,
                "target_serialization_profile": self.target_serialization_profile}
        return Document(blocks=[
            Block(kind="meta", name="igpv", fields=list(META_FIELDS), rows=[meta]),
            table("artifacts", ARTIFACT_FIELDS, "artifact_id", [_artifact_row(a) for a in self.artifacts]),
            table("producers", PRODUCER_FIELDS, "producer_id", [_producer_row(p) for p in self.producers]),
            table("objects", OBJECT_FIELDS, "object_id", [_object_row(o) for o in self.objects]),
            table("attributions", ATTRIBUTION_FIELDS, "attribution_id", [_attribution_row(a) for a in self.attributions]),
            table("derivations", DERIVATION_FIELDS, "derivation_id", [_derivation_row(d) for d in self.derivations]),
        ])

    def to_ison(self) -> str:
        self.check()
        return dumps_canonical(self.to_document())

    @property
    def digest(self) -> str:
        return sha256_hex(self.to_ison())

    @classmethod
    def from_ison(cls, text: str | bytes, *, limits: R.Limits = R.DEFAULT_LIMITS) -> "ProvenancePayload":
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
        blocks = _collect_blocks(doc)
        meta = _one_row(blocks[("meta", "igpv")], "meta.igpv", META_FIELDS)
        if meta["provenance_spec"] != R.PROVENANCE_SPEC:
            raise _err("meta.igpv.provenance_spec", f"must be {R.PROVENANCE_SPEC}")
        if meta["target_semantic_digest"] is not None or meta["target_semantic_digest_algorithm"] is not None:
            raise _err("meta.igpv.target_semantic_digest", "reserved: must be null until Semantic/2 freezes")
        rows: dict[str, list[dict]] = {}
        for name, fields, _key in TABLES:
            b = blocks[("table", name)]
            if set(b.fields) != set(fields):
                raise _err(f"table.{name}", f"fields {sorted(b.fields)} != {sorted(fields)}")
            if len(b.rows) > limits.max_rows_per_table:
                raise _limit("max_rows_per_table", f"table.{name} has {len(b.rows)} rows > {limits.max_rows_per_table}")
            rows[name] = b.rows
        payload = cls(
            target_artifact_sha256=meta["target_artifact_sha256"], target_serialization_profile=meta["target_serialization_profile"],
            artifacts=tuple(R.Artifact(r["artifact_id"], r["artifact_sha256"], r["kind"], r["size"], r["media_type"], r["revision"],
                                       r["uri"], r["serialization_profile"]) for r in rows["artifacts"]),
            producers=tuple(R.Producer(r["producer_id"], r["kind"], r["implementation"], r["version"], r["spec"], r["policy_sha256"])
                            for r in rows["producers"]),
            objects=tuple(_object_from_row(r) for r in rows["objects"]),
            attributions=tuple(_attribution_from_row(r) for r in rows["attributions"]),
            derivations=tuple(R.Derivation(r["derivation_id"], r["derived_object_id"], r["origin_object_id"], r["producer_id"], r["kind"])
                              for r in rows["derivations"]),
        )
        if payload.to_ison() != text:      # to_ison() runs check() first
            raise _err("canonical_form", "payload bytes are not the canonical writer's output for this document (row order included)")
        return payload

    def check(self) -> None:
        """P1 rules that need no bytes (18 §4.1 P1): field rules, then relation rules."""
        _check_fields(self)
        _check_relations(self)


def _collect_blocks(doc: Document) -> dict[tuple[str, str], Block]:
    required = {("meta", "igpv")} | {("table", name) for name, _f, _k in TABLES}
    out: dict[tuple[str, str], Block] = {}
    for b in doc.blocks:
        key = (b.kind, b.name)
        if key not in required:
            raise _err(f"{b.kind}.{b.name}", "unexpected block")
        if key in out:
            raise _err(f"{b.kind}.{b.name}", "duplicate block")
        out[key] = b
    for key in sorted(required - set(out)):
        raise _err(f"{key[0]}.{key[1]}", "missing block")
    return out


def _one_row(b: Block, name: str, expected: tuple[str, ...]) -> dict[str, Any]:
    if len(b.rows) != 1:
        raise _err(name, f"expected exactly one row, got {len(b.rows)}")
    row = b.rows[0]
    for f in expected:
        if f not in row:
            raise _err(f"{name}.{f}", "missing field")
    for f in row:
        if f not in expected:
            raise _err(f"{name}.{f}", "unexpected field")
    return row


def _need(cond: bool, field: str, detail: str) -> None:
    if not cond:
        raise _err(field, detail)


def _check_node_ref(ref: Any, where: str, type_col: str, id_col: str) -> None:
    _need(isinstance(ref, R.NodeRef), where, "NodeRef required")
    _need(R.is_identifier(ref.node_type), f"{where}.{type_col}", 'Core identifier (non-empty, no whitespace, none of : | " \\)')
    v = ref.node_id
    if R.is_int(v):
        _need(R.INT64_MIN <= v <= R.INT64_MAX, f"{where}.{id_col}", "integer id must lie within INT64")
    else:
        _need(R.is_str(v), f"{where}.{id_col}", "id must be an INT64 integer or a string (booleans, floats, null are not ids)")


def _opt_str(v: Any) -> bool:
    return v is None or (R.is_str(v) and v != "")


def _is_key(v: Any) -> bool:
    return R.is_str(v) and R.KEY_TOKEN.fullmatch(v) is not None


def _is_hex64(v: Any) -> bool:
    return R.is_str(v) and R.HEX64.fullmatch(v) is not None


def _utf8_ok(v: Any) -> bool:
    if not isinstance(v, str):
        return True
    try:
        v.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _check_utf8(p: ProvenancePayload) -> None:
    """Every string in every record must have a UTF-8 encoding: a lone surrogate has no bytes, so it has no digest."""
    def walk(value: Any, where: str) -> None:
        if isinstance(value, (R.NodeRef, R.EdgeAddress, R.Locator)):
            for f in dc_fields(value):
                walk(getattr(value, f.name), f"{where}.{f.name}" if isinstance(value, R.Locator) or isinstance(value, R.NodeRef) else where)
            return
        _need(_utf8_ok(value), where, "string is not UTF-8-encodable (lone surrogate)")

    for name, _fields, key in TABLES:
        for r in getattr(p, name):
            w = f"table.{name}.{getattr(r, key)}"
            for f in dc_fields(r):
                v = getattr(r, f.name)
                if isinstance(v, R.EdgeAddress):
                    walk(v.source.node_type, f"{w}.source_type"); walk(v.source.node_id, f"{w}.source_id")
                    walk(v.relation, f"{w}.relation")
                    walk(v.target.node_type, f"{w}.target_type"); walk(v.target.node_id, f"{w}.target_id")
                    walk(v.ordinal, f"{w}.ordinal")
                elif isinstance(v, R.NodeRef):
                    walk(v.node_type, f"{w}.node_type"); walk(v.node_id, f"{w}.node_id")
                elif isinstance(v, R.Locator):
                    walk(v.type, f"{w}.locator_type"); walk(v.text, f"{w}.locator_text")
                else:
                    walk(v, f"{w}.{f.name}")


def _check_fields(p: ProvenancePayload) -> None:
    _need(_is_hex64(p.target_artifact_sha256), "meta.igpv.target_artifact_sha256", "64 lowercase hex")
    _need(p.target_serialization_profile in R.PROFILES, "meta.igpv.target_serialization_profile", f"not one of {R.PROFILES}")
    _check_utf8(p)
    for a in p.artifacts:
        w = f"table.artifacts.{a.artifact_id}"
        _need(_is_key(a.artifact_id), f"{w}.artifact_id", "key token")
        _need(_is_hex64(a.artifact_sha256), f"{w}.artifact_sha256", "64 lowercase hex")
        _need(a.kind in R.ARTIFACT_KINDS, f"{w}.kind", f"not one of {R.ARTIFACT_KINDS}")
        _need(a.artifact_sha256 != p.target_artifact_sha256 or a.kind == "isongraph", f"{w}.kind",
              "an artifact carrying the target graph's digest must be isongraph (18 §1.1)")
        _need(R.is_int(a.size) and 0 <= a.size <= R.INT64_MAX, f"{w}.size", "INT64 in [0, 2^63-1]")
        _need(a.media_type is None or (R.is_str(a.media_type) and R.MEDIA_TYPE.fullmatch(a.media_type) is not None),
              f"{w}.media_type", "null or type/subtype")
        _need(_opt_str(a.revision), f"{w}.revision", "null or non-empty string")
        _need(_opt_str(a.uri), f"{w}.uri", "null or non-empty string")
        if a.kind == "isongraph":
            _need(a.serialization_profile in R.PROFILES, f"{w}.serialization_profile", f"isongraph artifacts need one of {R.PROFILES}")
        else:
            _need(a.serialization_profile is None, f"{w}.serialization_profile", "must be null unless kind is isongraph")
    for pr in p.producers:
        w = f"table.producers.{pr.producer_id}"
        _need(_is_key(pr.producer_id), f"{w}.producer_id", "key token")
        _need(pr.kind in R.PRODUCER_KINDS, f"{w}.kind", f"not one of {R.PRODUCER_KINDS}")
        _need(R.is_str(pr.implementation) and pr.implementation != "", f"{w}.implementation", "non-empty string")
        _need(R.is_str(pr.version) and pr.version != "", f"{w}.version", "non-empty string")
        _need(_opt_str(pr.spec), f"{w}.spec", "null or non-empty string")
        _need(pr.policy_sha256 is None or _is_hex64(pr.policy_sha256), f"{w}.policy_sha256", "null or 64 lowercase hex")
        if pr.kind == "extractor":
            _need(pr.policy_sha256 is None, f"{w}.policy_sha256", "extractors carry no policy digest")
    for o in p.objects:
        w = f"table.objects.{o.object_id}"
        _need(_is_key(o.object_id), f"{w}.object_id", "key token")
        _need(o.graph is None or _is_key(o.graph), f"{w}.graph", "null or artifact key token")
        _need(o.kind in R.OBJECT_KINDS, f"{w}.kind", f"not one of {R.OBJECT_KINDS}")
        if o.kind == "node":
            _need(o.node is not None, f"{w}.node", "node address required")
            _need(o.edge is None, f"{w}.edge", "must be absent for a node")
            _check_node_ref(o.node, w, "node_type", "node_id")
        elif o.kind == "edge":
            _need(isinstance(o.edge, R.EdgeAddress), f"{w}.edge", "edge address required")
            _need(o.node is None, f"{w}.node", "must be absent for an edge")
            _check_node_ref(o.edge.source, w, "source_type", "source_id")
            _need(R.is_identifier(o.edge.relation), f"{w}.relation", "Core identifier")
            _check_node_ref(o.edge.target, w, "target_type", "target_id")
            _need(R.is_str(o.edge.ordinal) and R.ORDINAL.fullmatch(o.edge.ordinal) is not None, f"{w}.ordinal",
                  'canonical decimal string ("0", "1", "10")')
        else:
            _need(o.node is None, f"{w}.node", "must be absent for a graph")
            _need(o.edge is None, f"{w}.edge", "must be absent for a graph")
    for at in p.attributions:
        w = f"table.attributions.{at.attribution_id}"
        for col, v in (("attribution_id", at.attribution_id), ("object_id", at.object_id), ("artifact_id", at.artifact_id),
                       ("producer_id", at.producer_id)):
            _need(_is_key(v), f"{w}.{col}", "key token")
        _need(at.locator is None or isinstance(at.locator, R.Locator), f"{w}.locator_type", "Locator or null")
    for d in p.derivations:
        w = f"table.derivations.{d.derivation_id}"
        for col, v in (("derivation_id", d.derivation_id), ("derived_object_id", d.derived_object_id),
                       ("origin_object_id", d.origin_object_id), ("producer_id", d.producer_id)):
            _need(_is_key(v), f"{w}.{col}", "key token")
        _need(d.kind in R.DERIVATION_KINDS, f"{w}.kind", f"not one of {R.DERIVATION_KINDS}")


def address_key(o: R.GraphObject) -> tuple:
    """Hashable address of an object inside its graph (18 §1.2): the lineage identity is (artifact_sha256, address_key)."""
    if o.kind == "node":
        return ("node", o.node)
    if o.kind == "edge":
        return ("edge", o.edge)
    return ("graph",)


def _sorted_by(rows, key):
    return sorted(rows, key=lambda r: _key_bytes(key(r)))


def _check_relations(p: ProvenancePayload) -> None:
    """Relation rules (18 §1.1): uniqueness, twins, locator shape, duplicates, reachability."""
    for name, col, rows in (("artifacts", "artifact_id", p.artifacts), ("producers", "producer_id", p.producers),
                            ("objects", "object_id", p.objects), ("attributions", "attribution_id", p.attributions),
                            ("derivations", "derivation_id", p.derivations)):
        seen: set = set()
        for r in rows:
            k = getattr(r, col)
            _need(k not in seen, f"table.{name}.{k}.{col}", "duplicate key")
            seen.add(k)
    digests: dict[str, str] = {}
    for a in p.artifacts:
        _need(a.artifact_sha256 not in digests, f"table.artifacts.{a.artifact_id}.artifact_sha256",
              f"same digest as {digests.get(a.artifact_sha256)}: one artifact record per content digest")
        digests[a.artifact_sha256] = a.artifact_id
    # object addresses unique per graph; twin ids per (graph, node_type) over object rows and edge endpoints
    addresses: dict[tuple, str] = {}
    ints: dict[tuple, str] = {}     # (graph, type, decimal spelling) -> object_id that mentioned the INT64 id
    strs: dict[tuple, str] = {}     # (graph, type, string)           -> object_id that mentioned the STRING id
    for o in _sorted_by(p.objects, lambda o: o.object_id):
        w = f"table.objects.{o.object_id}"
        key = (o.graph,) + address_key(o)
        col = "node_id" if o.kind == "node" else "relation" if o.kind == "edge" else "kind"
        _need(key not in addresses, f"{w}.{col}", f"same address as {addresses.get(key)}")
        addresses[key] = o.object_id
        refs = ([(o.node, "node_id")] if o.kind == "node"
                else [(o.edge.source, "source_id"), (o.edge.target, "target_id")] if o.kind == "edge" else [])
        for ref, col in refs:
            if R.is_int(ref.node_id):
                k = (o.graph, ref.node_type, str(ref.node_id))
                _need(k not in strs, f"{w}.{col}", f"INT64 id {ref.node_id} is a twin of a STRING id in {strs.get(k)} (ID-TWIN-INVARIANT)")
                ints.setdefault(k, o.object_id)
            else:
                k = (o.graph, ref.node_type, ref.node_id)
                _need(k not in ints, f"{w}.{col}", f"STRING id {ref.node_id!r} is a twin of an INT64 id in {ints.get(k)} (ID-TWIN-INVARIANT)")
                strs.setdefault(k, o.object_id)
    sizes = {a.artifact_id: a.size for a in p.artifacts}
    seen_at: set = set()
    for at in _sorted_by(p.attributions, lambda a: a.attribution_id):
        w = f"table.attributions.{at.attribution_id}"
        if at.artifact_id in sizes:
            check_locator_shape(at.locator, sizes[at.artifact_id], w)
        k = (at.object_id, at.artifact_id, at.producer_id, at.locator)
        _need(k not in seen_at, f"{w}.attribution_id", "duplicate attribution (same object, artifact, producer, locator)")
        seen_at.add(k)
    seen_d: set = set()
    for d in _sorted_by(p.derivations, lambda d: d.derivation_id):
        k = (d.derived_object_id, d.origin_object_id)
        _need(k not in seen_d, f"table.derivations.{d.derivation_id}.origin_object_id", "duplicate (derived, origin) pair")
        seen_d.add(k)
    # reachability (18 §1.1)
    reach_obj = ({a.object_id for a in p.attributions} | {d.derived_object_id for d in p.derivations}
                 | {d.origin_object_id for d in p.derivations})
    reach_prod = {a.producer_id for a in p.attributions} | {d.producer_id for d in p.derivations}
    reach_art = ({a.artifact_id for a in p.attributions}
                 | {o.graph for o in p.objects if o.object_id in reach_obj and o.graph is not None})
    for a in _sorted_by(p.artifacts, lambda a: a.artifact_id):
        _need(a.artifact_id in reach_art, f"table.artifacts.{a.artifact_id}.artifact_id",
              "unreachable: no attribution or reachable object references it")
    for pr in _sorted_by(p.producers, lambda x: x.producer_id):
        _need(pr.producer_id in reach_prod, f"table.producers.{pr.producer_id}.producer_id",
              "unreachable: no attribution or derivation references it")
    for o in _sorted_by(p.objects, lambda o: o.object_id):
        _need(o.object_id in reach_obj, f"table.objects.{o.object_id}.object_id",
              "unreachable: no attribution or derivation references it")


def check_references(p: ProvenancePayload) -> None:
    """P3 (18 §4.1): every reference resolves inside the payload; the derivation rules of §3 hold."""
    arts = {a.artifact_id: a for a in p.artifacts}
    prods = {x.producer_id for x in p.producers}
    objs = {o.object_id: o for o in p.objects}

    def unresolved(field: str, detail: str) -> None:
        raise IGPVError("UNRESOLVED_REFERENCE", field, detail, "P3")

    def invalid(field: str, detail: str) -> None:
        raise IGPVError("INVALID_DERIVATION", field, detail, "P3")

    for o in _sorted_by(p.objects, lambda o: o.object_id):
        if o.graph is not None:
            a = arts.get(o.graph)
            if a is None:
                unresolved(f"table.objects.{o.object_id}.graph", f"unknown artifact {o.graph!r}")
            if a.kind != "isongraph":
                unresolved(f"table.objects.{o.object_id}.graph", f"artifact {o.graph!r} is {a.kind}, not isongraph")
    for at in _sorted_by(p.attributions, lambda a: a.attribution_id):
        w = f"table.attributions.{at.attribution_id}"
        if at.object_id not in objs:
            unresolved(f"{w}.object_id", f"unknown object {at.object_id!r}")
        if at.artifact_id not in arts:
            unresolved(f"{w}.artifact_id", f"unknown artifact {at.artifact_id!r}")
        if at.producer_id not in prods:
            unresolved(f"{w}.producer_id", f"unknown producer {at.producer_id!r}")
    per_derived: dict[str, int] = {}
    for d in p.derivations:
        per_derived[d.derived_object_id] = per_derived.get(d.derived_object_id, 0) + 1
    for d in _sorted_by(p.derivations, lambda d: d.derivation_id):
        w = f"table.derivations.{d.derivation_id}"
        if d.derived_object_id not in objs:
            unresolved(f"{w}.derived_object_id", f"unknown object {d.derived_object_id!r}")
        if d.origin_object_id not in objs:
            unresolved(f"{w}.origin_object_id", f"unknown object {d.origin_object_id!r}")
        if d.producer_id not in prods:
            unresolved(f"{w}.producer_id", f"unknown producer {d.producer_id!r}")
        der, ori = objs[d.derived_object_id], objs[d.origin_object_id]
        if der.graph is not None:
            invalid(f"{w}.derived_object_id", "derived object must be in the target graph (graph null)")
        if ori.graph is None:
            invalid(f"{w}.origin_object_id", "origin object must be in an origin graph (self-derivation)")
        if arts[ori.graph].artifact_sha256 == p.target_artifact_sha256:
            invalid(f"{w}.origin_object_id", "origin graph is the target graph itself")
        if der.kind != ori.kind:
            invalid(f"{w}.origin_object_id", f"derived {der.kind} from origin {ori.kind}: kinds must match")
        if d.kind == "identity":
            if per_derived[d.derived_object_id] != 1:
                invalid(f"{w}.kind", "identity requires exactly one derivation row for the derived object")
            if address_key(der) != address_key(ori):
                invalid(f"{w}.kind", "identity requires equal addresses in origin and target")

# scripts/make_vectors_igdc.py   (Part A: vectors/igs-addr; Part B: vectors/igdc1)
"""Generate the IGDC/1 vector sets (26 §5). Independent of the production package: it never imports isongraph_ext.igdc (Part B uses the existing igx/igdm only as input builders and verdict oracles).

    python scripts/make_vectors_igdc.py --addr     # vectors/igs-addr  (hand-written literals; Task 2)
    python scripts/make_vectors_igdc.py            # also vectors/igdc1 (reference deriver; Task 5)

Typed literals keep a value's TYPE explicit so no reader ever infers it from digits:
    int:7  str:7  bool:true  float:1.5  null:  surrogate:d800 (a one-character str holding a lone surrogate)
    tagged:i:7  tagged-lone:d800 (the text "s:" followed by a lone surrogate)
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical, loads

ROOT = Path(__file__).resolve().parents[1]
I64_MIN, I64_MAX = -(2**63), 2**63 - 1
BAD = "reject:INVALID_ADDRESS"

# ---- table.vectors: id | kind | input | expect --------------------------------------------------------------------------
TAG = [  # kind "tag": a value's type decides its tag; spelling never does
    ("ok/int-7", "int:7", "i:7"), ("ok/string-7", "str:7", "s:7"), ("ok/int-zero", "int:0", "i:0"), ("ok/int-negative-one", "int:-1", "i:-1"),
    ("ok/int64-min", f"int:{I64_MIN}", f"i:{I64_MIN}"), ("ok/int64-max", f"int:{I64_MAX}", f"i:{I64_MAX}"),
    ("ok/string-007", "str:007", "s:007"), ("ok/string-minus0", "str:-0", "s:-0"), ("ok/string-1e3", "str:1e3", "s:1e3"),
    ("ok/string-leading-plus", "str:+5", "s:+5"), ("ok/string-looks-tagged-i", "str:i:7", "s:i:7"), ("ok/string-looks-tagged-s", "str:s:7", "s:s:7"),
    ("ok/string-beyond-int64", f"str:{I64_MAX + 1}", f"s:{I64_MAX + 1}"), ("ok/string-arabic-indic-digit", "str:\u0663", "s:\u0663"),
    ("ok/string-nfc", "str:\u00e9", "s:\u00e9"), ("ok/string-nfd", "str:e\u0301", "s:e\u0301"), ("ok/string-astral", "str:\U0001f600", "s:\U0001f600"),
    ("ok/string-fullwidth-tilde", "str:\uff5e", "s:\uff5e"), ("ok/string-with-quote", 'str:q"q', 's:q"q'),
    ("ok/string-empty-is-valid-syntax", "str:", "s:"),
    ("reject/int64-overflow", f"int:{I64_MAX + 1}", BAD), ("reject/int64-underflow", f"int:{I64_MIN - 1}", BAD),
    ("reject/bool-true-id", "bool:true", BAD), ("reject/bool-false-id", "bool:false", BAD), ("reject/float-id", "float:1.5", BAD),
    ("reject/float-integral-id", "float:7.0", BAD), ("reject/null-id", "null:", BAD), ("reject/lone-surrogate-id", "surrogate:d800", BAD),
]
PARSE = [  # kind "parse": the inverse; expect is a typed literal
    ("ok/parse-i-7", "tagged:i:7", "int:7"), ("ok/parse-s-7", "tagged:s:7", "str:7"), ("ok/parse-s-007", "tagged:s:007", "str:007"),
    ("ok/parse-s-looks-tagged", "tagged:s:i:7", "str:i:7"), ("ok/parse-s-empty", "tagged:s:", "str:"),
    ("ok/parse-i-min", f"tagged:i:{I64_MIN}", f"int:{I64_MIN}"), ("ok/parse-i-max", f"tagged:i:{I64_MAX}", f"int:{I64_MAX}"),
    ("reject/parse-bare-7", "tagged:7", BAD), ("reject/parse-i-leading-zero", "tagged:i:007", BAD), ("reject/parse-i-minus-zero", "tagged:i:-0", BAD),
    ("reject/parse-i-plus", "tagged:i:+5", BAD), ("reject/parse-i-empty", "tagged:i:", BAD), ("reject/parse-i-decimal-point", "tagged:i:1.0", BAD),
    ("reject/parse-i-space", "tagged:i: 7", BAD), ("reject/parse-i-trailing-space", "tagged:i:7 ", BAD),
    ("reject/parse-i-arabic-indic-digit", "tagged:i:\u0663", BAD), ("reject/parse-i-overflow", f"tagged:i:{I64_MAX + 1}", BAD),
    ("reject/parse-i-underflow", f"tagged:i:{I64_MIN - 1}", BAD), ("reject/parse-unknown-tag", "tagged:x:7", BAD),
    ("reject/parse-uppercase-tag", "tagged:I:7", BAD), ("reject/parse-empty", "tagged:", BAD), ("reject/parse-tag-without-colon", "tagged:i", BAD),
    ("reject/parse-s-lone-surrogate", "tagged-lone:d800", BAD),
]
IDENT = [  # kinds "node_type" and "relation" share Core's identifier rule: non-empty, no whitespace, none of : | " \
    *[(f"ok/{k}-{n}", k, v, "ok") for k in ("node_type", "relation") for n, v in (("plain", "order"), ("unicode", "\u00e9tude"), ("punctuation", "a-b_c.d"))],
    *[(f"reject/{k}-{n}", k, v, BAD) for k in ("node_type", "relation") for n, v in
      (("empty", "str:"), ("space", "str:a b"), ("colon", "str:a:b"), ("pipe", "str:a|b"), ("quote", 'str:a"b'), ("backslash", "str:a\\b"), ("tab", "str:a\tb"))],
]
IDENT = [(i, k, v if v.startswith("str:") else f"str:{v}", e) for i, k, v, e in IDENT]

# ---- table.edges: one logical edge; directed / multigraph decide which ordinals and endpoint orders are legal ---------------
# id | source_type source_id | relation | target_type target_id | ordinal | directed multigraph | expect | expect_source expect_target
EDGES = [
    ("ok/directed-as-written", "a", "int:9", "r", "a", "int:1", "0", "true", "false", "ok", "i:9", "i:1"),
    ("ok/directed-string-to-int", "a", "str:x", "r", "a", "int:1", "0", "true", "false", "ok", "s:x", "i:1"),
    ("ok/undirected-canonical-int-before-string", "a", "int:5", "r", "a", "str:a", "0", "false", "false", "ok", "i:5", "s:a"),
    ("ok/undirected-canonical-ints-numeric", "a", "int:3", "r", "a", "int:5", "0", "false", "false", "ok", "i:3", "i:5"),
    ("ok/undirected-canonical-negative-first", "a", "int:-1", "r", "a", "int:0", "0", "false", "false", "ok", "i:-1", "i:0"),
    ("ok/undirected-canonical-type-bytes", "a", "int:9", "r", "b", "int:1", "0", "false", "false", "ok", "i:9", "i:1"),
    ("ok/undirected-self-loop", "a", "int:3", "r", "a", "int:3", "0", "false", "false", "ok", "i:3", "i:3"),
    ("ok/multigraph-ordinal-0", "a", "int:1", "r", "a", "int:2", "0", "true", "true", "ok", "i:1", "i:2"),
    ("ok/multigraph-ordinal-1", "a", "int:1", "r", "a", "int:2", "1", "true", "true", "ok", "i:1", "i:2"),
    ("ok/multigraph-ordinal-10", "a", "int:1", "r", "a", "int:2", "10", "true", "true", "ok", "i:1", "i:2"),
    ("reject/undirected-string-before-int", "a", "str:a", "r", "a", "int:5", "0", "false", "false", BAD, "", ""),
    ("reject/undirected-ints-out-of-order", "a", "int:5", "r", "a", "int:3", "0", "false", "false", BAD, "", ""),
    ("reject/undirected-type-bytes-out-of-order", "b", "int:1", "r", "a", "int:9", "0", "false", "false", BAD, "", ""),
    ("reject/simple-graph-ordinal-1", "a", "int:1", "r", "a", "int:2", "1", "true", "false", BAD, "", ""),
    ("reject/ordinal-leading-zero", "a", "int:1", "r", "a", "int:2", "01", "true", "true", BAD, "", ""),
    ("reject/ordinal-double-zero", "a", "int:1", "r", "a", "int:2", "00", "true", "true", BAD, "", ""),
    ("reject/ordinal-negative", "a", "int:1", "r", "a", "int:2", "-1", "true", "true", BAD, "", ""),
    ("reject/ordinal-empty", "a", "int:1", "r", "a", "int:2", "", "true", "true", BAD, "", ""),
    ("reject/ordinal-not-ascii-digit", "a", "int:1", "r", "a", "int:2", "\u0663", "true", "true", BAD, "", ""),
]

# ---- table.order: a set of node addresses and the rank each must have in SEMANTIC order ----------------------------------
# id | set | trap | node_type | node_id | position.  `id` names the vector, its rows are the members of one set.
# trap=text: sorting (node_type, tagged id) as plain text gives a DIFFERENT order; trap=utf16: sorting by UTF-16 code units does; none: no claim.
ORDER = [
    *[("ok/order-mixed", "mixed", "text", t, v, p) for t, v, p in
      [("a", "int:-1", 0), ("a", "int:0", 1), ("a", "int:2", 2), ("a", "int:10", 3), ("a", "str:a", 4), ("a", "str:~", 5), ("a", "str:\u00e9", 6),
       ("a", "str:\U0001f600", 7), ("b", "int:1", 8), ("b", "str:a", 9)]],
    *[("ok/order-ints-numeric-not-text", "ints", "text", "t", v, p) for v, p in [("int:-10", 0), ("int:-2", 1), ("int:0", 2), ("int:2", 3), ("int:10", 4), ("int:100", 5)]],
    *[("ok/order-every-int-before-every-string", "intstr", "none", "t", v, p) for v, p in [("int:9223372036854775807", 0), ("str:", 1), ("str:0", 2)]],
    *[("ok/order-int64-extremes", "extremes", "text", "t", v, p) for v, p in [(f"int:{I64_MIN}", 0), ("int:-1", 1), ("int:0", 2), (f"int:{I64_MAX}", 3)]],
    *[("ok/order-utf8-not-utf16", "utf8", "utf16", "t", v, p) for v, p in [("str:\uff5e", 0), ("str:\U0001f600", 1)]],
    *[("ok/order-type-bytes-first", "types", "none", t, v, p) for t, v, p in [("a", "int:9", 0), ("a", "str:z", 1), ("b", "int:1", 2), ("\u00e9", "int:0", 3)]],
    *[("ok/order-string-bytes-not-case-folded", "strings", "none", "t", v, p) for v, p in [("str:A", 0), ("str:B", 1), ("str:a", 2), ("str:b", 3)]],
]
# ---- table.edge_order: source, relation bytes, target, ordinal bytes ---------------------------------------------------------
# id | set | source_type source_id | relation | target_type target_id | ordinal | position
EDGE_ORDER = [
    *[("ok/edge-order-ordinal-bytes", "ordinals", "t", "int:1", "r", "t", "int:2", o, p) for o, p in [("0", 0), ("1", 1), ("10", 2), ("2", 3)]],
    *[("ok/edge-order-relation-bytes", "relations", "t", "int:1", r, "t", "int:2", "0", p) for r, p in [("a", 0), ("b", 1), ("c", 2)]],
    *[("ok/edge-order-source-then-relation", "srcrel", "t", s, r, "t", "int:9", "0", p) for s, r, p in
      [("int:1", "z", 0), ("int:2", "a", 1), ("int:2", "b", 2), ("str:a", "a", 3)]],
]
# ---- table.twins: ID-TWIN-INVARIANT ---------------------------------------------------------------------------------------
# id | type_a id_a | type_b id_b | expect
TWINS = [
    ("reject/twin-i7-s7", "a", "int:7", "a", "str:7", "reject:TWIN_IDS"), ("reject/twin-s7-i7-reversed", "a", "str:7", "a", "int:7", "reject:TWIN_IDS"),
    ("reject/twin-i0-s0", "a", "int:0", "a", "str:0", "reject:TWIN_IDS"), ("reject/twin-negative", "a", "int:-7", "a", "str:-7", "reject:TWIN_IDS"),
    ("ok/twin-not-s007-vs-i7", "a", "int:7", "a", "str:007", "ok"), ("ok/twin-not-s-minus0-vs-i0", "a", "int:0", "a", "str:-0", "ok"),
    ("ok/twin-not-across-types", "a", "int:7", "b", "str:7", "ok"), ("ok/twin-not-two-ints", "a", "int:7", "a", "int:8", "ok"),
]


def _vec_rows():
    rows = [{"id": i, "kind": "tag", "input": a, "expect": e} for i, a, e in TAG]
    rows += [{"id": i, "kind": "parse", "input": a, "expect": e} for i, a, e in PARSE]
    rows += [{"id": i, "kind": k, "input": a, "expect": e} for i, k, a, e in IDENT]
    return rows


TABLES = (
    ("vectors", ["id", "kind", "input", "expect"], _vec_rows),
    ("edges", ["id", "source_type", "source_id", "relation", "target_type", "target_id", "ordinal", "directed", "multigraph", "expect", "expect_source", "expect_target"],
     lambda: [dict(zip(["id", "source_type", "source_id", "relation", "target_type", "target_id", "ordinal", "directed", "multigraph", "expect", "expect_source", "expect_target"], r)) for r in EDGES]),
    ("order", ["id", "trap", "node_type", "node_id", "position"], lambda: [dict(zip(["id", "trap", "node_type", "node_id", "position"], r[:1] + r[2:])) for r in ORDER]),
    ("edge_order", ["id", "source_type", "source_id", "relation", "target_type", "target_id", "ordinal", "position"],
     lambda: [dict(zip(["id", "source_type", "source_id", "relation", "target_type", "target_id", "ordinal", "position"], r[:1] + r[2:])) for r in EDGE_ORDER]),
    ("twins", ["id", "type_a", "id_a", "type_b", "id_b", "expect"], lambda: [dict(zip(["id", "type_a", "id_a", "type_b", "id_b", "expect"], r)) for r in TWINS]),
)

README = """# vectors/igs-addr — IGDC/1 typed-address vectors (26 §1, §5)

Hand-written literals, independent of `isongraph_ext.igdc`. Every row of every table is normative: a port claims conformance by passing ALL rows
(the manifest row counts are part of the claim). Values are typed literals (`int:7` is an integer, `str:7` a string, `surrogate:d800` a lone
surrogate); no reader may infer a type from digits. `SHA256SUMS` pins the files; `manifest.ison` is canonical ison-py output.

Tables: `vectors` (tag, parse, node_type, relation) · `edges` · `order` · `edge_order` · `twins`.
"""


def write_set(directory: Path, tables, readme: str) -> dict[str, int]:
    directory.mkdir(parents=True, exist_ok=True)
    blocks, counts, ids = [], {}, set()
    for name, cols, rows_fn in tables:
        rows = rows_fn()
        for r in rows:
            assert set(r) == set(cols), (name, r)
        counts[name] = len(rows)
        blocks.append(Block("table", name, cols, rows))
    text = dumps_canonical(Document(blocks=blocks))
    again = loads(text)
    for b, (name, cols, rows_fn) in zip(sorted(again.blocks, key=lambda b: b.name), sorted(tables, key=lambda t: t[0])):    # cells survive the writer
        key = lambda r: repr(sorted(r.items()))  # noqa: E731  (the writer orders rows; compare as sets of rows)
        assert sorted(b.rows, key=key) == sorted(rows_fn(), key=key), f"table {name} did not round-trip through the canonical writer"
    (directory / "manifest.ison").write_bytes(text.encode("utf-8"))
    (directory / "README.md").write_bytes(readme.encode("utf-8"))
    sums = "".join(f"{hashlib.sha256((directory / n).read_bytes()).hexdigest()}  {n}\n" for n in sorted(p.name for p in directory.iterdir() if p.name != "SHA256SUMS"))
    (directory / "SHA256SUMS").write_bytes(sums.encode("utf-8"))
    return counts


# =====================================================================================================================
# Part B - vectors/igdc1 (Task 5). Inputs are built with the EXISTING public igx/igdm API and verified with the existing
# verification path (as verdict oracles); the expected hint documents come from reference_derive below, which reads the
# PARSED IGDM/1 wire document and imports only ison_parser. The production `isongraph_ext.igdc` is never imported here.
# =====================================================================================================================
X_COLS = {"role", "ring", "a11y_role", "shape_role", "pattern_role", "family"}
NODE_H = ["magnitude", "role", "shape_role", "emphasis", "badge", "ring", "label", "visibility", "lod_min", "selectable", "focusable", "expandable",
          "drilldown", "temporal_state", "temporal_order", "layout_rank", "layout_anchor", "a11y_text", "a11y_role"]
EDGE_H = ["role", "pattern_role", "emphasis", "direction_display", "label", "visibility", "lod_min", "selectable", "focusable", "temporal_state",
          "temporal_order", "a11y_text"]
GROUP_H = ["parent_group_id", "label", "role", "collapsed", "visibility", "lod_min", "a11y_text"]
META_C = ["consumption_spec", "address_scheme", "igdm_payload_sha256", "target_artifact_sha256", "target_directed", "target_multigraph", "target_serialization_profile"]


def _tag(v):                                  # the cell type of the PARSED payload decides, never the spelling
    assert not isinstance(v, bool)
    return f"i:{v}" if isinstance(v, int) else f"s:{v}"


def _split(row, cols):
    out = {}
    for c in cols:
        v = row[c]
        isx = c in X_COLS and isinstance(v, str) and v.startswith("x-")
        out[c] = None if isx else v
        if c in X_COLS:
            out[c + "_x"] = v if isx else None
    return out


def _xcols(cols):
    return [y for c in cols for y in ([c, c + "_x"] if c in X_COLS else [c])]


def reference_derive(payload_bytes: bytes, directed: bool, multigraph: bool) -> str:
    doc = loads(payload_bytes.decode("utf-8"))
    B = {(b.kind, b.name): b for b in doc.blocks}
    m, lay = B[("meta", "igdm")].rows[0], B[("meta", "layout")].rows[0]
    tok = lambda b: "true" if b else "false"  # noqa: E731
    nodes = [{"node_type": r["node_type"], "node_id": _tag(r["node_id"]), **_split(r, NODE_H)} for r in B[("table", "nodes")].rows]
    edges = [{"source_type": r["source_type"], "source_id": _tag(r["source_id"]), "relation": r["relation"], "target_type": r["target_type"],
              "target_id": _tag(r["target_id"]), "ordinal": r["ordinal"], **_split(r, EDGE_H)} for r in B[("table", "edges")].rows]
    groups = [{"group_id": r["group_id"], "intent": r["intent"], **_split(r, GROUP_H)} for r in B[("table", "groups")].rows]
    members = [{"group_id": r["group_id"], "node_type": r["node_type"], "node_id": _tag(r["node_id"])} for r in B[("table", "members")].rows]
    f = lay["family"]
    isx = isinstance(f, str) and f.startswith("x-")
    lay2 = {"family": None if isx else f, "family_x": f if isx else None, "direction": lay["direction"], "stability": lay["stability"]}
    sha = hashlib.sha256(payload_bytes).hexdigest()
    return dumps_canonical(Document(blocks=[
        Block("meta", "igdc", META_C, [{"consumption_spec": "IGDC/1", "address_scheme": "igs-addr/1", "igdm_payload_sha256": sha,
              "target_artifact_sha256": m["target_artifact_sha256"], "target_directed": tok(directed), "target_multigraph": tok(multigraph),
              "target_serialization_profile": m["target_serialization_profile"]}]),
        Block("meta", "layout", ["family", "family_x", "direction", "stability"], [lay2]),
        Block("table", "nodes", ["node_type", "node_id"] + _xcols(NODE_H), nodes),
        Block("table", "edges", ["source_type", "source_id", "relation", "target_type", "target_id", "ordinal"] + _xcols(EDGE_H), edges),
        Block("table", "groups", ["group_id", "intent"] + _xcols(GROUP_H), groups),
        Block("table", "members", ["group_id", "node_type", "node_id"], members)]))


# ---- scenario inputs ----------------------------------------------------------------------------------------------------
def build_consumption(out: Path) -> dict[str, int]:
    sys.path.insert(0, str(ROOT / "isongraph-ext" / "src"))
    sys.path.insert(0, str(ROOT / "isongraph-ext" / "tests"))
    import shutil

    from conftest import all_baselines
    from ison_graph import ISONGraph

    from isongraph_ext.igdm.bind import verify_and_admit
    from isongraph_ext.igdm.errors import IGDMError
    from isongraph_ext.igdm.payload import DatamaticsPayload
    from isongraph_ext.igdm.records import EdgeHints, Group, LayoutHints, Limits, Member, NodeHints
    from isongraph_ext.igpv.records import EdgeAddress, NodeRef
    from isongraph_ext.igx.bind import bind as igx_bind
    from isongraph_ext.igx.binding import Capability, ExtensionBinding
    from isongraph_ext.igx.errors import IGXError

    IGDM = ROOT / "vectors" / "igdm1"
    BASES = all_baselines()
    sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    for sub in ("targets", "bindings", "payloads", "hints"):
        shutil.rmtree(out / sub, ignore_errors=True)
        (out / sub).mkdir(parents=True)
    rows: list[dict] = []

    def put(sub: str, name: str, data: bytes) -> str:
        (out / sub / name).write_bytes(data)
        return f"{sub}/{name}"

    def slug(i: str) -> str:
        return i.replace("/", "--")

    def row(id_, op, *, target=None, binding=None, payload=None, hints=None, expect, code=None, step=None, detail=None):
        rows.append({"id": id_, "op": op, "target": target, "binding": binding, "payload": payload, "hints": hints, "expect": expect,
                     "code": code, "step": step, "detail": detail})

    def bind_for(target: bytes, payload_text: str, profile: str = "ison-v1") -> str:
        return igx_bind(target, serialization_profile=profile, producer_port="python", identity_claim="artifact",
                        capabilities=(Capability("igdm", "^1", "REQUIRED", sha(payload_text.encode("utf-8"))),)).to_ison()

    def oracle_ok(target: bytes, binding_text: str, payload_text: str) -> None:
        _, dm, adm = verify_and_admit(payload_text.encode("utf-8"), ExtensionBinding.from_ison(binding_text), target, baselines=BASES)
        assert dm.object_resolution == "full" and adm.admitted, "scenario input must verify fully and be admitted"

    ok_hints: dict[str, str] = {}

    def ok_row(id_, target: bytes, payload_text: str, directed: bool, multigraph: bool, *, binding_text: str | None = None, profile="ison-v1", detail=None):
        binding_text = binding_text or bind_for(target, payload_text, profile)
        oracle_ok(target, binding_text, payload_text)
        s = slug(id_)
        h = reference_derive(payload_text.encode("utf-8"), directed, multigraph)
        ok_hints[id_] = h
        row(id_, "consume", target=put("targets", f"{sha(target)[:16]}.ison", target), binding=put("bindings", f"{s}.igx.ison", binding_text.encode()),
            payload=put("payloads", f"{s}.igdm.ison", payload_text.encode()), hints=put("hints", f"{s}.igdc.ison", h.encode()), expect="ok", detail=detail)

    # (a) copies of frozen IGDM/1 inputs: directedness is a property of the graph file
    flags = {"directed.ison": (True, False), "undirected.ison": (False, False), "multi.ison": (True, True)}
    manifest = {r["id"]: r for r in loads((IGDM / "manifest.ison").read_text(encoding="utf-8")).blocks[1].rows}
    for src, new in [("ok/node-hints-full-row", "ok/node-hints-full-row"), ("ok/edge-hints", "ok/edge-hints"), ("ok/multigraph-edge-ordinal", "ok/multigraph-ordinals"),
                     ("ok/undirected-edge-canonical", "ok/undirected-canonical-endpoints"), ("ok/groups-nested-hull-and-collapse", "ok/groups-members-resolved"),
                     ("ok/hierarchy-chain", "ok/hierarchy-chain"), ("ok/x-roles-preserved", "ok/x-roles-preserved"), ("ok/layout-only", "ok/layout-only"),
                     ("ok/empty-datamatics", "ok/empty-datamatics"), ("ok/empty-hull-group", "ok/empty-hull-group")]:
        m = manifest[src]
        graph = (IGDM / "graphs" / m["target"]).read_bytes()
        ok_row(new, graph, (IGDM / "payloads" / m["payload"]).read_text(encoding="utf-8"), *flags[Path(m["target"]).name],
               binding_text=(IGDM / "bindings" / m["binding"]).read_text(encoding="utf-8"))

    N = NodeRef

    def payload_for(target: bytes, profile="ison-v1", **kw) -> str:
        return DatamaticsPayload(sha(target), profile, **kw).to_ison()

    # (b) new scenarios
    g = ISONGraph()
    for t, i in [("a", 7), ("a", "s"), ("b", "7"), ("c", 7)]:
        g.add_node(t, i)
    g.add_edge("r", ("a", 7), ("b", "7"))
    T = g.to_ison().encode("utf-8")
    ok_row("ok/id-types-distinct", T, payload_for(T, nodes=tuple(NodeHints(N(t, i), role="info") for t, i in [("a", 7), ("a", "s"), ("b", "7"), ("c", 7)]),
           edges=(EdgeHints(EdgeAddress(N("a", 7), "r", N("b", "7")), role="neutral"),), groups=(Group("g", "hull"),),
           members=tuple(Member("g", N(t, i)) for t, i in [("a", 7), ("a", "s"), ("b", "7"), ("c", 7)])), True, False)

    digit_like = ["007", "-0", "+5", "1e3", "7", str(I64_MAX + 1), 'q"q', "é", "é", "\U0001f600", "～", "-", "~"]
    g = ISONGraph()
    for s in digit_like:
        g.add_node("t", s)
    g.add_edge("r", ("t", "007"), ("t", "-0"))
    T = g.to_ison().encode("utf-8")
    ok_row("ok/string-ids-digit-like-and-unicode", T, payload_for(T, nodes=tuple(NodeHints(N("t", s), role="info") for s in digit_like),
           edges=(EdgeHints(EdgeAddress(N("t", "007"), "r", N("t", "-0")), role="neutral"),)), True, False)

    ints = [I64_MIN, -1, 0, I64_MAX]
    g = ISONGraph()
    for i in ints:
        g.add_node("t", i)
    g.add_edge("r", ("t", I64_MIN), ("t", I64_MAX))
    T = g.to_ison().encode("utf-8")
    ok_row("ok/int64-extremes", T, payload_for(T, nodes=tuple(NodeHints(N("t", i), label=f"n{i}") for i in ints),
           edges=(EdgeHints(EdgeAddress(N("t", I64_MIN), "r", N("t", I64_MAX)), role="info"),), groups=(Group("g", "hull"),),
           members=tuple(Member("g", N("t", i)) for i in (I64_MIN, I64_MAX))), True, False)

    mixed = [10, 2, -1, 0, "é", "a"]
    g = ISONGraph()
    for i in mixed:
        g.add_node("t", i)
    g.add_edge("r", ("t", 10), ("t", 2))
    g.add_edge("r", ("t", 2), ("t", -1))
    T = g.to_ison().encode("utf-8")
    ok_row("ok/int-id-ordering-trap", T, payload_for(T, nodes=tuple(NodeHints(N("t", i), role="info") for i in mixed),
           edges=(EdgeHints(EdgeAddress(N("t", 10), "r", N("t", 2)), role="neutral"), EdgeHints(EdgeAddress(N("t", 2), "r", N("t", -1)), role="neutral"))), True, False,
           detail="file row order is NOT semantic order: i:10 precedes i:2 as text")

    g = ISONGraph()
    for i in (1, 2, 3, 4, 5):
        g.add_node("n", i)
    for a, b in ((1, 2), (2, 3), (3, 4), (4, 5)):
        g.add_edge("r", ("n", a), ("n", b))
    T = g.to_ison().encode("utf-8")
    allx = payload_for(T, layout=LayoutHints("x-radial-ish", "TB", "free"),
                       nodes=(NodeHints(N("n", 1), role="x-risk", ring="x-halo", a11y_role="x-alert", shape_role="x-star"),
                              NodeHints(N("n", 2), role="warning", ring="info", a11y_role="info", shape_role="circle")),
                       edges=(EdgeHints(EdgeAddress(N("n", 1), "r", N("n", 2)), role="x-bridge", pattern_role="x-wavy"),
                              EdgeHints(EdgeAddress(N("n", 2), "r", N("n", 3)), role="negative", pattern_role="dashed")),
                       groups=(Group("g", "hull", role="x-zone"), Group("h", "hull", role="neutral")),
                       members=(Member("g", N("n", 1)), Member("h", N("n", 2))))
    ok_row("ok/x-roles-all-columns", T, allx, True, False, detail="all six x-capable columns carry one x- token and one closed value")
    ok_row("ok/layout-intent", T, payload_for(T, layout=LayoutHints("radial", "BT", "free"),
           nodes=(NodeHints(N("n", 1), layout_rank=0, layout_anchor=True), NodeHints(N("n", 2), layout_rank=1))), True, False)
    ok_row("ok/accessibility-fields", T, payload_for(T, nodes=(
           NodeHints(N("n", 1), a11y_text='Order "one" | a:bé \U0001f600', a11y_role="info", label='He said "hi"', badge="3", visibility="collapsed", lod_min=2),
           NodeHints(N("n", 2), label="plain", visibility="hidden", lod_min=1024))), True, False)
    ok_row("ok/int64-hint-values", T, payload_for(T, nodes=(NodeHints(N("n", 1), temporal_order=2**53 + 1, layout_rank=I64_MAX, lod_min=1024),
           NodeHints(N("n", 2), temporal_order=0, layout_rank=0, magnitude=1))), True, False,
           detail="2**53+1 and INT64 max in numeric columns: a JavaScript Number cannot hold them")

    g = ISONGraph()
    g.add_node("n", 1)
    g.add_node("n", "s")
    g.add_edge("r", ("n", 1), ("n", "s"))
    TL = g.to_isonl().encode("utf-8")
    ok_row("ok/isonl-profile-carried", TL, payload_for(TL, profile="isonl-v1", nodes=(NodeHints(N("n", 1), role="info"),)), True, False, profile="isonl-v1",
           detail="isonl-v1 is carried; IGS/1's ison-v1-only rule belongs to the adapter")

    # (c) input-level rejections: codes come from the EXISTING verification path (oracle), or from the spec for IGDC's own gates
    def oracle_reject(target: bytes, binding_text: str, payload_text: str, limits=Limits()):
        try:
            verify_and_admit(payload_text.encode("utf-8"), ExtensionBinding.from_ison(binding_text), target, limits=limits, baselines=BASES)
        except (IGXError, IGDMError) as e:
            return e.code, e.step
        raise AssertionError("input was expected to be rejected")

    for src, new, limits, detail in [("reject/target-sha-mismatch", "reject/target-sha-mismatch", Limits(), None),
                                     ("reject/twin-ids", "reject/payload-twin-ids", Limits(), None),
                                     ("reject/oversized-payload", "reject/payload-oversize", Limits(max_payload_bytes=16), "limits:max_payload_bytes=16"),
                                     ("reject/payload-digest-mismatch", "reject/payload-digest-mismatch", Limits(), None),
                                     ("reject/unresolved-node", "reject/unresolved-node", Limits(), None)]:
        m = manifest[src]
        graph, b, p = ((IGDM / "graphs" / m["target"]).read_bytes(), (IGDM / "bindings" / m["binding"]).read_text(encoding="utf-8"),
                       (IGDM / "payloads" / m["payload"]).read_text(encoding="utf-8"))
        code, step = oracle_reject(graph, b, p, limits)
        s = slug(new)
        row(new, "consume", target=put("targets", f"{sha(graph)[:16]}.ison", graph), binding=put("bindings", f"{s}.igx.ison", b.encode()),
            payload=put("payloads", f"{s}.igdm.ison", p.encode()), expect="reject", code=code, step=step, detail=detail)
    other = ISONGraph()
    other.add_node("order", 99)
    TO = other.to_ison().encode("utf-8")
    base_target = (IGDM / "graphs/synthetic/directed.ison").read_bytes()
    base_payload = (IGDM / "payloads" / manifest["ok/node-hints-full-row"]["payload"]).read_text(encoding="utf-8")
    foreign = bind_for(TO, base_payload)                       # a binding that names a different artifact than the payload and the supplied bytes
    code, step = oracle_reject(base_target, foreign, base_payload)
    row("reject/binding-artifact-mismatch", "consume", target=put("targets", f"{sha(base_target)[:16]}.ison", base_target),
        binding=put("bindings", "reject--binding-artifact-mismatch.igx.ison", foreign.encode()),
        payload=put("payloads", "reject--binding-artifact-mismatch.igdm.ison", base_payload.encode()), expect="reject", code=code, step=step)
    lim = manifest["ok/limited-runtime-skips-resolution"]
    graph = (IGDM / "graphs" / lim["target"]).read_bytes()
    row("reject/resolution-limited", "consume", target=put("targets", f"{sha(graph)[:16]}.ison", graph),
        binding=put("bindings", "reject--resolution-limited.igx.ison", (IGDM / "bindings" / lim["binding"]).read_bytes()),
        payload=put("payloads", "reject--resolution-limited.igdm.ison", (IGDM / "payloads" / lim["payload"]).read_bytes()),
        expect="reject", code="RESOLUTION_REQUIRED", step="P0", detail="baselines:all")

    # (d) hint-document rejections: corrupt the expected file of ok/node-hints-full-row THROUGH ison_parser (or as text/bytes where the fault is textual)
    base = ok_hints["ok/node-hints-full-row"]
    assert rows[0]["id"] == "ok/node-hints-full-row"
    inputs = {k: rows[0][k] for k in ("target", "binding", "payload")}

    def edit(fn) -> str:
        d = loads(base)
        fn(d)
        return dumps_canonical(d)

    def blk(d, name):
        return next(b for b in d.blocks if b.name == name)

    def set_first(table, col, value):
        def f(d):
            blk(d, table).rows[0][col] = value
        return f

    def set_many(*fns):
        def f(d):
            for fn in fns:
                fn(d)
        return f

    def dup_col(name):
        def f(d):
            b = blk(d, name)
            b.fields.append(b.fields[0])
        return f

    def with_node(**kw):
        def f(d):
            n = blk(d, "nodes")
            n.rows.append({**{c: None for c in n.fields}, **kw})
        return f

    def drop_block(name):
        def f(d):
            d.blocks[:] = [b for b in d.blocks if b.name != name]
        return f

    def dup_block(name):
        def f(d):
            d.blocks.append(blk(d, name))
        return f

    def dup_row(table, **over):
        def f(d):
            blk(d, table).rows.append(dict(blk(d, table).rows[0], **over))
        return f

    def add_member(**kw):
        def f(d):
            blk(d, "members").rows.append(kw)
        return f

    def swap_edge(d):
        e = blk(d, "edges").rows[0]
        e["source_id"], e["target_id"] = e["target_id"], e["source_id"]
        blk(d, "igdc").rows[0]["target_directed"] = "false"

    def make_cycle(d):
        for r in blk(d, "groups").rows:
            if r["group_id"] == "region":
                r["parent_group_id"] = "cluster"

    def set_group(gid, col, value):
        def f(d):
            for r in blk(d, "groups").rows:
                if r["group_id"] == gid:
                    r[col] = value
        return f

    def add_unexpected_column(d):
        m = blk(d, "members")
        m.fields.append("extra")
        for r in m.rows:
            r["extra"] = None

    MALFORMED, INVALID = "MALFORMED_CONSUMPTION", "INVALID_ADDRESS"
    text_cases = [   # id, code, step, document (str or bytes), detail
        ("reject/igdc-noncanonical", MALFORMED, "C0", base.replace("\n\n", "\n\n\n", 1), None),
        ("reject/igdc-cr", MALFORMED, "C0", base.replace("\n", "\r\n"), None),
        ("reject/igdc-bom", MALFORMED, "C0", "﻿" + base, None),
        ("reject/igdc-not-utf8", MALFORMED, "C0", b"\xff\xfe" + base.encode(), None),
        ("reject/igdc-oversize", "DATAMATICS_LIMIT_EXCEEDED", "C0", base, "limits:max_payload_bytes=64"),
        ("reject/igdc-row-budget", "DATAMATICS_LIMIT_EXCEEDED", "C1", base, "limits:max_rows_per_table=1"),
        ("reject/igdc-unexpected-block", MALFORMED, "C1", edit(lambda d: d.blocks.append(Block("table", "extra", ["a"], []))), None),
        ("reject/igdc-missing-block", MALFORMED, "C1", edit(drop_block("members")), None),
        ("reject/igdc-duplicate-block", MALFORMED, "C1", edit(dup_block("members")), None),
        ("reject/igdc-meta-extra-row", MALFORMED, "C1", edit(dup_row("igdc")), None),
        ("reject/igdc-summary-row", MALFORMED, "C1", base + "\n---\nrows 2", None),
        ("reject/igdc-typed-column", MALFORMED, "C1", base.replace("group_id", "group_id:int", 1), None),
        ("reject/igdc-computed-column", MALFORMED, "C1", base.replace("group_id", "group_id:computed", 1), None),
        ("reject/igdc-reference-cell", MALFORMED, "C1", base.replace("i:1 order", ":order:1 order", 1), None),
        *[(f"reject/igdc-duplicate-column-{n}", MALFORMED, "C1", edit(dup_col(n)), None) for n in ("igdc", "layout", "nodes", "edges", "groups", "members")],
        ("reject/igdc-unexpected-column", MALFORMED, "C1", edit(add_unexpected_column), None),
        ("reject/igdc-missing-column", MALFORMED, "C1", edit(lambda d: blk(d, "members").fields.remove("node_type")), None),
        ("reject/igdc-bare-boolean", MALFORMED, "C1", edit(with_node(node_type="order", node_id="i:9", selectable=True)), None),
        ("reject/igdc-directed-bare-boolean", MALFORMED, "C1", edit(set_first("igdc", "target_directed", True)), None),
        ("reject/igdc-closed-outside-vocab", MALFORMED, "C1", edit(set_first("nodes", "emphasis", "huge")), None),
        ("reject/igdc-x-in-closed-column", MALFORMED, "C1", edit(set_first("nodes", "role", "x-risk")), None),
        ("reject/igdc-x-token-malformed", MALFORMED, "C1", edit(set_first("nodes", "role_x", "risk")), None),
        ("reject/igdc-closed-and-x-both", MALFORMED, "C1", edit(set_many(set_first("nodes", "role", "active"), set_first("nodes", "role_x", "x-risk"))), None),
        ("reject/igdc-wrong-spec", MALFORMED, "C1", edit(set_first("igdc", "consumption_spec", "IGDC/2")), None),
        ("reject/igdc-wrong-address-scheme", MALFORMED, "C1", edit(set_first("igdc", "address_scheme", "igs-addr/2")), None),
        ("reject/igdc-bad-hex", MALFORMED, "C1", edit(set_first("igdc", "igdm_payload_sha256", "xyz")), None),
        ("reject/igdc-bad-profile", MALFORMED, "C1", edit(set_first("igdc", "target_serialization_profile", "ison-v9")), None),
        ("reject/igdc-lod-out-of-range", MALFORMED, "C1", edit(set_first("nodes", "lod_min", 5000)), None),
        ("reject/igdc-magnitude-out-of-range", MALFORMED, "C1", edit(set_first("nodes", "magnitude", 1.5)), None),
        ("reject/igdc-untagged-id", INVALID, "C2", edit(set_first("nodes", "node_id", "1")), None),
        ("reject/igdc-id-leading-zero", INVALID, "C2", edit(set_first("nodes", "node_id", "i:007")), None),
        ("reject/igdc-id-minus-zero", INVALID, "C2", edit(set_first("nodes", "node_id", "i:-0")), None),
        ("reject/igdc-id-out-of-int64", INVALID, "C2", edit(set_first("nodes", "node_id", "i:9223372036854775808")), None),
        ("reject/igdc-unknown-tag", INVALID, "C2", edit(set_first("nodes", "node_id", "x:1")), None),
        ("reject/igdc-id-empty-int", INVALID, "C2", edit(set_first("nodes", "node_id", "i:")), None),
        ("reject/igdc-bad-node-type", INVALID, "C2", edit(set_first("nodes", "node_type", "a b")), None),
        ("reject/igdc-undirected-noncanonical", INVALID, "C2", edit(swap_edge), None),
        ("reject/igdc-simple-ordinal-1", INVALID, "C2", edit(set_first("edges", "ordinal", "1")), None),
        ("reject/igdc-ordinal-leading-zero", INVALID, "C2", edit(set_many(set_first("igdc", "target_multigraph", "true"), set_first("edges", "ordinal", "01"))), None),
        ("reject/igdc-duplicate-node-row", INVALID, "C2", edit(dup_row("nodes", label="x")), None),
        ("reject/igdc-duplicate-edge-row", INVALID, "C2", edit(dup_row("edges", label="x")), None),
        ("reject/igdc-duplicate-member", INVALID, "C2", edit(dup_row("members")), None),
        ("reject/igdc-duplicate-group", INVALID, "C2", edit(dup_row("groups", label="x")), None),
        ("reject/igdc-twin-ids", "TWIN_IDS", "C2", edit(add_member(group_id="region", node_type="order", node_id="s:1")), None),
        ("reject/igdc-unknown-parent", "UNRESOLVED_REFERENCE", "C3", edit(set_group("cluster", "parent_group_id", "nope")), None),
        ("reject/igdc-member-unknown-group", "UNRESOLVED_REFERENCE", "C3", edit(add_member(group_id="nope", node_type="order", node_id="i:1")), None),
        ("reject/igdc-group-cycle", "GROUP_CYCLE", "C3", edit(make_cycle), None),
        ("reject/igdc-group-depth", "DATAMATICS_LIMIT_EXCEEDED", "C3", base, "limits:max_group_depth=0"),
    ]
    for id_, code, step, doc, detail in text_cases:
        data = doc if isinstance(doc, bytes) else doc.encode("utf-8")
        row(id_, "verify", hints=put("hints", f"{slug(id_)}.igdc.ison", data), expect="reject", code=code, step=step, detail=detail)
    row("ok/igdc-wellformed-not-verified", "verify",
        hints=put("hints", "ok--igdc-wellformed-not-verified.igdc.ison", edit(lambda d: blk(d, "nodes").rows[0].update(label="changed")).encode()),
        expect="ok", detail="C0-C3 pass; only C4 or a trusted receipt ties a document to a payload")

    # (e) C4: well-formed documents that are not the derivation of the supplied inputs
    def c4(id_, fn, detail=None):
        row(id_, "derivation", hints=put("hints", f"{slug(id_)}.igdc.ison", edit(fn).encode()), expect="reject", code="DERIVATION_MISMATCH", step="C4",
            detail=detail, **inputs)

    c4("reject/igdc-derivation-mismatch", lambda d: blk(d, "nodes").rows[0].update(label="Order #999"))
    c4("reject/igdc-payload-digest-mismatch", set_first("igdc", "igdm_payload_sha256", "0" * 63 + "f"))
    c4("reject/igdc-directed-fact-wrong", set_first("igdc", "target_directed", "false"), "the target is directed; the document claims otherwise")
    c4("reject/igdc-multigraph-fact-wrong", set_first("igdc", "target_multigraph", "true"), "the target is a simple graph")
    c4("reject/igdc-row-dropped", lambda d: blk(d, "nodes").rows.pop())
    c4("reject/igdc-row-added", with_node(node_type="order", node_id="i:99", role="info"), "a well-formed row for a node the payload does not mention")

    # (f) manifest, README, SHA256SUMS
    cols = ["id", "op", "target", "binding", "payload", "hints", "expect", "code", "step", "detail"]
    for r in rows:
        assert set(r) == set(cols)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate vector id"
    text = dumps_canonical(Document(blocks=[Block("meta", "corpus", ["consumption_spec", "version"], [{"consumption_spec": "IGDC/1", "version": 1}]),
                                            Block("table", "vectors", cols, rows)]))
    (out / "manifest.ison").write_bytes(text.encode("utf-8"))
    (out / "README.md").write_bytes(CONSUMPTION_README.encode("utf-8"))
    files = sorted(str(p.relative_to(out)).replace("\\", "/") for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (out / "SHA256SUMS").write_bytes("".join(f"{sha((out / n).read_bytes())}  {n}\n" for n in files).encode("utf-8"))
    counts: dict[str, int] = {}
    for r in rows:
        k = f"{r['op']}:{r['expect']}"
        counts[k] = counts.get(k, 0) + 1
    return counts


CONSUMPTION_README = """# vectors/igdc1 — IGDC/1 consumption vectors (26 §5)

Every row of `manifest.ison` is normative. `op` selects what a runner does, never the presence of a column:
`consume` (inputs -> expected hint file, or the stated error), `verify` (hint document -> C0-C3 result), `derivation` (hint document + inputs -> C4).
Expected hint files are written by the reference deriver in `scripts/make_vectors_igdc.py` (ison_parser only), not by `isongraph_ext.igdc`.
`SHA256SUMS` pins every file. Input-level rejections carry the code and step the EXISTING igx/igdm verification path raises (IGDC propagates them unchanged).
"""


def main(argv: list[str]) -> None:
    counts = write_set(ROOT / "vectors" / "igs-addr", TABLES, README)
    print("igs-addr", counts, "total", sum(counts.values()))
    if "--addr" not in argv:
        c = build_consumption(ROOT / "vectors" / "igdc1")
        print("igdc1", c, "total", sum(c.values()))


if __name__ == "__main__":
    main(sys.argv[1:])

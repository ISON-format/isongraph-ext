#!/usr/bin/env python3
"""Generate vectors/igpv1 (graphs, bindings, payloads, sources, manifest) from the public API plus deliberate mutations (18 §6).

Every row is asserted against the runtime before it is written: the manifest records observed behaviour.
Run from the repo root with the venv:  .venv/Scripts/python.exe scripts/make_vectors_igpv.py

A row's binding is derived from the payload text it ships with (bind_text), so a mutated payload is always bound by its
own digest and the vector reaches the step it names; only rows that test the binding itself pass an explicit binding.
Payloads that must bypass check() (duplicate digests, twins, dangling rows) are emitted through to_document().
"""

from __future__ import annotations

import dataclasses
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "isongraph-ext" / "src"))
sys.path.insert(0, str(ROOT / "isongraph-ext" / "tests"))

from conftest import RETIRED, all_baselines  # noqa: E402
from ison_graph import ISONGraph  # noqa: E402
from ison_graph.multigraph import MultiGraph  # noqa: E402
from ison_parser import Block, Document, dumps_canonical, loads  # noqa: E402

from isongraph_ext.igpv.bind import verify_and_admit  # noqa: E402
from isongraph_ext.igpv.errors import IGPVError  # noqa: E402
from isongraph_ext.igpv.lineage import Lineage  # noqa: E402
from isongraph_ext.igpv.payload import ProvenancePayload  # noqa: E402
from isongraph_ext.igpv.records import Artifact, Attribution, Derivation, EdgeAddress, GraphObject, Limits, Locator, NodeRef, Producer  # noqa: E402
from isongraph_ext.igx.bind import bind as igx_bind  # noqa: E402
from isongraph_ext.igx.binding import Capability, ExtensionBinding  # noqa: E402
from isongraph_ext.igx.errors import IGXError  # noqa: E402

VEC = ROOT / "vectors" / "igpv1"
B = all_baselines()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---- graphs (generator-made with the pinned Core; byte-exact) ------------------------------------------------

def _g(directed=True, nodes=(), edges=()) -> bytes:
    g = ISONGraph(directed=directed)
    for t, i in nodes:
        g.add_node(t, i)
    for rel, s, t in edges:
        g.add_edge(rel, s, t)
    return g.to_ison().encode("utf-8")


DIRECTED = _g(nodes=[("p", 1), ("p", "s1")], edges=[("knows", ("p", 1), ("p", "s1"))])
STRING_ONE = _g(nodes=[("p", "1")])
UNDIRECTED = _g(directed=False, nodes=[("p", 1), ("p", "s1")], edges=[("knows", ("p", "s1"), ("p", 1))])
_m = MultiGraph()
_m.add_node("p", 1)
_m.add_node("p", 2)
for _k in (0, 1, 10):
    _m.add_edge("r", ("p", 1), ("p", 2), key=_k)
MULTI = _m.to_ison().encode("utf-8")
ORIGIN = _g(nodes=[("p", 7), ("p", 8), ("p", 1), ("p", "s1")], edges=[("knows", ("p", 7), ("p", 8)), ("knows", ("p", 1), ("p", "s1"))])
ORIGIN2 = _g(nodes=[("p", 1), ("p", 9)])
DOC = b"# orders\n\nline two\nline three\n"
DOC_CRLF = b"# orders\r\n\r\nline two\r\nline three\r\n"
GRAPHS = {"synthetic/directed.ison": DIRECTED, "synthetic/string-one.ison": STRING_ONE, "synthetic/undirected.ison": UNDIRECTED,
          "synthetic/multi.ison": MULTI, "synthetic/origin.ison": ORIGIN, "synthetic/origin2.ison": ORIGIN2}
SOURCES = {sha(d): d for d in (DOC, DOC_CRLF, ORIGIN, ORIGIN2)}
D, S, U, X, O = ("synthetic/directed.ison", "synthetic/string-one.ison", "synthetic/undirected.ison", "synthetic/multi.ison", "synthetic/origin.ison")
OR, OR2, SD, SDC, TD = sha(ORIGIN), sha(ORIGIN2), sha(DOC), sha(DOC_CRLF), sha(DIRECTED)

# ---- payload building blocks --------------------------------------------------------------------------------

X0 = Producer("x0", "extractor", "betterify-ri-extractor", "2.3.0")
T0 = Producer("t0", "transformation", "isongraph-ext", "0.2.0", spec="IGDAG/1", policy_sha256="3" * 64)
SRC0 = Artifact("src0", SD, "document", len(DOC), media_type="text/markdown")
SRCC = Artifact("srcc", SDC, "document", len(DOC_CRLF), media_type="text/markdown")
G0 = Artifact("g0", OR, "isongraph", len(ORIGIN), serialization_profile="ison-v1")
G2 = Artifact("g2", OR2, "isongraph", len(ORIGIN2), serialization_profile="ison-v1")
GA = Artifact("ga", TD, "isongraph", len(DIRECTED), serialization_profile="ison-v1")
N1 = GraphObject("n1", "node", node=NodeRef("p", 1))
N2 = GraphObject("n2", "node", node=NodeRef("p", "s1"))
G = GraphObject("G", "graph")
E1 = GraphObject("e1", "edge", edge=EdgeAddress(NodeRef("p", 1), "knows", NodeRef("p", "s1")))
O1 = GraphObject("o1", "node", graph="g0", node=NodeRef("p", 1))
O7 = GraphObject("o7", "node", graph="g0", node=NodeRef("p", 7))
O8 = GraphObject("o8", "node", graph="g0", node=NodeRef("p", 8))
OE = GraphObject("oe", "edge", graph="g0", edge=EdgeAddress(NodeRef("p", 7), "knows", NodeRef("p", 8)))
A0 = Attribution("a0", "n1", "src0", "x0")


def P(target: bytes = DIRECTED, *, artifacts=(SRC0,), producers=(X0,), objects=(N1,), attributions=(A0,), derivations=(),
      profile="ison-v1") -> ProvenancePayload:
    return ProvenancePayload(sha(target), profile, tuple(artifacts), tuple(producers), tuple(objects), tuple(attributions), tuple(derivations))


def raw(p: ProvenancePayload) -> str:
    """Canonical text WITHOUT check(): for payloads that are deliberately malformed at P1."""
    return dumps_canonical(p.to_document())


def der(*rows: tuple[str, str, str, str]) -> tuple[Derivation, ...]:
    return tuple(Derivation(i, d, o, "t0", k) for i, d, o, k in rows)


def bind_text(text: str, target: bytes = DIRECTED, requirement="REQUIRED", claim="artifact") -> str:
    """The binding that ships with a payload text: carries sha256 of exactly those bytes."""
    return igx_bind(target, serialization_profile="ison-v1", producer_port="python", identity_claim=claim,
                    capabilities=(Capability("igpv", "^1", requirement, sha(text.encode("utf-8"))),)).to_ison()


def mut(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def add_block(text: str, block: Block) -> str:
    doc = loads(text)
    doc.blocks.append(block)
    return dumps_canonical(doc)


def swap_rows(text: str, table: str) -> str:
    """Parse, swap the first two rows of `table`, re-emit WITHOUT re-sorting: a deliberately non-canonical row order."""
    doc = loads(text)
    b = next(b for b in doc.blocks if (b.kind, b.name) == ("table", table))
    assert len(b.rows) >= 2, table
    b.rows[0], b.rows[1] = b.rows[1], b.rows[0]
    out = _emit_in_order(doc)
    assert out != text, table
    return out


def _emit_in_order(doc: Document) -> str:
    """dumps_canonical re-sorts rows, so a non-canonical row order has to be written by hand (same layout otherwise)."""
    from ison_parser import Serializer
    out = []
    for b in sorted(doc.blocks, key=lambda b: f"{b.kind}.{b.name}"):
        fields = Serializer._sort_fields_canonical(b.fields)
        lines = [f"{b.kind}.{b.name}", " ".join(fields)]
        for row in b.rows:
            lines.append(" ".join(Serializer._value_to_ison(row.get(f)) for f in fields).rstrip())
        out.append("\n".join(lines))
    return "\n\n".join(out)


base = P()
bt = base.to_ison()
base_b = ExtensionBinding.from_ison(bind_text(bt))
no_row_b = igx_bind(DIRECTED, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact").to_ison()
null_digest_b = igx_bind(DIRECTED, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact",
                         capabilities=(Capability("igpv", "^1", "OPTIONAL", None),)).to_ison()
excl_b = igx_bind(DIRECTED, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact",
                  capabilities=(Capability("igpv", "=2.0.0", "OPTIONAL", base.digest),)).to_ison()
bad_corpus_b = dataclasses.replace(base_b, core_vector_corpus_digest="c" * 64).to_ison()
retired_b = dataclasses.replace(base_b, core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256).to_ison()

loc_b = P(attributions=(Attribution("a0", "n1", "src0", "x0", Locator("bytes/1", 2, 8)),)).to_ison()
loc_l = P(attributions=(Attribution("a0", "n1", "src0", "x0", Locator("lines/1", 2, 4)),)).to_ison()
loc_lc = P(artifacts=(SRCC,), attributions=(Attribution("a0", "n1", "srcc", "x0", Locator("lines/1", 2, 4)),)).to_ison()
loc_x = P(attributions=(Attribution("a0", "n1", "src0", "x0", Locator("x-pdf-page/1", text="7")),)).to_ison()
multi_src = P(artifacts=(SRC0, SRCC), producers=(X0, T0),
              attributions=(A0, Attribution("a1", "n1", "srcc", "x0"), Attribution("a2", "n1", "src0", "t0"))).to_ison()
str_one = P(STRING_ONE, objects=(GraphObject("n1", "node", node=NodeRef("p", "1")),)).to_ison()
edge_p = P(objects=(E1,), attributions=(Attribution("a0", "e1", "src0", "x0"),)).to_ison()
multi_p = P(MULTI, objects=tuple(GraphObject(f"e{k}", "edge", edge=EdgeAddress(NodeRef("p", 1), "r", NodeRef("p", 2), str(k))) for k in (0, 1, 10)),
            attributions=tuple(Attribution(f"a{k}", f"e{k}", "src0", "x0") for k in (0, 1, 10))).to_ison()
undir_p = P(UNDIRECTED, objects=(E1,), attributions=(Attribution("a0", "e1", "src0", "x0"),)).to_ison()
graph_p = P(objects=(G,), attributions=(Attribution("a0", "G", "src0", "x0"),)).to_ison()
ident = P(artifacts=(G0,), producers=(T0,), objects=(N1, O1), attributions=(), derivations=der(("d0", "n1", "o1", "identity")))
ident_p = ident.to_ison()
collapse = P(artifacts=(G0,), producers=(T0,), objects=(N1, O7, O8), attributions=(),
             derivations=der(("d0", "n1", "o7", "collapse"), ("d1", "n1", "o8", "collapse")))
collapse_p = collapse.to_ison()
rewrite_p = P(artifacts=(G0,), producers=(T0,), objects=(E1, OE), attributions=(), derivations=der(("d0", "e1", "oe", "rewrite"))).to_ison()
kind_mismatch_p = P(artifacts=(G0,), producers=(T0,), objects=(N1, OE), attributions=(), derivations=der(("d0", "n1", "oe", "rewrite"))).to_ison()
# built programmatically: moving o7 from g0 to the target changes its row position, so a text mutation would be non-canonical
self_deriv_p = P(artifacts=(G0,), producers=(T0,), objects=(N1, GraphObject("o7", "node", node=NodeRef("p", 7)), O8), attributions=(),
                 derivations=der(("d0", "n1", "o7", "collapse"), ("d1", "n1", "o8", "collapse"))).to_ison()
empty_p = P(artifacts=(), producers=(), objects=(), attributions=()).to_ison()
dup_digest_p = raw(P(artifacts=(SRC0, Artifact("src1", SD, "document", len(DOC))), attributions=(A0, Attribution("a1", "n1", "src1", "x0"))))
twin_p = raw(P(objects=(N1, GraphObject("n9", "node", node=NodeRef("p", "1"))), attributions=(A0, Attribution("a1", "n9", "src0", "x0"))))
dangling_p = raw(P(artifacts=(SRC0, SRCC)))
two_faults_p = mut(P(objects=(N1, GraphObject("n9", "node", node=NodeRef("p", 9))), attributions=(A0, Attribution("a1", "n9", "src0", "x0"))).to_ison(),
                   f"IGPV/1 {TD}", f"IGPV/1 {'e' * 64}")
isonl_p = P(profile="isonl-v1").to_ison()
other_target_p = P(ORIGIN).to_ison()

# lineage: DIRECTED.p1 <- ORIGIN.{p7,p8} (collapse), ORIGIN.p7 <- ORIGIN2.p9 (rewrite), ORIGIN2 has no payload
A_p = collapse_p
O_p = P(ORIGIN, artifacts=(G2, SRC0), producers=(T0, X0),
        objects=(GraphObject("n7", "node", node=NodeRef("p", 7)), GraphObject("n8", "node", node=NodeRef("p", 8)),
                 GraphObject("o9", "node", graph="g2", node=NodeRef("p", 9))),
        attributions=(Attribution("a0", "n8", "src0", "x0"),), derivations=der(("d0", "n7", "o9", "rewrite"))).to_ison()
A_one = P(artifacts=(G0,), producers=(T0,), objects=(N1, O7), attributions=(), derivations=der(("d0", "n1", "o7", "rewrite"))).to_ison()
O_cycle = P(ORIGIN, artifacts=(GA,), producers=(T0,), objects=(GraphObject("n7", "node", node=NodeRef("p", 7)), GraphObject("oa", "node", graph="ga", node=NodeRef("p", 1))),
            attributions=(), derivations=der(("d0", "n7", "oa", "rewrite"))).to_ison()
O_revisit = P(ORIGIN, artifacts=(GA,), producers=(T0,), objects=(GraphObject("n7", "node", node=NodeRef("p", 7)), GraphObject("oa", "node", graph="ga", node=NodeRef("p", "s1"))),
              attributions=(), derivations=der(("d0", "n7", "oa", "rewrite"))).to_ison()
A_two = P(artifacts=(G0,), producers=(T0,), objects=(N2, O7), attributions=(), derivations=der(("d0", "n2", "o7", "rewrite"))).to_ison()

# id, target, binding (None = bind_text(payload) over that target), payload text or [texts], sources, expect, step, detail
VECTORS = [
    ("ok/attribution-whole-artifact", D, None, bt, "none", "verify_ok+admit_ok", None, None),
    ("ok/attribution-bytes-locator-unverified", D, None, loc_b, "none", "verify_ok+admit_ok", None, "locator:a0=UNVERIFIED"),
    ("ok/attribution-bytes-locator-verified", D, None, loc_b, SD, "verify_ok+admit_ok", None, "locator:a0=VERIFIED"),
    ("ok/attribution-lines-locator-verified", D, None, loc_lc, SDC, "verify_ok+admit_ok", None, "locator:a0=VERIFIED;CRLF document, CR stays in the line"),
    ("ok/attribution-x-locator-stays-unverified", D, None, loc_x, SD, "verify_ok+admit_ok", None, "locator:a0=UNVERIFIED"),
    ("ok/multiple-sources-one-object", D, None, multi_src, "none", "verify_ok+admit_ok", None, None),
    ("ok/typed-ids-distinct-across-graphs", S, None, str_one, "none", "verify_ok+admit_ok", None, 'STRING "1" resolves where the graph holds "1"; reject/unresolved-node is the INT64 twin case'),
    ("ok/edge-int-and-string-endpoints", D, None, edge_p, "none", "verify_ok+admit_ok", None, None),
    ("ok/multigraph-ordinals", X, None, multi_p, "none", "verify_ok+admit_ok", None, None),
    ("ok/undirected-logical-edge", U, None, undir_p, "none", "verify_ok+admit_ok", None, "canonical endpoint order (p 1, p s1)"),
    ("ok/graph-scope-attribution", D, None, graph_p, "none", "verify_ok+admit_ok", None, None),
    ("ok/derivation-identity", D, None, ident_p, OR, "verify_ok+admit_ok", None, "origin:g0=verified"),
    ("ok/derivation-collapse-many-to-one", D, None, collapse_p, OR, "verify_ok+admit_ok", None, "origin:g0=verified"),
    ("ok/derivation-rewrite-edge", D, None, rewrite_p, OR, "verify_ok+admit_ok", None, "origin:g0=verified"),
    ("ok/derivation-origin-unverified", D, None, collapse_p, "none", "verify_ok+admit_ok", None, "origin:g0=unverified"),
    ("ok/limited-runtime-skips-resolution", D, retired_b, bt, "none", "verify_ok+admit:STALE_BINDING", "A1", "resolution:skipped;retired baseline runtime not installed"),
    ("ok/optional-igpv-row", D, bind_text(bt, requirement="OPTIONAL"), bt, "none", "verify_ok+admit_ok", None, None),
    ("ok/reserialize-stable", D, None, collapse_p, "none", "verify_ok+admit_ok", None, "from_ison(to_ison(p)).to_ison() == bytes; digest == sha256(bytes)"),
    ("ok/empty-provenance", D, None, empty_p, "none", "verify_ok+admit_ok", None, "all five tables empty"),
    ("ok/origin-artifact-reached-via-objects-graph", D, None, collapse_p, "none", "verify_ok+admit_ok", None, "g0 referenced only through objects.graph"),
    ("ok/locator-lines-counting", D, None, loc_l, SD, "verify_ok+admit_ok", None, "locator:a0=VERIFIED;lines/1 [2,4] over 4 lines"),
    ("reject/not-bound", D, no_row_b, bt, "none", "reject:PROVENANCE_NOT_BOUND", "P0", None),
    ("reject/payload-digest-null", D, null_digest_b, bt, "none", "reject:PROVENANCE_NOT_BOUND", "P0", None),
    ("reject/version-range-excludes", D, excl_b, bt, "none", "reject:PROVENANCE_VERSION_UNSUPPORTED", "P0", None),
    ("reject/payload-digest-mismatch", D, base_b.to_ison(), loc_b, "none", "reject:PAYLOAD_DIGEST_MISMATCH", "P0", None),
    ("reject/binding-fails-igx", D, bad_corpus_b, bt, "none", "reject:CORPUS_DIGEST_MISMATCH", "P0", "IGXError raised from P0"),
    ("reject/oversized-payload", D, None, bt, "none", "reject:PROVENANCE_LIMIT_EXCEEDED", "P1", "limits:max_payload_bytes=16"),
    ("reject/oversized-target", D, None, bt, "none", "reject:PROVENANCE_LIMIT_EXCEEDED", "P1", "limits:max_graph_bytes=16"),
    ("reject/oversized-target-and-bad-binding", D, bad_corpus_b, bt, "none", "reject:PROVENANCE_LIMIT_EXCEEDED", "P1", "limits:max_graph_bytes=16;preflight wins"),
    ("reject/oversized-sources", D, None, loc_b, f"{SD}+{OR}", "reject:PROVENANCE_LIMIT_EXCEEDED", "P1", f"limits:max_sources_bytes={len(DOC)}"),
    ("reject/noncanonical-payload-text", D, None, bt + "\n", "none", "reject:MALFORMED_PROVENANCE", "P1", "trailing newline"),
    ("reject/rows-not-sorted", D, None, swap_rows(multi_src, "attributions"), "none", "reject:MALFORMED_PROVENANCE", "P1", "canonical_form"),
    ("reject/duplicate-artifact-digest", D, None, dup_digest_p, "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/node-id-outside-int64", D, None, mut(bt, "null node 1 p n1", "null node 9223372036854775808 p n1"), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/twin-ids-in-one-graph", D, None, twin_p, "none", "reject:MALFORMED_PROVENANCE", "P1", "ID-TWIN-INVARIANT"),
    ("reject/duplicate-block", D, None, add_block(bt, Block("meta", "igpv", ["provenance_spec"], [{"provenance_spec": "IGPV/1"}])), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/unexpected-block", D, None, add_block(bt, Block("meta", "extra", ["a"], [{"a": 1}])), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/semantic-digest-set", D, None, mut(bt, f"IGPV/1 {TD} null null", f"IGPV/1 {TD} {'a' * 64} sha256"), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/object-null-pattern", D, None, mut(bt, "null node 1 p n1 null null null null null null", "null node 1 p n1 null knows null null null null"), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/float-node-id", D, None, mut(bt, "null node 1 p n1", "null node 1.0 p n1"), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/ordinal-not-decimal", D, None, mut(edge_p, 'e1 "0" knows', 'e1 "01" knows'), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/identifier-unrepresentable", D, None, mut(bt, "null node 1 p n1", 'null node 1 "a:b" n1'), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/locator-past-size", D, None, mut(loc_b, "src0 a0 8 2 null bytes/1", f"src0 a0 {len(DOC) + 1} 2 null bytes/1"), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/locator-shape", D, None, mut(loc_l, "src0 a0 4 2 null lines/1", "src0 a0 4 2 t lines/1"), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/dangling-artifact-row", D, None, dangling_p, "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/extractor-with-policy", D, None, mut(bt, "betterify-ri-extractor extractor null x0", f"betterify-ri-extractor extractor {'3' * 64} x0"), "none", "reject:MALFORMED_PROVENANCE", "P1", None),
    ("reject/target-sha-mismatch", D, None, other_target_p, "none", "reject:TARGET_BINDING_MISMATCH", "P2", "payload names another graph"),
    ("reject/target-profile-mismatch", D, None, isonl_p, "none", "reject:TARGET_BINDING_MISMATCH", "P2", None),
    ("reject/unresolved-producer", D, None, mut(multi_src, "srcc a1 null null null null n1 x0", "srcc a1 null null null null n1 x9"), "none", "reject:UNRESOLVED_REFERENCE", "P3", "x0 stays reachable through a0, so P1 passes and P3 fires"),
    ("reject/origin-not-isongraph", D, None, mut(collapse_p, f"g0 {OR} isongraph null null ison-v1", f"g0 {OR} document null null null"), "none", "reject:UNRESOLVED_REFERENCE", "P3", None),
    ("reject/self-derivation", D, None, self_deriv_p, "none", "reject:INVALID_DERIVATION", "P3", "origin object sits in the target graph"),
    ("reject/origin-graph-is-target", D, None, mut(collapse_p, f"g0 {OR} isongraph", f"g0 {TD} isongraph"), "none", "reject:INVALID_DERIVATION", "P3", None),
    ("reject/derivation-kind-mismatch", D, None, kind_mismatch_p, "none", "reject:INVALID_DERIVATION", "P3", "node derived from an edge"),
    ("reject/identity-with-two-origins", D, None, collapse_p.replace("collapse", "identity"), "none", "reject:INVALID_DERIVATION", "P3", None),
    ("reject/identity-address-differs", D, None, mut(ident_p, "g0 node 1 p o1", "g0 node 7 p o1"), "none", "reject:INVALID_DERIVATION", "P3", None),
    ("reject/unresolved-node", D, None, mut(bt, "null node 1 p n1", 'null node "1" p n1'), "none", "reject:UNRESOLVED_OBJECT", "P4", 'STRING "1" where the graph holds INT64 1'),
    ("reject/unresolved-edge-ordinal", D, None, mut(edge_p, 'e1 "0" knows', 'e1 "1" knows'), "none", "reject:UNRESOLVED_OBJECT", "P4", None),
    ("reject/undirected-noncanonical-endpoints", U, None, mut(undir_p, 'e1 "0" knows 1 p s1 p', 'e1 "0" knows s1 p 1 p'), "none", "reject:UNRESOLVED_OBJECT", "P4", "endpoints not canonical"),
    ("reject/origin-object-missing", D, None, mut(collapse_p, "g0 node 8 p o8", "g0 node 80 p o8"), OR, "reject:UNRESOLVED_OBJECT", "P4", None),
    ("reject/origin-size-wrong", D, None, mut(collapse_p, f"ison-v1 {len(ORIGIN)} null", f"ison-v1 {len(ORIGIN) + 1} null"), OR, "reject:SOURCE_ARTIFACT_MISMATCH", "P4", "digest matches, declared size lies"),
    ("reject/document-size-wrong", D, None, mut(loc_b, f"text/markdown null null {len(DOC)} null", f"text/markdown null null {len(DOC) + 1} null"), SD, "reject:SOURCE_ARTIFACT_MISMATCH", "P5", None),
    ("reject/locator-lines-past-end", D, None, mut(loc_l, "src0 a0 4 2 null lines/1", "src0 a0 5 2 null lines/1"), SD, "reject:LOCATOR_INVALID", "P5", "end 5 <= size but > 4 lines"),
    ("reject/two-faults-first-wins", D, None, two_faults_p, "none", "reject:TARGET_BINDING_MISMATCH", "P2", "wrong target sha and unresolved node: P2 fires first"),
    ("lineage/chain-two-hops", "none", "none", [A_p, O_p], "none", "lineage_ok", None, "query:n1;origins:3;terminal:no_derivation_record"),
    ("lineage/cycle-detected", "none", "none", [A_one, O_cycle], "none", "lineage:DERIVATION_CYCLE", "L", "query:n1"),
    ("lineage/graph-revisited-different-object", "none", "none", [A_one, O_revisit], "none", "lineage_ok", None, "query:n1;origins:2;terminal:no_derivation_record"),
    ("lineage/ambiguous-target", "none", "none", [A_p, A_two], "none", "lineage:LINEAGE_AMBIGUOUS", "L", "query:n1"),
    ("lineage/depth-budget", "none", "none", [A_p, O_p], "none", "lineage:LINEAGE_BUDGET_EXCEEDED", "L", "query:n1;limits:max_lineage_depth=1"),
    ("lineage/payload-unavailable-terminal", "none", "none", [A_p], "none", "lineage_ok", None, "query:n1;origins:2;terminal:payload_unavailable"),
    ("lineage/no-derivation-record-terminal", "none", "none", [A_p, O_p], "none", "lineage_ok", None, "query:n1;origins:3;terminal:no_derivation_record"),
]


def _details(detail: str | None) -> dict[str, list[str]]:
    d: dict[str, list[str]] = {}
    for item in (detail or "").split(";"):
        if ":" in item:
            k, v = item.split(":", 1)
            d.setdefault(k.strip(), []).append(v.strip())
    return d


def check(id_, target_rel, binding_text, payload_texts, sources, expect, step, detail) -> None:
    d = _details(detail)
    limits = Limits(**{k: int(v) for item in d.get("limits", []) for k, v in [item.split("=")]})
    src = {} if sources == "none" else {name: SOURCES[name] for name in sources.split("+")}
    tokens = expect.split("+")
    if id_.startswith("lineage/"):
        payloads = [ProvenancePayload.from_ison(t) for t in payload_texts]
        obj = next(o for o in payloads[0].objects if o.object_id == d["query"][0])
        addr = obj.node if obj.kind == "node" else obj.edge if obj.kind == "edge" else None
        try:
            steps = Lineage(payloads, limits=limits).origins_of(payloads[0].target_artifact_sha256, addr)
        except IGPVError as e:
            assert (e.code, e.step) == (tokens[0][len("lineage:"):], step), (id_, e)
            return
        assert "lineage_ok" in tokens, id_
        for n in d.get("origins", []):
            assert sum(1 for s in steps if s.kind) == int(n), (id_, steps)
        for t in d.get("terminal", []):
            assert steps[-1].terminal == t, (id_, steps)
        return
    target = GRAPHS[target_rel]
    try:
        result, prov, decision = verify_and_admit(payload_texts.encode("utf-8"), ExtensionBinding.from_ison(binding_text), target,
                                                  sources=src, limits=limits, baselines=B)
    except (IGXError, IGPVError) as e:
        s = "P0" if isinstance(e, IGXError) else e.step
        assert tokens[0].startswith("reject:") and (e.code, s) == (tokens[0][len("reject:"):], step), (id_, e)
        return
    assert "verify_ok" in tokens, id_
    for item in d.get("locator", []):
        aid, posture = item.split("=")
        assert prov.locators[aid] == posture, (id_, prov.locators)
    for item in d.get("origin", []):
        aid, status = item.split("=")
        assert prov.origin_resolution[aid] == status, (id_, prov.origin_resolution)
    assert prov.object_resolution == ("skipped" if "skipped" in d.get("resolution", []) else "full"), id_
    for t in tokens:
        if t == "admit_ok":
            assert decision.admitted, (id_, decision)
        elif t.startswith("admit:"):
            assert (decision.admitted, decision.code, decision.step) == (False, t[len("admit:"):], step), (id_, decision)


def write_all() -> None:
    for sub in ("graphs/synthetic", "bindings", "payloads", "sources"):
        shutil.rmtree(VEC / sub, ignore_errors=True)
        (VEC / sub).mkdir(parents=True)
    for rel, data in GRAPHS.items():
        (VEC / "graphs" / rel).write_bytes(data)
    for name, data in SOURCES.items():
        (VEC / "sources" / name).write_bytes(data)
    rows = []
    for id_, target_rel, binding_text, payload_texts, sources, expect, step, detail in VECTORS:
        if binding_text is None:
            binding_text = bind_text(payload_texts, GRAPHS[target_rel])
        check(id_, target_rel, binding_text, payload_texts, sources, expect, step, detail)
        slug = id_.replace("/", "--")
        if isinstance(payload_texts, list):
            names = []
            for i, t in enumerate(payload_texts):
                name = f"{slug}-{i}.igpv.ison"
                (VEC / "payloads" / name).write_bytes(t.encode("utf-8"))
                names.append(name)
            payload_name, binding_name = "+".join(names), "none"
        else:
            payload_name, binding_name = f"{slug}.igpv.ison", f"{slug}.igx.ison"
            (VEC / "payloads" / payload_name).write_bytes(payload_texts.encode("utf-8"))
            (VEC / "bindings" / binding_name).write_bytes(binding_text.encode("utf-8"))
        rows.append({"id": id_, "target": target_rel, "binding": binding_name, "payload": payload_name, "sources": sources,
                     "expect": expect, "step": step, "detail": detail})
    doc = Document(blocks=[Block("meta", "corpus", ["provenance_spec", "version"], [{"provenance_spec": "IGPV/1", "version": 1}]),
                           Block("table", "vectors", ["id", "target", "binding", "payload", "sources", "expect", "step", "detail"], rows)])
    (VEC / "manifest.ison").write_bytes((dumps_canonical(doc) + "\n").encode("utf-8"))
    print(f"wrote {len(rows)} vectors")


if __name__ == "__main__":
    write_all()

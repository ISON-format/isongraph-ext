#!/usr/bin/env python3
"""Generate vectors/igdm1 from the public API plus deliberate mutations (19 §5). Every row is asserted before writing.
Run from the repo root:  .venv/Scripts/python.exe scripts/make_vectors_igdm.py

A row's binding is derived from the payload text it ships with (bind_text) unless the row tests the binding itself;
payloads that must bypass check() are emitted through to_document() (raw)."""

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
from ison_parser import Block, Document, dumps_canonical  # noqa: E402

from isongraph_ext.igdm.bind import verify_and_admit  # noqa: E402
from isongraph_ext.igdm.errors import IGDMError  # noqa: E402
from isongraph_ext.igdm.payload import DatamaticsPayload  # noqa: E402
from isongraph_ext.igdm.records import EdgeHints, Group, LayoutHints, Limits, Member, NodeHints  # noqa: E402
from isongraph_ext.igpv.payload import ProvenancePayload  # noqa: E402
from isongraph_ext.igpv.records import Artifact, Attribution, EdgeAddress, GraphObject, NodeRef, Producer  # noqa: E402
from isongraph_ext.igx.bind import bind as igx_bind  # noqa: E402
from isongraph_ext.igx.binding import Capability, ExtensionBinding  # noqa: E402
from isongraph_ext.igx.errors import IGXError  # noqa: E402

VEC = ROOT / "vectors" / "igdm1"
B = all_baselines()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _g(directed=True, nodes=(), edges=()) -> bytes:
    g = ISONGraph(directed=directed)
    for t, i in nodes:
        g.add_node(t, i)
    for rel, s, t in edges:
        g.add_edge(rel, s, t)
    return g.to_ison().encode("utf-8")


DIRECTED = _g(nodes=[("order", 1), ("order", "s1"), ("order", 2)], edges=[("knows", ("order", 1), ("order", "s1"))])
UNDIRECTED = _g(directed=False, nodes=[("order", 1), ("order", "s1")], edges=[("knows", ("order", "s1"), ("order", 1))])
_m = MultiGraph()
_m.add_node("order", 1)
_m.add_node("order", 2)
for _k in (0, 10):
    _m.add_edge("r", ("order", 1), ("order", 2), key=_k)
MULTI = _m.to_ison().encode("utf-8")
GRAPHS = {"synthetic/directed.ison": DIRECTED, "synthetic/undirected.ison": UNDIRECTED, "synthetic/multi.ison": MULTI}
D, U, X = "synthetic/directed.ison", "synthetic/undirected.ison", "synthetic/multi.ison"
TD = sha(DIRECTED)
N1, S1, N2 = NodeRef("order", 1), NodeRef("order", "s1"), NodeRef("order", 2)
E1 = EdgeAddress(N1, "knows", S1)
REGION = Group("region", "hull", label="Region A", role="neutral", collapsed=False, visibility="visible", lod_min=0)
CLUSTER = Group("cluster", "collapse", parent_group_id="region", label="Cluster", role="emphasis-low", collapsed=True, visibility="visible", lod_min=1)
NODE1 = NodeHints(N1, magnitude=0.8, role="active", emphasis="high", label="Order #1", lod_min=0, selectable=True, expandable=True,
                  shape_role="document", temporal_state="changed", temporal_order=3, layout_rank=0, layout_anchor=True,
                  a11y_text="Order 1 (active)", visibility="visible")
NODES1 = NodeHints(S1, magnitude=0.1, role="inactive", emphasis="medium", badge="3", ring="warning", lod_min=2, shape_role="circle",
                   visibility="collapsed", a11y_role="warning")


def P(target: bytes = DIRECTED, **kw) -> DatamaticsPayload:
    profile = kw.pop("profile", "ison-v1")
    base = dict(layout=LayoutHints("layered", "LR", "stable"), nodes=(NODE1, NODES1),
                edges=(EdgeHints(E1, role="neutral", pattern_role="dashed", emphasis="low", direction_display="forward", lod_min=1, visibility="visible"),),
                groups=(REGION, CLUSTER), members=(Member("cluster", N1), Member("region", N1), Member("region", S1)))
    base.update(kw)
    return DatamaticsPayload(sha(target), profile, **base)


def raw(p: DatamaticsPayload) -> str:
    """Canonical text WITHOUT check(): for payloads that are deliberately malformed at D1."""
    return dumps_canonical(p.to_document())


def bind_text(text: str, target: bytes = DIRECTED, requirement="REQUIRED", extra=()) -> str:
    return igx_bind(target, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact",
                    capabilities=tuple(extra) + (Capability("igdm", "^1", requirement, sha(text.encode("utf-8"))),)).to_ison()


def mut(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def swap_wire_rows(text: str, first: str, second: str) -> str:
    """Swap two adjacent data lines of the canonical text: an explicit, non-canonical row order on the wire."""
    return mut(text, f"{first}\n{second}", f"{second}\n{first}")


base = P()
bt = base.to_ison()
base_b = ExtensionBinding.from_ison(bind_text(bt))
bad_corpus_b = dataclasses.replace(base_b, core_vector_corpus_digest="c" * 64).to_ison()
retired_b = dataclasses.replace(base_b, core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256).to_ison()
no_row_b = igx_bind(DIRECTED, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact").to_ison()
excl_b = igx_bind(DIRECTED, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact",
                  capabilities=(Capability("igdm", "=2.0.0", "OPTIONAL", base.digest),)).to_ison()
edge_only = P(nodes=(), groups=(), members=()).to_ison()
multi_p = P(MULTI, nodes=(), groups=(), members=(), edges=tuple(EdgeHints(EdgeAddress(N1, "r", N2, k), role="info") for k in ("0", "10"))).to_ison()
undir_p = P(UNDIRECTED, nodes=(), groups=(), members=(), edges=(EdgeHints(E1, role="info"),)).to_ison()
empty_hull = P(groups=(REGION, CLUSTER, Group("outer", "hull"), Group("inner", "hull", parent_group_id="outer")),
               members=base.members + (Member("inner", S1),)).to_ison()
hier = P(groups=(Group("h1", "hierarchy"), Group("h2", "hierarchy", parent_group_id="h1")), members=(Member("h1", N1), Member("h2", N1))).to_ison()
xroles = P(nodes=(NodeHints(N1, role="x-betterify-risk"), NodeHints(S1, role="warning")), edges=(EdgeHints(E1, pattern_role="x-wavy"),)).to_ison()
layout_only = P(nodes=(), edges=(), groups=(), members=()).to_ison()
empty_dm = P(layout=LayoutHints(), nodes=(), edges=(), groups=(), members=()).to_ison()
igpv_payload = ProvenancePayload(TD, "ison-v1", (Artifact("src0", "b1" * 32, "document", 10),), (Producer("x0", "extractor", "ext", "1.0.0"),),
                                 (GraphObject("G", "graph"),), (Attribution("a0", "G", "src0", "x0"),), ())
both_b = bind_text(bt, extra=(Capability("igpv", "^1", "REQUIRED", igpv_payload.digest),))
chain = tuple(Group(f"g{i}", "hull", parent_group_id=(f"g{i - 1}" if i else None)) for i in range(4))

# id, target, binding (None = bind_text(payload) over that target), payload text, expect, step, detail
VECTORS = [
    ("ok/node-hints-full-row", D, None, bt, "verify_ok+admit_ok", None, None),
    ("ok/edge-hints", D, None, edge_only, "verify_ok+admit_ok", None, None),
    ("ok/multigraph-edge-ordinal", X, None, multi_p, "verify_ok+admit_ok", None, None),
    ("ok/undirected-edge-canonical", U, None, undir_p, "verify_ok+admit_ok", None, "canonical endpoint order"),
    ("ok/groups-nested-hull-and-collapse", D, None, bt, "verify_ok+admit_ok", None, None),
    ("ok/empty-hull-group", D, None, empty_hull, "verify_ok+admit_ok", None, "outer has no members but a child with members"),
    ("ok/hierarchy-chain", D, None, hier, "verify_ok+admit_ok", None, None),
    ("ok/x-roles-preserved", D, None, xroles, "verify_ok+admit_ok", None, "roles:edges.pattern_role:x-wavy,nodes.role:x-betterify-risk"),
    ("ok/layout-only", D, None, layout_only, "verify_ok+admit_ok", None, None),
    ("ok/empty-datamatics", D, None, empty_dm, "verify_ok+admit_ok", None, None),
    ("ok/optional-igdm-row", D, bind_text(bt, requirement="OPTIONAL"), bt, "verify_ok+admit_ok", None, None),
    ("ok/limited-runtime-skips-resolution", D, retired_b, bt, "verify_ok+admit:STALE_BINDING", "A1", "resolution:skipped"),
    ("ok/reserialize-stable", D, None, bt, "verify_ok+admit_ok", None, None),
    ("ok/igpv-and-igdm-same-binding", D, both_b, bt, "verify_ok+admit_ok", None, "binding also carries an igpv row"),
    ("reject/not-bound", D, no_row_b, bt, "reject:DATAMATICS_NOT_BOUND", "D0", None),
    ("reject/version-range-excludes", D, excl_b, bt, "reject:DATAMATICS_VERSION_UNSUPPORTED", "D0", None),
    ("reject/payload-digest-mismatch", D, base_b.to_ison(), edge_only, "reject:PAYLOAD_DIGEST_MISMATCH", "D0", None),
    ("reject/binding-fails-igx", D, bad_corpus_b, bt, "reject:CORPUS_DIGEST_MISMATCH", "D0", "IGXError raised from D0"),
    ("reject/oversized-payload", D, None, bt, "reject:DATAMATICS_LIMIT_EXCEEDED", "D1", "limits:max_payload_bytes=16"),
    ("reject/oversized-target", D, None, bt, "reject:DATAMATICS_LIMIT_EXCEEDED", "D1", "limits:max_graph_bytes=16"),
    ("reject/noncanonical-text", D, None, bt + "\n", "reject:MALFORMED_DATAMATICS", "D1", "trailing newline"),
    ("reject/rows-not-sorted", D, None, swap_wire_rows(bt, "cluster 1 order", "region 1 order"), "reject:MALFORMED_DATAMATICS", "D1", "canonical_form"),
    ("reject/unexpected-block", D, None, bt + "\n\nmeta.extra\na\n1", "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/role-outside-vocabulary", D, None, mut(bt, "warning inactive null circle", "warning hot null circle"), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/magnitude-out-of-range", D, None, mut(bt, "0 0.8 1 order", "0 1.5 1 order"), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/magnitude-nan", D, None, mut(bt, "0 0.8 1 order", "0 nan 1 order"), "reject:MALFORMED_DATAMATICS", "D1", "nan parses as a string"),
    ("reject/lod-negative", D, None, mut(bt, "null null 2 0.1 s1", "null null -1 0.1 s1"), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/boolean-not-token", D, None, mut(bt, '"true" document', "true document"), "reject:MALFORMED_DATAMATICS", "D1", "bare boolean"),
    ("reject/badge-too-long", D, None, mut(bt, 'warning null "3" null', f'warning null {"b" * 17} null'), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/all-null-hint-row", D, None, raw(P(nodes=(NodeHints(N1), NODES1))), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/duplicate-node-row", D, None, raw(P(nodes=(NODE1, NODES1, NodeHints(N1, role="warning")))), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/twin-ids", D, None, raw(P(nodes=(NODE1, NODES1, NodeHints(NodeRef("order", "1"), role="warning")))), "reject:MALFORMED_DATAMATICS", "D1", "ID-TWIN-INVARIANT"),
    ("reject/collapse-exclusivity", D, None, raw(P(groups=(REGION, CLUSTER, Group("agg", "aggregate")), members=base.members + (Member("agg", N1),))), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/hierarchy-not-chain", D, None, raw(P(groups=(Group("h1", "hierarchy"), Group("h3", "hierarchy")), members=(Member("h1", N1), Member("h3", N1)))), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/group-self-parent", D, None, raw(P(groups=(Group("region", "hull", parent_group_id="region"),), members=(Member("region", N1),))), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/group-unreachable", D, None, raw(P(groups=(REGION, CLUSTER, Group("lonely", "hull")))), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/direction-without-family", D, None, raw(P(layout=LayoutHints(None, "LR", None))), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/node-id-outside-int64", D, None, mut(bt, "0 0.8 1 order", "0 0.8 9223372036854775808 order"), "reject:MALFORMED_DATAMATICS", "D1", None),
    ("reject/target-sha-mismatch", D, None, P(UNDIRECTED).to_ison(), "reject:TARGET_BINDING_MISMATCH", "D2", None),
    ("reject/target-profile-mismatch", D, None, P(profile="isonl-v1").to_ison(), "reject:TARGET_BINDING_MISMATCH", "D2", None),
    ("reject/unknown-parent-group", D, None, P(groups=(REGION, Group("cluster", "collapse", parent_group_id="nope"))).to_ison(), "reject:UNRESOLVED_REFERENCE", "D3", None),
    ("reject/member-unknown-group", D, None, P(members=base.members + (Member("ghost", N1),)).to_ison(), "reject:UNRESOLVED_REFERENCE", "D3", None),
    ("reject/group-cycle", D, None, P(groups=(Group("a", "hull", parent_group_id="b"), Group("b", "hull", parent_group_id="a")), members=(Member("a", N1),)).to_ison(), "reject:GROUP_CYCLE", "D3", None),
    ("reject/group-depth-budget", D, None, P(groups=chain, members=(Member("g3", N1),)).to_ison(), "reject:DATAMATICS_LIMIT_EXCEEDED", "D3", "limits:max_group_depth=2"),
    ("reject/unresolved-node", D, None, P(nodes=(NODE1, NODES1, NodeHints(NodeRef("order", 9), role="info"))).to_ison(), "reject:UNRESOLVED_OBJECT", "D4", None),
    ("reject/unresolved-edge", D, None, P(edges=(EdgeHints(EdgeAddress(S1, "knows", N1), role="info"),)).to_ison(), "reject:UNRESOLVED_OBJECT", "D4", "directed: reversed edge is absent"),
    ("reject/unresolved-member", D, None, P(members=base.members + (Member("region", NodeRef("order", 77)),)).to_ison(), "reject:UNRESOLVED_OBJECT", "D4", None),
    ("reject/undirected-noncanonical-endpoints", U, None, P(UNDIRECTED, nodes=(), groups=(), members=(), edges=(EdgeHints(EdgeAddress(S1, "knows", N1), role="info"),)).to_ison(), "reject:UNRESOLVED_OBJECT", "D4", "endpoints not canonical"),
    ("reject/two-faults-first-wins", D, None, mut(P(nodes=(NODE1, NODES1, NodeHints(NodeRef("order", 9), role="info"))).to_ison(), f"IGDM/1 {TD}", f"IGDM/1 {'e' * 64}"), "reject:TARGET_BINDING_MISMATCH", "D2", "wrong target sha and unresolved node"),
]


def _details(detail):
    d = {}
    for item in (detail or "").split(";"):
        if ":" in item:
            k, v = item.split(":", 1)
            d.setdefault(k.strip(), []).append(v.strip())
    return d


def check(id_, target_rel, binding_text, payload_text, expect, step, detail) -> None:
    d = _details(detail)
    limits = Limits(**{k: int(v) for item in d.get("limits", []) for k, v in [item.split("=")]})
    tokens = expect.split("+")
    try:
        result, dm, decision = verify_and_admit(payload_text.encode("utf-8"), ExtensionBinding.from_ison(binding_text), GRAPHS[target_rel],
                                                limits=limits, baselines=B)
    except (IGXError, IGDMError) as e:
        s = "D0" if isinstance(e, IGXError) else e.step
        assert tokens[0].startswith("reject:") and (e.code, s) == (tokens[0][len("reject:"):], step), (id_, e)
        return
    assert "verify_ok" in tokens, id_
    for csv in d.get("roles", []):
        assert dm.unrecognized_roles == tuple(csv.split(",")), (id_, dm.unrecognized_roles)
    assert dm.object_resolution == ("skipped" if "skipped" in d.get("resolution", []) else "full"), id_
    for t in tokens:
        if t == "admit_ok":
            assert decision.admitted, (id_, decision)
        elif t.startswith("admit:"):
            assert (decision.admitted, decision.code, decision.step) == (False, t[len("admit:"):], step), (id_, decision)


def write_all() -> None:
    for sub in ("graphs/synthetic", "bindings", "payloads"):
        shutil.rmtree(VEC / sub, ignore_errors=True)
        (VEC / sub).mkdir(parents=True)
    for rel, data in GRAPHS.items():
        (VEC / "graphs" / rel).write_bytes(data)
    rows = []
    for id_, target_rel, binding_text, payload_text, expect, step, detail in VECTORS:
        if binding_text is None:
            binding_text = bind_text(payload_text, GRAPHS[target_rel])
        check(id_, target_rel, binding_text, payload_text, expect, step, detail)
        slug = id_.replace("/", "--")
        (VEC / "payloads" / f"{slug}.igdm.ison").write_bytes(payload_text.encode("utf-8"))
        (VEC / "bindings" / f"{slug}.igx.ison").write_bytes(binding_text.encode("utf-8"))
        rows.append({"id": id_, "target": target_rel, "binding": f"{slug}.igx.ison", "payload": f"{slug}.igdm.ison", "expect": expect, "step": step, "detail": detail})
    doc = Document(blocks=[Block("meta", "corpus", ["datamatics_spec", "version"], [{"datamatics_spec": "IGDM/1", "version": 1}]),
                           Block("table", "vectors", ["id", "target", "binding", "payload", "expect", "step", "detail"], rows)])
    (VEC / "manifest.ison").write_bytes((dumps_canonical(doc) + "\n").encode("utf-8"))
    print(f"wrote {len(rows)} vectors")


if __name__ == "__main__":
    write_all()

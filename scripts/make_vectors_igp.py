#!/usr/bin/env python3
"""Generate vectors/igp1 (sources, policies, expected result/payload bytes, manifest) from the public API plus deliberate mutations (21 section 6).

Every row is asserted against the runtime before it is written: the manifest records observed behaviour.
Run from the repo root with the venv:  .venv/Scripts/python.exe scripts/make_vectors_igp.py [OUT_DIR]
"""

from __future__ import annotations

import dataclasses
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "isongraph-ext" / "src"))

from ison_graph import ISONGraph  # noqa: E402
from ison_graph.multigraph import MultiGraph  # noqa: E402
from ison_parser import Block, Document, dumps_canonical  # noqa: E402

from isongraph_ext import igpv  # noqa: E402
from isongraph_ext.igp import IGPError, Limits, Policy, project, verify_projection  # noqa: E402
from isongraph_ext.igpv import NodeRef  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "vectors" / "igp1"


def graph(nodes, edges, directed=True) -> bytes:
    g = ISONGraph(directed=directed)
    for n in nodes:
        g.add_node(n[0], n[1], **(n[2] if len(n) > 2 else {}))
    for e in edges:
        g.add_edge(e[0], e[1], e[2], **(e[3] if len(e) > 3 else {}))
    return g.to_ison().encode("utf-8")


def pol(*anchors, mandatory=(), **kw) -> Policy:
    return Policy(anchors=tuple(NodeRef(*a) for a in anchors), mandatory=tuple(NodeRef(*m) for m in mandatory), **kw)


TREE = graph([("n", "a"), ("n", "b1"), ("n", "b2"), ("n", "c1"), ("n", "c2"), ("n", "d"), ("n", "x"), ("m", "far")],
             [("r", ("n", "a"), ("n", "b1")), ("r", ("n", "a"), ("n", "b2")), ("r", ("n", "b1"), ("n", "c1")), ("r", ("n", "b2"), ("n", "c2")),
              ("r", ("n", "c1"), ("n", "d")), ("s", ("n", "b1"), ("n", "b2")), ("r", ("n", "x"), ("n", "b1")), ("t", ("m", "far"), ("n", "a"))])
INST = graph([("decision", "D-4", {"title": "Relocate the archive"}), ("decision", "D-9"), ("evidence", "FR-19"), ("evidence", "CM-3"),
              ("meeting", "2026-03-12"), ("meeting", "2026-04-01")],
             [("supports", ("evidence", "FR-19"), ("decision", "D-4")), ("supports", ("evidence", "CM-3"), ("decision", "D-4")),
              ("supports", ("evidence", "CM-3"), ("decision", "D-9")), ("decided_at", ("decision", "D-4"), ("meeting", "2026-03-12")),
              ("decided_at", ("decision", "D-9"), ("meeting", "2026-04-01"))])
SUPPLY = graph([("supplier", "S-ACME"), ("supplier", "S-NORD"), ("facility", "F-LYON"), ("facility", "F-OSAKA"), ("component", "C-HOUSING"),
                ("component", "C-SEAL"), ("component", "C-PUMP"), ("component", "C-MOTOR")],
               [("supplies", ("supplier", "S-ACME"), ("facility", "F-LYON")), ("supplies", ("supplier", "S-NORD"), ("facility", "F-LYON")),
                ("produces", ("facility", "F-LYON"), ("component", "C-HOUSING")), ("produces", ("facility", "F-LYON"), ("component", "C-SEAL")),
                ("produces", ("facility", "F-OSAKA"), ("component", "C-MOTOR")), ("depends_on", ("component", "C-PUMP"), ("component", "C-HOUSING")),
                ("depends_on", ("component", "C-PUMP"), ("component", "C-SEAL")), ("depends_on", ("component", "C-PUMP"), ("component", "C-MOTOR"))])
MIXED = graph([("p", 1, {"label": "café ☃", "n": 3, "x": 1.5, "ok": True}), ("p", "s1"), ("q", "1"), ("p", -7)],
              [("r", ("p", 1), ("p", "s1"), {"w": 2}), ("r", ("q", "1"), ("p", -7))])
_m = MultiGraph()
_m.add_node("p", 1)
_m.add_edge("r", ("p", 1), ("p", 1))
_one = ISONGraph()
_one.add_node("p", 1)
_big = ISONGraph()
_big.add_node("p", 2**63)
RAW = {  # sources that are not (or must not be treated as) accepted graphs
    "multigraph": _m.to_ison().encode(), "undirected": graph([("p", 1)], [], directed=False), "isonl": _one.to_isonl().encode(),
    "noncanonical": TREE + b"\n\n", "id-beyond-int64": _big.to_ison().encode(), "node-type-column": b"nodes.p\nid node_type\n1 x\n", "not-utf8": b"\xff\xfe\x00",
}
CHAIN = graph([("n", "a"), ("n", "z"), ("n", "b")], [("r", ("n", "a"), ("n", "z")), ("r", ("n", "z"), ("n", "b"))])
FORK = graph([("n", "a"), ("n", "b"), ("n", "c")], [("r", ("n", "a"), ("n", "b")), ("s", ("n", "a"), ("n", "c"))])
FAR = graph([("n", "a"), ("n", "b"), ("m", "far")], [("r", ("n", "a"), ("n", "b")), ("t", ("m", "far"), ("n", "a"))])
XTYPE = graph([("x", "a"), ("n", "b")], [("r", ("x", "a"), ("n", "b"))])
TREE_LF = TREE + b"\n"   # the Core writer does not emit a final LF, but Q1 admits one
SOURCES = {"chain": CHAIN, "fork": FORK, "far": FAR, "xtype": XTYPE, "tree-lf": TREE_LF, "tree": TREE, "institutional": INST, "supply": SUPPLY, "mixed": MIXED, **RAW}

BASE_POLICY = pol(("n", "a"), direction="out", depth=1)
BT = BASE_POLICY.to_ison()
CONTEXT = pol(("decision", "D-4"), mandatory=[("meeting", "2026-03-12")], node_types=("decision", "evidence", "meeting"),
              relations=("supports", "decided_at"), direction="both", depth=2, max_nodes=50)
IMPACT = pol(("supplier", "S-ACME"), node_types=("supplier", "facility", "component"), relations=("supplies", "produces"), direction="out", depth=3)


def mut(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


# id, source, policy (Policy | str), expect, step, detail   -- ok rows store expected result/payload; verify rows tamper them
OK = "ok"
V = [
    ("ok/anchors-only", "tree", pol(("n", "a"), depth=0), OK, None, "nodes:a"),
    ("ok/depth-1-out", "tree", pol(("n", "a"), depth=1), OK, None, "nodes:a,b1,b2"),
    ("ok/depth-2-both", "tree", pol(("n", "b1"), depth=2, direction="both"), OK, None, "nodes:a,b1,b2,c1,c2,d,x,far"),
    ("ok/direction-in", "tree", pol(("n", "a"), depth=1, direction="in"), OK, None, "nodes:a,far"),
    ("ok/relation-allow-list", "tree", pol(("n", "a"), depth=3, relations=("s",)), OK, None, "nodes:a"),
    ("ok/node-type-allow-list", "tree", pol(("n", "a"), depth=1, direction="both", node_types=("n",)), OK, None, "nodes:a,b1,b2"),
    ("ok/both-allow-lists", "tree", pol(("n", "a"), depth=3, direction="both", node_types=("n",), relations=("r",)), OK, None, "nodes:a,b1,b2,c1,c2,d,x"),
    ("ok/unrestricted-empty-lists", "tree", pol(("n", "a"), depth=1, direction="both"), OK, None, "nodes:a,b1,b2,far"),
    ("ok/int-and-string-ids", "mixed", pol(("p", 1), depth=1), OK, None, "nodes:1,s1"),
    ("ok/same-id-different-types", "mixed", pol(("q", "1"), depth=1), OK, None, "nodes:1,-7"),
    ("ok/induced-sibling-edge", "tree", pol(("n", "a"), depth=1), OK, None, "stats:result_edges=3"),
    ("ok/out-projection-holds-incoming-edge", "tree", pol(("n", "b1"), mandatory=[("n", "x")], depth=0), OK, None, "nodes:b1,x;stats:result_edges=1"),
    ("ok/mandatory-inside-traversal", "tree", pol(("n", "a"), mandatory=[("n", "b1")], depth=1), OK, None, "nodes:a,b1,b2"),
    ("ok/mandatory-outside-traversal-induced-edge", "tree", pol(("n", "a"), mandatory=[("m", "far")], depth=0, node_types=("n",)), OK, None,
     "nodes:a,far;stats:result_edges=1"),
    ("ok/mandatory-also-anchor", "tree", pol(("n", "a"), mandatory=[("n", "a")], depth=0), OK, None, "nodes:a"),
    ("ok/mandatory-survives-without-edge", "tree", pol(("n", "a"), mandatory=[("m", "far")], depth=1, max_edges=0), OK, None,
     "nodes:a,b1,b2,far;stats:result_edges=0,pruned_edges=4,truncated=true"),
    ("ok/node-budget-farthest-first", "tree", pol(("n", "a"), depth=3, max_nodes=4), OK, None, "nodes:a,b1,b2,c1;stats:pruned_nodes=2,truncated=true"),
    ("ok/edge-budget-by-distance", "tree", pol(("n", "a"), depth=3, max_edges=3), OK, None, "stats:result_edges=3,pruned_edges=3"),
    ("ok/protected-equals-max-nodes", "tree", pol(("n", "a"), mandatory=[("n", "d")], depth=0, max_nodes=2), OK, None, "nodes:a,d"),
    ("ok/property-carry-over", "mixed", pol(("p", 1), depth=1), OK, None, "nodes:1,s1"),
    ("ok/stats-exclude-never-selected", "tree", pol(("n", "a"), depth=1, max_nodes=2), OK, None, "stats:selected_nodes=2,pruned_nodes=1"),
    ("ok/institutional-context", "institutional", CONTEXT, OK, None, "nodes:D-4,D-9,FR-19,CM-3,2026-03-12;stats:result_edges=4"),
    ("ok/supply-chain-impact", "supply", IMPACT, OK, None, "nodes:S-ACME,F-LYON,C-HOUSING,C-SEAL"),
    ("ok/whole-graph-identity", "tree", pol(("n", "a"), depth=3, direction="both"), OK, None, "result:source"),
    ("ok/node-budget-distance-before-address", "chain", pol(("n", "a"), depth=2, max_nodes=2), OK, None, "nodes:a,z;farthest first: b is farther but sorts before z"),
    ("ok/edge-budget-tie-break-greatest-edge-order", "fork", pol(("n", "a"), depth=1, max_edges=1), OK, None, "stats:result_edges=1,pruned_edges=1;both edges at distance 1: (a,s,c) is removed first"),
    ("ok/edge-budget-untraversed-mandatory-first", "far", pol(("n", "a"), mandatory=[("m", "far")], depth=1, node_types=("n",), max_edges=1), OK, None, "nodes:a,b,far;stats:result_edges=1,pruned_edges=1;the edge to the untraversed mandatory node has distance infinity"),
    ("ok/anchor-outside-node-type-allow-list", "xtype", pol(("x", "a"), depth=1, node_types=("n",)), OK, None, "nodes:a,b;an anchor is selected whatever its type"),
    ("ok/trailing-lf-source-identity-rows", "tree-lf", pol(("n", "a"), depth=3, direction="both"), OK, None, "nodes:a,b1,b2,c1,c2,d,x,far;the result is not byte-identical to the source, so the lineage has identity rows"),
    # --- policy rejections
    ("reject/policy-noncanonical", "tree", BT + "\n", "reject:POLICY_MALFORMED", "Q0", None),
    ("reject/policy-duplicate-block", "tree", BT + "\n\nmeta.igp\ndepth\n1", "reject:POLICY_MALFORMED", "Q0", None),
    ("reject/policy-unexpected-block", "tree", BT + "\n\nmeta.extra\na\n1", "reject:POLICY_MALFORMED", "Q0", None),
    ("reject/policy-wrong-spec", "tree", mut(BT, "IGP/1", "IGP/2"), "reject:POLICY_VERSION_UNSUPPORTED", "Q0", None),
    ("reject/policy-bad-direction", "tree", mut(BT, "1 out", "1 sideways"), "reject:POLICY_MALFORMED", "Q0", None),
    ("reject/policy-depth-out-of-range", "tree", mut(BT, "1 out", "1048577 out"), "reject:POLICY_MALFORMED", "Q0", None),
    ("reject/policy-zero-anchors", "tree", mut(BT, "a n\n", ""), "reject:POLICY_MALFORMED", "Q0", None),
    ("reject/policy-duplicate-anchor", "tree", mut(BT, "a n", "a n\na n"), "reject:POLICY_MALFORMED", "Q0", None),
    ("reject/policy-id-beyond-int64", "tree", mut(BT, "a n", "9223372036854775808 n"), "reject:POLICY_MALFORMED", "Q0", None),
    ("reject/policy-twin-ids", "tree", mut(pol(("p", 1)).to_ison(), "table.mandatory\nnode_id node_type", 'table.mandatory\nnode_id node_type\n"1" p'),
     "reject:POLICY_MALFORMED", "Q0", "INT64 1 anchor and STRING 1 mandatory node"),
    ("reject/policy-unknown-identifier", "tree", mut(BT, "table.node_types\nnode_type", 'table.node_types\nnode_type\n"a b"'), "reject:POLICY_MALFORMED", "Q0", None),
    ("reject/policy-oversized", "tree", BASE_POLICY, "reject:PROJECTION_LIMIT_EXCEEDED", "Q0", "limits:max_policy_bytes=10"),
    # --- source rejections
    ("reject/source-multigraph", "multigraph", BASE_POLICY, "reject:SOURCE_UNSUPPORTED", "Q1", None),
    ("reject/source-undirected", "undirected", pol(("p", 1)), "reject:SOURCE_UNSUPPORTED", "Q1", None),
    ("reject/source-isonl", "isonl", pol(("p", 1)), "reject:SOURCE_UNSUPPORTED", "Q1", "the exact bytes of an ISONL document"),
    ("reject/source-noncanonical", "noncanonical", BASE_POLICY, "reject:SOURCE_UNSUPPORTED", "Q1", None),
    ("reject/source-id-beyond-int64", "id-beyond-int64", pol(("p", 1)), "reject:SOURCE_UNSUPPORTED", "Q1", None),
    ("reject/source-node-type-column", "node-type-column", pol(("p", 1)), "reject:SOURCE_UNSUPPORTED", "Q1", "Core itself cannot load a property column named node_type"),
    ("reject/source-not-utf8", "not-utf8", BASE_POLICY, "reject:SOURCE_UNSUPPORTED", "Q1", None),
    ("reject/source-oversized", "tree", BASE_POLICY, "reject:PROJECTION_LIMIT_EXCEEDED", "Q1", "limits:max_source_bytes=10"),
    # --- selection and lineage rejections
    ("reject/anchor-not-found", "tree", pol(("n", "nope")), "reject:ANCHOR_NOT_FOUND", "Q2", None),
    ("reject/mandatory-not-found", "tree", pol(("n", "a"), mandatory=[("n", "nope")]), "reject:MANDATORY_NOT_FOUND", "Q2", None),
    ("reject/typed-id-mismatch", "mixed", pol(("q", 1)), "reject:ANCHOR_NOT_FOUND", "Q2", "INT64 1 is not STRING 1"),
    ("reject/budget-unsatisfiable", "tree", pol(("n", "a"), mandatory=[("n", "d")], max_nodes=1), "reject:PROJECTION_BUDGET_UNSATISFIABLE", "Q2", None),
    ("reject/lineage-row-limit", "institutional", CONTEXT, "reject:PROJECTION_LIMIT_EXCEEDED", "Q3", "limits:lineage.max_rows_per_table=17"),
    ("reject/lineage-byte-limit", "institutional", CONTEXT, "reject:PROJECTION_LIMIT_EXCEEDED", "Q3", "limits:lineage.max_payload_bytes=200"),
    ("reject/two-faults-first-wins", "multigraph", BT + "\n", "reject:POLICY_MALFORMED", "Q0", "bad policy and bad source: Q0 fires first"),
    # --- verification rejections (stored result/payload are the tampered artifacts)
    ("reject/verify-tampered-result", "institutional", CONTEXT, "reject:RESULT_MISMATCH", "Q4", "verify:result"),
    ("reject/verify-tampered-payload", "institutional", CONTEXT, "reject:LINEAGE_MISMATCH", "Q4", "verify:payload"),
    ("reject/verify-implementation-version", "institutional", CONTEXT, "reject:IMPLEMENTATION_VERSION_MISMATCH", "Q4", "verify:version"),
    ("reject/verify-version-before-result", "institutional", CONTEXT, "reject:IMPLEMENTATION_VERSION_MISMATCH", "Q4", "verify:version-result"),
    ("reject/verify-policy-changed", "institutional", dataclasses.replace(CONTEXT, depth=1), "reject:RESULT_MISMATCH", "Q4", "verify:policy"),
]


def details(detail):
    d = {}
    for item in (detail or "").split(";"):
        if ":" in item:
            k, v = item.split(":", 1)
            d.setdefault(k.strip(), []).append(v.strip())
    return d


def limits_of(d) -> Limits:
    kw, lin = {}, {}
    for item in d.get("limits", []):
        name, value = item.split("=")
        (lin if name.startswith("lineage.") else kw)[name.removeprefix("lineage.")] = int(value)
    return Limits(**kw, **({"lineage": igpv.Limits(**lin)} if lin else {}))


def write_all() -> None:
    for sub in ("sources", "policies", "expected"):
        shutil.rmtree(OUT / sub, ignore_errors=True)
        (OUT / sub).mkdir(parents=True)
    for name, data in SOURCES.items():
        (OUT / "sources" / f"{name}.ison").write_bytes(data)
    rows = []
    for id_, src, pol_, expect, step, detail in V:
        d = details(detail)
        limits = limits_of(d)
        slug = id_.replace("/", "--")
        text = pol_ if isinstance(pol_, str) else pol_.to_ison()
        (OUT / "policies" / f"{slug}.igp.ison").write_bytes(text.encode("utf-8"))
        source = SOURCES[src]
        result_name = payload_name = "none"
        tamper = d.get("verify", [None])[0]
        if expect == OK or tamper:
            base_pol = CONTEXT if tamper in ("result", "payload", "version", "version-result") else pol_
            base = project(source, base_pol, limits=limits)
            result, payload = base.result_bytes, base.payload
            if tamper == "result":
                result = result + b"\n"
            elif tamper == "payload":
                payload = dataclasses.replace(payload, derivations=tuple(x for x in payload.derivations if x.derivation_id != "dn0"),
                                              objects=tuple(x for x in payload.objects if x.object_id not in ("n0", "o0")))
            elif tamper == "version":
                payload = dataclasses.replace(payload, producers=(dataclasses.replace(payload.producers[0], version="0.9.0"),))
            elif tamper == "version-result":
                result = result + b"\n"
                payload = dataclasses.replace(payload, producers=(dataclasses.replace(payload.producers[0], version="0.9.0"),))
            elif tamper == "policy":
                base = project(source, CONTEXT)                       # artifacts of the original policy, verified against the changed one
                result, payload = base.result_bytes, base.payload
            result_name, payload_name = f"{slug}.result.ison", f"{slug}.igpv.ison"
            (OUT / "expected" / result_name).write_bytes(result)
            (OUT / "expected" / payload_name).write_bytes(payload.to_ison().encode("utf-8"))
            check_row(id_, source, text, expect, step, d, limits, result, payload.to_ison(), tamper)
        else:
            check_row(id_, source, text, expect, step, d, limits, None, None, None)
        rows.append({"id": id_, "source": f"{src}.ison", "policy": f"{slug}.igp.ison", "result": result_name, "payload": payload_name,
                     "expect": expect, "step": step, "detail": detail})
    doc = Document(blocks=[Block("meta", "corpus", ["policy_spec", "version"], [{"policy_spec": "IGP/1", "version": 1}]),
                           Block("table", "vectors", ["id", "source", "policy", "result", "payload", "expect", "step", "detail"], rows)])
    (OUT / "manifest.ison").write_bytes((dumps_canonical(doc) + "\n").encode("utf-8"))
    print(f"wrote {len(rows)} vectors to {OUT}")


def check_row(id_, source, text, expect, step, d, limits, result, payload, tamper) -> None:
    try:
        if tamper:
            verify_projection(source, text.encode("utf-8"), result, payload, limits=limits)
        else:
            proj = project(source, text.encode("utf-8"), limits=limits)
    except IGPError as e:
        assert expect == f"reject:{e.code}" and e.step == step, (id_, e)
        return
    assert expect == OK and not tamper, (id_, "expected a rejection")
    ids = [n.id for n in ISONGraph.from_ison(proj.result_bytes.decode()).nodes()]
    for spec in d.get("nodes", []):
        assert sorted(map(str, ids)) == sorted(spec.split(",")), (id_, ids)
    for spec in d.get("stats", []):
        for kv in spec.split(","):
            k, v = kv.split("=")
            assert str(proj.stats[k]).lower() == v, (id_, k, proj.stats[k])
    if "source" in d.get("result", []):
        assert proj.result_bytes == source, id_
    sources = {hashlib.sha256(source).hexdigest(): source}               # every successful projection's lineage must be admitted by IGPV/1
    binding = igpv.bind(proj.result_bytes, proj.payload, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact", sources=sources)
    assert igpv.verify_and_admit(proj.payload, binding, proj.result_bytes, sources=sources)[2].admitted, id_


if __name__ == "__main__":
    write_all()

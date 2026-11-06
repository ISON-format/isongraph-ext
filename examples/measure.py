"""Informational timings, measured separately so nothing is counted twice. No thresholds, no caching, no optimisation.

    python measure.py [N ...]        # default: 100 1000 (nodes; edges = 2N). Larger N is an optional local run.

Columns (seconds, single wall-clock run each):
  core_parse    ISONGraph.from_ison on the graph text                         (what a Core-only consumer pays)
  igx_verify    igx.verify of the binding                                     (IGX alone)
  igpv_total    igpv.verify_and_admit  -- INCLUDES an igx verification inside
  igpv_extra    igpv_total - igx_verify  (the capability's own steps)
  igdm_total    igdm.verify_and_admit  -- INCLUDES an igx verification inside
  igdm_extra    igdm_total - igx_verify
  svg_render    igdm_to_svg.render (generation only, payload already verified)
"""
from __future__ import annotations

import hashlib
import sys
import time

from ison_graph import ISONGraph

from igdm_to_svg import render
from isongraph_ext import igdm, igpv, igx
from isongraph_ext.igdm import DatamaticsPayload, Group, Member, NodeHints
from isongraph_ext.igpv import Artifact, Attribution, GraphObject, NodeRef, Producer, ProvenancePayload

sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
KW = dict(serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")
DOC = b"source document\n" * 8


def timed(fn):
    t = time.perf_counter()
    out = fn()
    return time.perf_counter() - t, out


def run(n: int) -> dict:
    g = ISONGraph()
    for i in range(n):
        g.add_node("item", i, name=f"item {i}")
    for i in range(n):
        g.add_edge("links", ("item", i), ("item", (i + 1) % n))
        g.add_edge("feeds", ("item", i), ("item", (i + 2) % n))
    text = g.to_ison()
    G = text.encode("utf-8")
    row = {"nodes": n, "edges": 2 * n}
    row["core_parse"], _ = timed(lambda: ISONGraph.from_ison(text))

    pp = ProvenancePayload(sha(G), "ison-v1", artifacts=(Artifact("doc", sha(DOC), "document", len(DOC)),),
                           producers=(Producer("x", "extractor", "example", "1"),),
                           objects=tuple(GraphObject(f"o{i}", "node", node=NodeRef("item", i)) for i in range(n)),
                           attributions=tuple(Attribution(f"a{i}", f"o{i}", "doc", "x") for i in range(n)))
    dp = DatamaticsPayload(sha(G), "ison-v1", nodes=tuple(NodeHints(igdm.NodeRef("item", i), role="neutral") for i in range(n)),
                           groups=(Group("all", "hull"),), members=tuple(Member("all", igdm.NodeRef("item", i)) for i in range(n)))
    pb, db = pp.to_ison().encode("utf-8"), dp.to_ison().encode("utf-8")
    bind_igx = igx.bind(G, **KW)
    bind_pv = igx.bind(G, capabilities=(igx.Capability("igpv", "^1", "REQUIRED", sha(pb)),), **KW)
    bind_dm = igx.bind(G, capabilities=(igx.Capability("igdm", "^1", "REQUIRED", sha(db)),), **KW)
    row["igx_verify"], _ = timed(lambda: igx.verify(bind_igx, G))
    row["igpv_total"], _ = timed(lambda: igpv.verify_and_admit(pb, bind_pv, G, sources={sha(DOC): DOC}))
    row["igpv_extra"] = row["igpv_total"] - row["igx_verify"]
    row["igdm_total"], _ = timed(lambda: igdm.verify_and_admit(db, bind_dm, G))
    row["igdm_extra"] = row["igdm_total"] - row["igx_verify"]
    row["svg_render"], svg = timed(lambda: render(G, dp))
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    return row


def main(argv: list[str]) -> int:
    sizes = [int(a) for a in argv] or [100, 1000]
    print("seconds; igpv/igdm totals include an IGX verification (see *_extra); informational only")
    for n in sizes:
        r = run(n)
        print(" ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in r.items()), flush=True)
    print("OK: measure")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

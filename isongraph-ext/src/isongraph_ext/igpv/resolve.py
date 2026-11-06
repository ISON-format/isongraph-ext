"""P4 primitives (18 §1.2, §4.1): NodeRef ordering, canonical undirected endpoints, Core loading and object lookup."""

from __future__ import annotations

from ison_graph.multigraph import MultiGraph

from ..igx.source import _load
from . import records as R
from .errors import IGPVError


def node_ref_key(ref: R.NodeRef) -> tuple:
    """13 §2.3: node_type bytes, then INT64 before STRING, ints numerically, strings by UTF-8 bytes."""
    if R.is_int(ref.node_id):
        return (ref.node_type.encode("utf-8"), 0, ref.node_id)
    return (ref.node_type.encode("utf-8"), 1, ref.node_id.encode("utf-8", "surrogatepass"))


def canonical_endpoints(a: R.NodeRef, b: R.NodeRef) -> tuple[R.NodeRef, R.NodeRef]:
    return (a, b) if node_ref_key(a) <= node_ref_key(b) else (b, a)


def load_graph(data: bytes, profile: str, where: str):
    try:
        graph, _doc = _load(data, profile)
    except Exception as e:  # Core's own hierarchy plus decode errors: whatever it is, the objects cannot be resolved
        raise IGPVError("UNRESOLVED_OBJECT", where, f"graph does not load under the pinned Core: {e}", "P4") from None
    return graph


def resolve_object(graph, obj: R.GraphObject, where: str) -> None:
    def fail(col: str, detail: str) -> None:
        raise IGPVError("UNRESOLVED_OBJECT", f"{where}.{col}", detail, "P4")

    if obj.kind == "graph":
        return
    if obj.kind == "node":
        n = obj.node
        try:
            found = graph.has_node(n.node_type, n.node_id)
        except Exception:
            found = False
        if not found:
            fail("node_id", f"no node {n.node_type}:{n.node_id!r} in the graph")
        return
    e = obj.edge
    if not getattr(graph, "directed", True) and canonical_endpoints(e.source, e.target) != (e.source, e.target):
        fail("source_id", "endpoints not canonical for an undirected graph (13 §2.3 order required)")
    src = (e.source.node_type, e.source.node_id)
    tgt = (e.target.node_type, e.target.node_id)
    try:
        if isinstance(graph, MultiGraph):
            found = graph.has_edge(e.relation, src, tgt, key=int(e.ordinal))
        else:
            if e.ordinal != "0":
                fail("ordinal", 'simple graph edges carry ordinal "0"')
            found = graph.has_edge(e.relation, src, tgt)
    except IGPVError:
        raise
    except Exception:
        found = False
    if not found:
        fail("relation", f"no edge {src!r} -{e.relation}-> {tgt!r} ordinal {e.ordinal} in the graph")

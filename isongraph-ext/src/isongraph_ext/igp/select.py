"""Q2: structural selection (21 §2). Pure, iterative, adjacency indexes built once."""

from __future__ import annotations

from dataclasses import dataclass

from ison_graph import ISONGraph

from ..igpv.records import NodeRef
from ..igpv.resolve import node_ref_key
from .errors import IGPError
from .records import Policy, utf8

INF = 1 << 62
Ref = tuple  # (node_type, node_id)
Edge = tuple  # (source Ref, relation, target Ref)


def node_key(ref: Ref) -> tuple:
    return node_ref_key(NodeRef(ref[0], ref[1]))


def edge_key(e: Edge) -> tuple:
    return (node_key(e[0]), utf8(e[1]), node_key(e[2]))


@dataclass(frozen=True)
class Selection:
    nodes: tuple[Ref, ...]          # canonical order
    edges: tuple[Edge, ...]         # canonical order
    stats: dict


def select(g: ISONGraph, pol: Policy) -> Selection:
    nodes = {(n.type, n.id) for n in g.nodes()}
    all_edges = [(e.source, e.rel_type, e.target) for e in g.edges()]
    allow_rel, allow_type = set(pol.relations), set(pol.node_types)
    ok_edges = [e for e in all_edges if not allow_rel or e[1] in allow_rel]
    out_adj: dict[Ref, list[Ref]] = {}
    in_adj: dict[Ref, list[Ref]] = {}
    for s, _r, t in ok_edges:
        out_adj.setdefault(s, []).append(t)
        in_adj.setdefault(t, []).append(s)
    anchors = [(a.node_type, a.node_id) for a in pol.anchors]
    mandatory = [(m.node_type, m.node_id) for m in pol.mandatory]
    for a in anchors:                                                    # 1. resolve (canonical order: Policy holds them sorted)
        if a not in nodes:
            raise IGPError("ANCHOR_NOT_FOUND", f"table.anchors.{a[0]}:{a[1]}", "no such node in the source", "Q2")
    for m in mandatory:
        if m not in nodes:
            raise IGPError("MANDATORY_NOT_FOUND", f"table.mandatory.{m[0]}:{m[1]}", "no such node in the source", "Q2")
    dist: dict[Ref, int] = {a: 0 for a in anchors}                       # 2. traverse (multi-source BFS)
    frontier, level = list(anchors), 0
    while frontier and level < pol.depth:
        level += 1
        nxt: list[Ref] = []
        for n in frontier:
            neigh = []
            if pol.direction in ("out", "both"):
                neigh += out_adj.get(n, ())
            if pol.direction in ("in", "both"):
                neigh += in_adj.get(n, ())
            for m in neigh:
                if m in dist or (allow_type and m[0] not in allow_type):
                    continue
                dist[m] = level
                nxt.append(m)
        frontier = nxt
    for m in mandatory:                                                  # 3. mandatory nodes, whatever their distance or type
        dist.setdefault(m, INF)
    protected = set(anchors) | set(mandatory)
    pruned_nodes = pruned_edges = 0
    if pol.max_nodes is not None and len(dist) > pol.max_nodes:          # 5. node budget: farthest first, greatest address first
        if len(protected) > pol.max_nodes:
            raise IGPError("PROJECTION_BUDGET_UNSATISFIABLE", "meta.igp.max_nodes",
                           f"{len(protected)} anchors and mandatory nodes exceed max_nodes {pol.max_nodes}", "Q2")
        removable = sorted((n for n in dist if n not in protected), key=lambda n: (dist[n], node_key(n)))
        pruned_nodes = len(dist) - pol.max_nodes
        for n in removable[len(removable) - pruned_nodes:]:
            del dist[n]
    edges = [e for e in ok_edges if e[0] in dist and e[2] in dist]       # 4. induced edges (after any node pruning)
    if pol.max_edges is not None and len(edges) > pol.max_edges:         # 6. edge budget
        ranked = sorted(edges, key=lambda e: (max(dist[e[0]], dist[e[2]]), edge_key(e)))
        pruned_edges = len(edges) - pol.max_edges
        edges = ranked[:pol.max_edges]
    nodes_out = tuple(sorted(dist, key=node_key))
    edges_out = tuple(sorted(edges, key=edge_key))
    stats = {"source_nodes": len(nodes), "source_edges": len(all_edges), "selected_nodes": len(nodes_out), "result_edges": len(edges_out),
             "pruned_nodes": pruned_nodes, "pruned_edges": pruned_edges, "truncated": bool(pruned_nodes or pruned_edges)}
    return Selection(nodes_out, edges_out, stats)

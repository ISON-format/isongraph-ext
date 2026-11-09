"""Shared fixtures for the igp tests: tiny directed graphs built with the pinned Core, non-software vocabulary."""
from ison_graph import ISONGraph

from isongraph_ext.igp import Policy
from isongraph_ext.igpv import NodeRef


def graph_bytes(nodes, edges, directed=True) -> bytes:
    """nodes: (type, id[, props]); edges: (relation, (type, id), (type, id)[, props])."""
    g = ISONGraph(directed=directed)
    for n in nodes:
        g.add_node(n[0], n[1], **(n[2] if len(n) > 2 else {}))
    for e in edges:
        g.add_edge(e[0], e[1], e[2], **(e[3] if len(e) > 3 else {}))
    return g.to_ison().encode("utf-8")


def ref(t, i) -> NodeRef:
    return NodeRef(t, i)


def pol(*anchors, **kw) -> Policy:
    return Policy(anchors=tuple(NodeRef(*a) for a in anchors), **{k: (tuple(NodeRef(*m) for m in v) if k == "mandatory" else v) for k, v in kw.items()})


# Institutional scenario: decisions, evidence, meetings (no software vocabulary).
INSTITUTIONAL = graph_bytes(
    [("decision", "D-4", {"title": "Relocate the archive"}), ("decision", "D-9"), ("evidence", "FR-19"), ("evidence", "CM-3"),
     ("meeting", "2026-03-12"), ("meeting", "2026-04-01")],
    [("supports", ("evidence", "FR-19"), ("decision", "D-4")), ("supports", ("evidence", "CM-3"), ("decision", "D-4")),
     ("supports", ("evidence", "CM-3"), ("decision", "D-9")), ("decided_at", ("decision", "D-4"), ("meeting", "2026-03-12")),
     ("decided_at", ("decision", "D-9"), ("meeting", "2026-04-01"))])

# Supply-chain scenario: suppliers, facilities, components.
SUPPLY = graph_bytes(
    [("supplier", "S-ACME"), ("supplier", "S-NORD"), ("facility", "F-LYON"), ("facility", "F-OSAKA"),
     ("component", "C-HOUSING"), ("component", "C-SEAL"), ("component", "C-PUMP"), ("component", "C-MOTOR")],
    [("supplies", ("supplier", "S-ACME"), ("facility", "F-LYON")), ("supplies", ("supplier", "S-NORD"), ("facility", "F-LYON")),
     ("produces", ("facility", "F-LYON"), ("component", "C-HOUSING")), ("produces", ("facility", "F-LYON"), ("component", "C-SEAL")),
     ("produces", ("facility", "F-OSAKA"), ("component", "C-MOTOR")),
     ("depends_on", ("component", "C-PUMP"), ("component", "C-HOUSING")), ("depends_on", ("component", "C-PUMP"), ("component", "C-SEAL")),
     ("depends_on", ("component", "C-PUMP"), ("component", "C-MOTOR"))])

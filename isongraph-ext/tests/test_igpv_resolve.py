import pytest
from ison_graph import ISONGraph
from ison_graph.multigraph import MultiGraph

from isongraph_ext.igpv.errors import IGPVError
from isongraph_ext.igpv.records import EdgeAddress, GraphObject, NodeRef
from isongraph_ext.igpv.resolve import canonical_endpoints, load_graph, node_ref_key, resolve_object


def _directed():
    g = ISONGraph()
    g.add_node("p", 1); g.add_node("p", "s1"); g.add_edge("knows", ("p", 1), ("p", "s1"))
    return g


def _undirected():
    g = ISONGraph(directed=False)
    g.add_node("p", 1); g.add_node("p", "s1"); g.add_edge("knows", ("p", "s1"), ("p", 1))     # added reversed on purpose
    return g


def _multi():
    g = MultiGraph()
    g.add_node("p", 1); g.add_node("p", 2); g.add_edge("r", ("p", 1), ("p", 2)); g.add_edge("r", ("p", 1), ("p", 2), key=10)
    return g


def _fails(graph, obj, col):
    with pytest.raises(IGPVError) as info:
        resolve_object(graph, obj, "table.objects.x")
    assert (info.value.code, info.value.step, info.value.field) == ("UNRESOLVED_OBJECT", "P4", f"table.objects.x.{col}"), info.value
    return info.value.detail


def test_node_ref_ordering_pins_13_2_3():
    assert node_ref_key(NodeRef("p", 1)) < node_ref_key(NodeRef("p", "1"))       # INT64 < STRING
    assert node_ref_key(NodeRef("p", 2)) < node_ref_key(NodeRef("p", 10))        # ints numerically
    assert node_ref_key(NodeRef("p", "10")) < node_ref_key(NodeRef("p", "2"))    # strings by bytes
    assert node_ref_key(NodeRef("a", 9)) < node_ref_key(NodeRef("b", 1))         # type first
    assert canonical_endpoints(NodeRef("p", "s1"), NodeRef("p", 1)) == (NodeRef("p", 1), NodeRef("p", "s1"))


def test_directed_simple_graph():
    g = _directed()
    resolve_object(g, GraphObject("G", "graph"), "w")
    resolve_object(g, GraphObject("n", "node", node=NodeRef("p", 1)), "w")
    resolve_object(g, GraphObject("e", "edge", edge=EdgeAddress(NodeRef("p", 1), "knows", NodeRef("p", "s1"))), "w")
    assert "no node" in _fails(g, GraphObject("n", "node", node=NodeRef("p", "1")), "node_id")        # typed id: STRING "1" is not INT64 1
    _fails(g, GraphObject("n", "node", node=NodeRef("q", 1)), "node_id")
    _fails(g, GraphObject("e", "edge", edge=EdgeAddress(NodeRef("p", "s1"), "knows", NodeRef("p", 1))), "relation")   # directed: reversed is absent
    _fails(g, GraphObject("e", "edge", edge=EdgeAddress(NodeRef("p", 1), "knows", NodeRef("p", "s1"), "1")), "ordinal")


def test_undirected_reversed_endpoints_unresolved():
    # Review Focus 3: Core's has_edge finds either direction; the address must still be canonical.
    g = _undirected()
    resolve_object(g, GraphObject("e", "edge", edge=EdgeAddress(NodeRef("p", 1), "knows", NodeRef("p", "s1"))), "w")
    assert "endpoints not canonical" in _fails(g, GraphObject("e", "edge", edge=EdgeAddress(NodeRef("p", "s1"), "knows", NodeRef("p", 1))), "source_id")


def test_multigraph_ordinals():
    g = _multi()
    resolve_object(g, GraphObject("e", "edge", edge=EdgeAddress(NodeRef("p", 1), "r", NodeRef("p", 2), "0")), "w")
    resolve_object(g, GraphObject("e", "edge", edge=EdgeAddress(NodeRef("p", 1), "r", NodeRef("p", 2), "10")), "w")
    _fails(g, GraphObject("e", "edge", edge=EdgeAddress(NodeRef("p", 1), "r", NodeRef("p", 2), "1")), "relation")


def test_load_graph_dispatches_and_fails_closed():
    assert isinstance(load_graph(_multi().to_ison().encode("utf-8"), "ison-v1", "target"), MultiGraph)
    assert isinstance(load_graph(_directed().to_ison().encode("utf-8"), "ison-v1", "target"), ISONGraph)
    with pytest.raises(IGPVError) as info:
        load_graph(b"nodes.p\nid\n1\n1", "ison-v1", "target")
    assert (info.value.code, info.value.step, info.value.field) == ("UNRESOLVED_OBJECT", "P4", "target")

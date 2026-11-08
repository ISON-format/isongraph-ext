import pytest
from igp_helpers import graph_bytes, pol

from isongraph_ext.igp import DEFAULT_LIMITS, IGPError, Policy
from isongraph_ext.igp.select import select
from isongraph_ext.igp.source import load_source

# a -> b1,b2 ; b1 -> c1 ; b2 -> c2 ; c1 -> d ; extra sibling edge b1 -> b2 ; an incoming edge x -> b1
NODES = [("n", "a"), ("n", "b1"), ("n", "b2"), ("n", "c1"), ("n", "c2"), ("n", "d"), ("n", "x"), ("m", "far")]
EDGES = [("r", ("n", "a"), ("n", "b1")), ("r", ("n", "a"), ("n", "b2")), ("r", ("n", "b1"), ("n", "c1")), ("r", ("n", "b2"), ("n", "c2")),
         ("r", ("n", "c1"), ("n", "d")), ("s", ("n", "b1"), ("n", "b2")), ("r", ("n", "x"), ("n", "b1")), ("t", ("m", "far"), ("n", "a"))]
G = load_source(graph_bytes(NODES, EDGES), DEFAULT_LIMITS)


def sel(p: Policy):
    s = select(G, p)
    return {n[1] for n in s.nodes}, {(e[0][1], e[1], e[2][1]) for e in s.edges}, s.stats


def test_depth_and_direction():
    assert sel(pol(("n", "a"), depth=0))[0] == {"a"}
    assert sel(pol(("n", "a"), depth=1))[0] == {"a", "b1", "b2"}
    assert sel(pol(("n", "a"), depth=3))[0] == {"a", "b1", "b2", "c1", "c2", "d"}
    assert sel(pol(("n", "a"), depth=1, direction="in"))[0] == {"a", "far"}
    assert sel(pol(("n", "b1"), depth=1, direction="both"))[0] == {"b1", "a", "c1", "x", "b2"}


def test_induced_edges_include_unwalked_and_incoming_edges():
    nodes, edges, _ = sel(pol(("n", "a"), depth=1, direction="out"))
    assert nodes == {"a", "b1", "b2"}
    assert ("b1", "s", "b2") in edges                                  # sibling edge the BFS never walked
    n2, e2, _ = sel(pol(("n", "b1"), mandatory=[("n", "x")], depth=0))
    assert n2 == {"b1", "x"} and e2 == {("x", "r", "b1")}              # an `out` policy still holds an incoming edge between selected nodes


def test_allow_lists_empty_means_unrestricted():
    assert sel(pol(("n", "a"), depth=3, relations=("r",)))[0] == {"a", "b1", "b2", "c1", "c2", "d"}
    assert sel(pol(("n", "a"), depth=3, relations=("s",)))[0] == {"a"}
    assert sel(pol(("n", "a"), depth=1, direction="both", node_types=("n",)))[0] == {"a", "b1", "b2"}        # far (type m) not entered
    assert ("b1", "s", "b2") not in sel(pol(("n", "a"), depth=1, relations=("r",)))[1]                      # edge allow-list filters induced edges


def test_mandatory_outside_traversal_and_type_exempt():
    nodes, edges, _ = sel(pol(("n", "a"), mandatory=[("m", "far")], depth=0, node_types=("n",)))
    assert nodes == {"a", "far"} and edges == {("far", "t", "a")}      # mandatory node of a disallowed type; induced edge never walked


def test_node_budget_prunes_farthest_first_with_greatest_address_tiebreak():
    nodes, _, st = sel(pol(("n", "a"), depth=3, max_nodes=4))
    assert nodes == {"a", "b1", "b2", "c1"} and st["pruned_nodes"] == 2 and st["truncated"]       # d (dist 3) first, then c2 over c1 (greater address)
    nodes2, _, _ = sel(pol(("n", "a"), mandatory=[("n", "d")], depth=3, max_nodes=4))
    assert "d" in nodes2 and len(nodes2) == 4                                                    # mandatory never pruned


def test_budget_unsatisfiable_when_protected_exceeds_max_nodes():
    with pytest.raises(IGPError) as info:
        select(G, pol(("n", "a"), mandatory=[("n", "d")], max_nodes=1))
    assert (info.value.code, info.value.field, info.value.step) == ("PROJECTION_BUDGET_UNSATISFIABLE", "meta.igp.max_nodes", "Q2")
    assert sel(pol(("n", "a"), mandatory=[("n", "d")], depth=0, max_nodes=2))[0] == {"a", "d"}      # exactly equal is fine


def test_edge_budget_prunes_farthest_and_mandatory_node_survives_without_its_edge():
    _, edges, st = sel(pol(("n", "a"), depth=3, max_edges=3))
    assert len(edges) == 3 and st["pruned_edges"] == 3 and ("c1", "r", "d") not in edges
    nodes, edges0, st0 = sel(pol(("n", "a"), mandatory=[("m", "far")], depth=1, max_edges=0))
    assert "far" in nodes and edges0 == set() and st0["pruned_edges"] > 0                          # node kept, relationship not


def test_stats_pruned_nodes_excludes_nodes_never_selected():
    _, _, st = sel(pol(("n", "a"), depth=1, max_nodes=2))
    assert (st["source_nodes"], st["selected_nodes"], st["pruned_nodes"]) == (8, 2, 1)               # only b1/b2 competed; c1, d, x, far never selected


def test_anchor_and_mandatory_must_exist_and_ids_are_typed():
    for kw, code in (({"anchors": (("n", "nope"),)}, "ANCHOR_NOT_FOUND"), ({"anchors": (("n", "a"),), "mandatory": [("n", "nope")]}, "MANDATORY_NOT_FOUND")):
        anchors = kw.pop("anchors")
        with pytest.raises(IGPError) as info:
            select(G, pol(*anchors, **kw))
        assert (info.value.code, info.value.step) == (code, "Q2")
    ints = load_source(graph_bytes([("p", 1)], []), DEFAULT_LIMITS)
    with pytest.raises(IGPError) as info:
        select(ints, pol(("p", "1")))                                                                # STRING "1" is not INT64 1
    assert info.value.code == "ANCHOR_NOT_FOUND"

import pytest
from igp_helpers import INSTITUTIONAL, graph_bytes
from ison_graph import ISONGraph
from ison_graph.multigraph import MultiGraph

from isongraph_ext.igp import DEFAULT_LIMITS, IGPError, Limits
from isongraph_ext.igp.source import load_source

NODES = [("p", 1), ("p", "s")]
EDGES = [("r", ("p", 1), ("p", "s"))]


def no(data, field=None, code="SOURCE_UNSUPPORTED", limits=DEFAULT_LIMITS):
    with pytest.raises(IGPError) as info:
        load_source(data, limits)
    assert (info.value.code, info.value.step) == (code, "Q1"), info.value
    if field:
        assert info.value.field == field, info.value
    return info.value


def test_accepts_canonical_directed_simple_graph_with_or_without_trailing_lf():
    g = load_source(INSTITUTIONAL, DEFAULT_LIMITS)
    assert g.node_count() == 6 and g.directed
    assert load_source(INSTITUTIONAL + b"\n", DEFAULT_LIMITS).node_count() == 6


def test_rejects_multigraph_undirected_isonl_noncanonical_and_bad_bytes():
    m = MultiGraph()
    m.add_node("p", 1)
    m.add_edge("r", ("p", 1), ("p", 1))
    no(m.to_ison().encode(), "meta.graph.format")
    no(graph_bytes(NODES, EDGES, directed=False), "meta.graph.directed")
    g = ISONGraph()
    g.add_node("p", 1)
    no(g.to_isonl().encode(), "source")                      # Review focus: ISONL bytes that a permissive loader might try
    no(INSTITUTIONAL + b"\n\n", "source")                    # not the Core writer's bytes
    no(INSTITUTIONAL.replace(b"nodes.decision", b"nodes.decision\n"), "source")
    no(b"\xff\xfe", "source")
    no(b"nodes.p\nid node_type\n1 x\n", "source")            # Core itself cannot load a property column named node_type


def test_rejects_node_id_beyond_int64():
    big = ISONGraph()
    big.add_node("p", 2**63)
    no(big.to_ison().encode(), "nodes.p.9223372036854775808")


def test_source_size_limit():
    e = no(INSTITUTIONAL, code="PROJECTION_LIMIT_EXCEEDED", limits=Limits(max_source_bytes=10))
    assert e.field == "max_source_bytes"

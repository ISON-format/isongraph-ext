"""Behavior the frozen IGP/1 spec (21) promises that earlier tests left unpinned. Each test names the mutation it kills (found by the 0.4.0 audit)."""
from dataclasses import replace

import pytest
from igp_helpers import graph_bytes, pol

from isongraph_ext.igp import DEFAULT_LIMITS, IGPError, Limits, Policy, project, verify_projection
from isongraph_ext.igp import policy as P
from isongraph_ext.igp.records import DEPTH_MAX
from isongraph_ext.igp.select import select
from isongraph_ext.igp.source import load_source
from isongraph_ext.igpv import NodeRef, Producer

INT64_MAX = 2**63 - 1


def _select(nodes, edges, policy):
    s = select(load_source(graph_bytes(nodes, edges), DEFAULT_LIMITS), policy)
    return {n[1] for n in s.nodes}, {(e[0][1], e[1], e[2][1]) for e in s.edges}, s.stats


CHAIN = [("n", "a"), ("n", "b"), ("n", "c"), ("n", "d")]
CHAIN_EDGES = [("r", ("n", "a"), ("n", "b")), ("r", ("n", "b"), ("n", "c")), ("r", ("n", "c"), ("n", "d"))]


# --- node and edge budgets -------------------------------------------------------------------------------------------------

def test_protected_nodes_exactly_filling_max_nodes_still_prune_the_rest():
    # reachable 4 > max_nodes 2, protected 2 == max_nodes: pruning must run, not be refused (kills `>` -> `>=` on the protected check)
    nodes, _, st = _select(CHAIN, CHAIN_EDGES, pol(("n", "a"), mandatory=[("n", "d")], depth=3, max_nodes=2))
    assert nodes == {"a", "d"} and st["pruned_nodes"] == 2 and st["truncated"]


def test_node_budget_ties_break_by_greatest_address_not_discovery_order():
    # c9 (via b1) is discovered before c1 (via b2); both sit at distance 2, so the greatest address (c9) must go
    # (kills dropping node_key from the sort)
    nodes, _, _ = _select([("n", "a"), ("n", "b1"), ("n", "b2"), ("n", "c1"), ("n", "c9")],
                          [("r", ("n", "a"), ("n", "b1")), ("r", ("n", "a"), ("n", "b2")), ("r", ("n", "b1"), ("n", "c9")), ("r", ("n", "b2"), ("n", "c1"))],
                          pol(("n", "a"), depth=2, max_nodes=4))
    assert nodes == {"a", "b1", "b2", "c1"}


def test_edge_budget_ties_break_by_edge_order_not_by_the_source_file_order():
    # the source lists edges by relation first, the spec orders them by source first: with every node an anchor all edges tie at distance 0,
    # and the one that sorts last by (source, relation, target) must go (kills dropping edge_key from the sort)
    _, edges, _ = _select([("n", "a"), ("n", "b"), ("n", "c")],
                          [("s", ("n", "a"), ("n", "b")), ("r", ("n", "b"), ("n", "c")), ("r", ("n", "c"), ("n", "a"))],
                          pol(("n", "a"), ("n", "b"), ("n", "c"), depth=0, max_edges=1))
    assert edges == {("a", "s", "b")}


def test_a_mandatory_node_reached_by_the_traversal_keeps_its_real_distance():
    # b is mandatory and also walked at distance 1; its edge must rank by distance 1, not infinity (kills setdefault -> assignment)
    _, edges, _ = _select([("n", "a"), ("n", "b"), ("n", "z")], [("r", ("n", "a"), ("n", "b")), ("r", ("n", "a"), ("n", "z"))],
                          pol(("n", "a"), mandatory=[("n", "b")], depth=1, max_edges=1))
    assert edges == {("a", "r", "b")}


# --- policy field boundaries -----------------------------------------------------------------------------------------------

def test_an_int_id_that_is_a_twin_of_a_string_id_is_rejected_across_anchors_and_mandatory():
    # anchors and mandatory are each sorted on their own, so a STRING anchor can precede its INT64 twin in the mandatory table and vice versa
    for p in (pol(("t", "1"), mandatory=[("t", 1)]), pol(("t", 1), mandatory=[("t", "1")])):
        with pytest.raises(IGPError) as info:
            P.check(p)
        assert info.value.code == "POLICY_MALFORMED" and "ID-TWIN-INVARIANT" in info.value.detail


def test_depth_boundaries_are_inclusive_and_follow_the_smaller_limit():
    P.check(pol(("t", "a"), depth=DEPTH_MAX))
    with pytest.raises(IGPError) as info:
        P.check(pol(("t", "a"), depth=DEPTH_MAX + 1))
    assert (info.value.code, info.value.field) == ("POLICY_MALFORMED", "meta.igp.depth")
    P.check(pol(("t", "a"), depth=7), Limits(max_depth=7))
    with pytest.raises(IGPError):
        P.check(pol(("t", "a"), depth=8), Limits(max_depth=7))


def test_int64_max_is_a_valid_id_and_one_more_is_not():
    p = pol(("t", INT64_MAX))
    assert P.from_ison(P.to_ison(p)) == p
    with pytest.raises(IGPError):
        P.check(pol(("t", INT64_MAX + 1)))
    data = graph_bytes([("t", INT64_MAX), ("t", 1)], [("r", ("t", INT64_MAX), ("t", 1))])
    out = project(data, pol(("t", INT64_MAX), depth=1))
    assert {n[1] for n in select(load_source(data, DEFAULT_LIMITS), pol(("t", INT64_MAX), depth=1)).nodes} == {INT64_MAX, 1}
    assert out.stats["selected_nodes"] == 2


def test_a_second_meta_row_is_reported_on_the_meta_block():
    text = P.to_ison(pol(("t", "a")))
    marker = "meta.igp"
    assert marker in text
    lines = text.split("\n")
    i = next(k for k, ln in enumerate(lines) if ln.startswith("meta.igp"))
    doubled = "\n".join(lines[:i + 3] + [lines[i + 2]] + lines[i + 3:])      # header, fields, row, then a duplicate row
    with pytest.raises(IGPError) as info:
        P.from_ison(doubled)
    assert info.value.code == "POLICY_MALFORMED" and info.value.field == "meta.igp"


# --- budgets accept exactly the limit and refuse one more ------------------------------------------------------------------

def test_policy_byte_budget_is_inclusive_on_serialize_and_parse():
    p = pol(("t", "a"))
    n = len(P.to_ison(p).encode("utf-8"))
    P.to_ison(p, Limits(max_policy_bytes=n))
    P.from_ison(P.to_ison(p), limits=Limits(max_policy_bytes=n))
    for call in (lambda: P.to_ison(p, Limits(max_policy_bytes=n - 1)), lambda: P.from_ison(P.to_ison(p), limits=Limits(max_policy_bytes=n - 1))):
        with pytest.raises(IGPError) as info:
            call()
        assert info.value.code == "PROJECTION_LIMIT_EXCEEDED" and info.value.field == "max_policy_bytes"


def test_policy_row_budget_is_inclusive():
    p = pol(("t", "a"), ("t", "b"), ("t", "c"))
    P.check(p, Limits(max_rows_per_table=3))
    with pytest.raises(IGPError) as info:
        P.check(p, Limits(max_rows_per_table=2))
    assert info.value.code == "PROJECTION_LIMIT_EXCEEDED" and info.value.field == "max_rows_per_table"


def test_lineage_payload_byte_budget_is_inclusive():
    data = graph_bytes([("n", "a"), ("n", "b")], [("r", ("n", "a"), ("n", "b")), ("r", ("n", "b"), ("n", "a"))])
    pr = pol(("n", "a"), depth=0)
    size = len(project(data, pr).payload.to_ison().encode("utf-8"))
    lim = DEFAULT_LIMITS.lineage
    project(data, pr, limits=replace(DEFAULT_LIMITS, lineage=replace(lim, max_payload_bytes=size)))
    with pytest.raises(IGPError) as info:
        project(data, pr, limits=replace(DEFAULT_LIMITS, lineage=replace(lim, max_payload_bytes=size - 1)))
    assert info.value.field == "max_payload_bytes"


# --- verification only looks at the IGP producer ---------------------------------------------------------------------------

def test_a_foreign_producer_does_not_decide_the_implementation_version_verdict():
    data = graph_bytes([("n", "a"), ("n", "b"), ("n", "c"), ("n", "z")], [("r", ("n", "a"), ("n", "b")), ("r", ("n", "a"), ("n", "c"))])
    pr = pol(("n", "a"), depth=1)
    proj = project(data, pr)
    extra = Producer("p9", "transformation", "some-other-tool", "9.9.9")           # no spec: not an IGP producer
    ders = (replace(proj.payload.derivations[0], producer_id="p9"),) + proj.payload.derivations[1:]
    padded = replace(proj.payload, producers=proj.payload.producers + (extra,), derivations=ders)
    padded.to_ison()                                                                 # a well-formed payload that merely differs from the recomputation
    with pytest.raises(IGPError) as info:
        verify_projection(data, pr, proj.result_bytes, padded)
    assert info.value.code == "LINEAGE_MISMATCH"                                     # not IMPLEMENTATION_VERSION_MISMATCH (kills dropping the spec filter)

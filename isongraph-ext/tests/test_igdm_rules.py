import pytest
from igdm_helpers import payload

from isongraph_ext.igdm.errors import IGDMError
from isongraph_ext.igdm.payload import check_references, unrecognized_roles
from isongraph_ext.igdm.records import DEFAULT_LIMITS, EdgeHints, Group, LayoutHints, Limits, Member, NodeHints
from isongraph_ext.igpv.records import EdgeAddress, NodeRef

N, S = NodeRef("order", 1), NodeRef("order", "s1")


def _d1(field, **kw):
    with pytest.raises(IGDMError) as info:
        payload(**kw).check()
    assert (info.value.code, info.value.step, info.value.field) == ("MALFORMED_DATAMATICS", "D1", field), info.value


def _d3(code, field, limits=DEFAULT_LIMITS, **kw):
    p = payload(**kw)
    p.check()
    with pytest.raises(IGDMError) as info:
        check_references(p, limits)
    assert (info.value.code, info.value.step, info.value.field) == (code, "D3", field), info.value


def test_sample_passes():
    p = payload()
    p.check()
    check_references(p, DEFAULT_LIMITS)
    assert unrecognized_roles(p) == ()


def test_uniqueness_and_twins():
    _d1("table.nodes.order:1.node_id", nodes=payload().nodes + (NodeHints(N, role="warning"),))
    _d1("table.edges.order:1-knows-order:s1#0.relation", edges=payload().edges + (EdgeHints(payload().edges[0].edge, role="warning"),))
    _d1("table.groups.region.group_id", groups=payload().groups + (Group("region", "hull"),))
    _d1("table.members.region/order:1.node_id", members=payload().members + (Member("region", N),))
    _d1("table.nodes.order:1.node_id", nodes=payload().nodes + (NodeHints(NodeRef("order", "1"), role="warning"),))          # twin via node row
    _d1("table.members.region/order:1.node_id", members=payload().members + (Member("region", NodeRef("order", "1")),))    # twin via member
    _d1("table.edges.order:1-knows-order:1#0.target_id", edges=(EdgeHints(EdgeAddress(N, "knows", NodeRef("order", "1")), role="neutral"),))


def test_all_null_hint_rows_are_noise():
    _d1("table.nodes.order:1.node_id", nodes=(NodeHints(N),) + payload().nodes[1:])
    _d1("table.edges.order:1-knows-order:s1#0.relation", edges=(EdgeHints(payload().edges[0].edge),))


def test_collapse_aggregate_exclusivity():
    # Review Focus 3: exclusivity spans collapse AND aggregate.
    groups = payload().groups + (Group("agg", "aggregate"),)
    # memberships are held in key order (agg/... < cluster/...); the conflict is reported at the LATER membership
    _d1("table.members.cluster/order:1.group_id", groups=groups, members=payload().members + (Member("agg", N),))
    ok = payload(groups=groups, members=payload().members + (Member("agg", S),))      # s1 is only in a hull otherwise
    ok.check()


def test_hierarchy_chain_rule_and_reachability():
    h = (Group("h1", "hierarchy"), Group("h2", "hierarchy", parent_group_id="h1"), Group("h3", "hierarchy"))
    payload(groups=h[:2], members=(Member("h1", N), Member("h2", N))).check()                               # chain: h2 under h1
    _d1("table.members.h3/order:1.group_id", groups=h, members=(Member("h1", N), Member("h2", N), Member("h3", N)))   # h3 unrelated
    _d1("table.groups.lonely.group_id", groups=payload().groups + (Group("lonely", "hull"),))                # no members, no children
    payload(groups=payload().groups + (Group("outer", "hull"), Group("inner", "hull", parent_group_id="outer")),
            members=payload().members + (Member("inner", S),)).check()                                     # outer reachable via inner


def test_references_cycles_and_depth():
    region = next(g for g in payload().groups if g.group_id == "region")      # records are key-ordered: groups[0] is cluster
    _d3("UNRESOLVED_REFERENCE", "table.groups.cluster.parent_group_id", groups=(region, Group("cluster", "collapse", parent_group_id="nope")))
    _d3("UNRESOLVED_REFERENCE", "table.members.ghost/order:1.group_id", members=payload().members + (Member("ghost", N),))
    cyc = (Group("a", "hull", parent_group_id="b"), Group("b", "hull", parent_group_id="a"))
    _d3("GROUP_CYCLE", "table.groups.a.parent_group_id", groups=cyc, members=(Member("a", N),))
    chain = tuple(Group(f"g{i}", "hull", parent_group_id=(f"g{i - 1}" if i else None)) for i in range(5))
    _d3("DATAMATICS_LIMIT_EXCEEDED", "max_group_depth", limits=Limits(max_group_depth=3), groups=chain, members=(Member("g4", N),))


def test_hierarchy_validation_is_bounded_on_shared_memberships():
    # Review correction 1: one node in 3000 nested hierarchy groups must validate in linear-ish time, not O(m^2 h).
    import time
    chain = tuple(Group(f"g{i}", "hierarchy", parent_group_id=(f"g{i - 1}" if i else None)) for i in range(3000))
    members = tuple(Member(f"g{i}", N) for i in range(3000))
    t0 = time.perf_counter()
    payload(groups=chain, members=members).check()
    assert time.perf_counter() - t0 < 5.0
    broken = chain + (Group("side", "hierarchy"),)
    _d1("table.members.side/order:1.group_id", groups=broken, members=members + (Member("side", N),))


def test_group_depth_budget_iterative():
    # Review Focus 4: a 5000-deep chain is a budget failure, never a RecursionError.
    chain = tuple(Group(f"g{i}", "hull", parent_group_id=(f"g{i - 1}" if i else None)) for i in range(5000))
    _d3("DATAMATICS_LIMIT_EXCEEDED", "max_group_depth", groups=chain, members=(Member("g4999", N),))


def test_unrecognized_roles_reported_sorted_distinct():
    p = payload(nodes=(NodeHints(N, role="x-betterify-risk", ring="x-betterify-risk"), NodeHints(S, shape_role="x-blob")),
                edges=(EdgeHints(payload().edges[0].edge, pattern_role="x-wavy"),), layout=LayoutHints("x-hex"))
    p.check()
    assert unrecognized_roles(p) == ("edges.pattern_role:x-wavy", "layout.family:x-hex", "nodes.ring:x-betterify-risk",
                                     "nodes.role:x-betterify-risk", "nodes.shape_role:x-blob")


def test_deep_chain_is_linear_in_memory_and_time():
    # Review fix 1: ancestry must not materialise ancestor sets; a 50k-deep chain must validate within a small memory bound.
    import time
    import tracemalloc
    n = 50_000
    chain = tuple(Group(f"g{i:06d}", "hierarchy", parent_group_id=(f"g{i - 1:06d}" if i else None)) for i in range(n))
    members = tuple(Member(f"g{i:06d}", N) for i in range(n))
    p = payload(groups=chain, members=members)
    tracemalloc.start()
    t0 = time.perf_counter()
    p.check()
    elapsed = time.perf_counter() - t0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 64 * 1024 * 1024, peak
    assert elapsed < 10.0, elapsed
    _d3("DATAMATICS_LIMIT_EXCEEDED", "max_group_depth", groups=chain, members=members)


def test_hierarchy_chain_reports_first_conflicting_membership_in_key_order():
    # Review fix 2 (19 §1.1): b is a root incomparable with the a-c chain; in key order a < b < c, so b is reported.
    groups = (Group("b", "hierarchy"), Group("c", "hierarchy"), Group("a", "hierarchy", parent_group_id="c"))
    _d1("table.members.b/order:1.group_id", groups=groups, members=(Member("a", N), Member("b", N), Member("c", N)))
    payload(groups=groups[1:], members=(Member("a", N), Member("c", N))).check()      # a under c: a chain


def test_long_cycle_is_group_cycle_not_depth_budget():
    # Review fix 3: a 100-group cycle under default limits is GROUP_CYCLE at the smallest-key member, not a depth failure.
    cyc = tuple(Group(f"c{i:03d}", "hull", parent_group_id=f"c{(i - 1) % 100:03d}") for i in range(100))
    _d3("GROUP_CYCLE", "table.groups.c000.parent_group_id", groups=cyc, members=(Member("c050", N),))


def test_lone_surrogates_in_addresses_are_malformed():
    # Review fix 4: in-memory addresses with no UTF-8 encoding must fail check(), never UnicodeEncodeError later.
    _d1("table.nodes.order:\ud800.node_id", nodes=payload().nodes + (NodeHints(NodeRef("order", "\ud800"), role="info"),))
    _d1("table.nodes.or\udc00der:7.node_type", nodes=payload().nodes + (NodeHints(NodeRef("or\udc00der", 7), role="info"),))
    _d1("table.edges.order:1-kn\udc00ows-order:s1#0.relation", edges=payload().edges + (EdgeHints(EdgeAddress(N, "kn\udc00ows", S), role="info"),))
    _d1("table.members.region/order:\ud800.node_id", members=payload().members + (Member("region", NodeRef("order", "\ud800")),))

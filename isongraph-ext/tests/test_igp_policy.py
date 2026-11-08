import pytest
from igp_helpers import pol

from isongraph_ext.igp import IGPError, Limits, Policy
from isongraph_ext.igpv import NodeRef
from isongraph_ext.igx.digest import sha256_hex

ORACLE = (  # 21 section 1 example; block/field/row order and quoting are the canonical writer's
    "meta.igp\n"
    "depth direction max_edges max_nodes policy_spec\n"
    "2 both null 50 IGP/1\n"
    "\n"
    "table.anchors\n"
    "node_id node_type\n"
    "D-4 decision\n"
    "\n"
    "table.mandatory\n"
    "node_id node_type\n"
    "2026-03-12 meeting\n"
    "\n"
    "table.node_types\n"
    "node_type\n"
    "decision\n"
    "evidence\n"
    "meeting\n"
    "\n"
    "table.relations\n"
    "relation\n"
    "decided_at\n"
    "supports"
)


def sample() -> Policy:
    return pol(("decision", "D-4"), mandatory=[("meeting", "2026-03-12")], node_types=("meeting", "decision", "evidence"),
               relations=("supports", "decided_at"), direction="both", depth=2, max_nodes=50)


def test_to_ison_matches_oracle_and_digest_is_sha256_of_bytes():
    p = sample()
    assert p.to_ison() == ORACLE
    assert p.digest == sha256_hex(ORACLE.encode("utf-8"))


def test_roundtrip_and_construction_order_independence():
    p = sample()
    assert Policy.from_ison(p.to_ison()) == p and Policy.from_ison(p.to_ison().encode("utf-8")) == p
    shuffled = pol(("decision", "D-4"), mandatory=[("meeting", "2026-03-12")], node_types=("evidence", "decision", "meeting"),
                   relations=("decided_at", "supports"), direction="both", depth=2, max_nodes=50)
    assert shuffled == p and shuffled.to_ison() == ORACLE


def rejects(text, code="POLICY_MALFORMED", field=None, limits=None):
    with pytest.raises(IGPError) as info:
        Policy.from_ison(text, **({"limits": limits} if limits else {}))
    assert (info.value.code, info.value.step) == (code, "Q0"), info.value
    if field:
        assert info.value.field == field, info.value
    return info.value


def test_wire_rejections():
    rejects(ORACLE + "\n", field="canonical_form")
    rejects(ORACLE.replace("\n", "\r\n"), field="canonical_form")
    rejects(b"\xff\xfe", field="document")
    rejects(ORACLE + "\n\nmeta.extra\na\n1", field="meta.extra")
    rejects(ORACLE.replace("table.relations", "table.relationz"), field="table.relationz")
    rejects(ORACLE + "\n\nmeta.igp\ndepth\n1", field="meta.igp")
    rejects(ORACLE.replace("IGP/1", "IGP/2"), code="POLICY_VERSION_UNSUPPORTED", field="meta.igp.policy_spec")
    rejects(ORACLE.replace("2 both", "2 sideways"), field="meta.igp.direction")
    rejects(ORACLE.replace("2 both null 50", "-1 both null 50"), field="meta.igp.depth")
    rejects(ORACLE.replace("2 both null 50", "1048577 both null 50"), field="meta.igp.depth")
    rejects(ORACLE.replace("2 both null 50", "2 both null 0"), field="meta.igp.max_nodes")
    rejects(ORACLE.replace("2 both null 50", "2 both -1 50"), field="meta.igp.max_edges")
    rejects(ORACLE.replace("D-4 decision", "D-4 decision\nD-4 decision"), field="table.anchors.decision:D-4.node_id")
    rejects(ORACLE.replace("decision\nevidence", "decision\ndecision"), field="table.node_types.decision.node_type")


def test_programmatic_rules():
    def bad(field, **kw):
        with pytest.raises(IGPError) as info:
            Policy(**kw).to_ison()
        assert (info.value.code, info.value.step, info.value.field) == ("POLICY_MALFORMED", "Q0", field), info.value

    a = NodeRef("decision", "D-4")
    bad("table.anchors", anchors=())
    bad("meta.igp.depth", anchors=(a,), depth=True)
    bad("meta.igp.max_nodes", anchors=(a,), max_nodes=True)
    bad("table.anchors.a:b:x.node_type", anchors=(NodeRef("a:b", "x"),))
    bad("table.anchors.p:9223372036854775808.node_id", anchors=(NodeRef("p", 2**63),))
    bad("table.anchors.p:1.node_id", anchors=(NodeRef("p", 1), NodeRef("p", 1)))
    bad("table.anchors.p:1.node_id", anchors=(NodeRef("p", 1),), mandatory=(NodeRef("p", "1"),))        # twin across tables
    bad("table.node_types.a b.node_type", anchors=(a,), node_types=("a b",))
    bad("table.relations.r.relation", anchors=(a,), relations=("r", "r"))
    bad("table.anchors.p:\ud800.node_id", anchors=(NodeRef("p", "\ud800"),))                           # lone surrogate has no UTF-8 bytes
    Policy(anchors=(NodeRef("p", 1), NodeRef("p", "2")), mandatory=(NodeRef("p", 1),)).to_ison()      # anchor+mandatory overlap is fine


def test_limits():
    e = rejects(ORACLE, code="PROJECTION_LIMIT_EXCEEDED", limits=Limits(max_policy_bytes=10))
    assert e.field == "max_policy_bytes"
    e = rejects(ORACLE, code="PROJECTION_LIMIT_EXCEEDED", limits=Limits(max_rows_per_table=1))
    assert e.field == "max_rows_per_table"


def test_to_ison_enforces_the_byte_budget_for_in_memory_policies():
    from isongraph_ext.igp.policy import to_ison
    assert to_ison(sample(), Limits(max_policy_bytes=len(ORACLE))) == ORACLE
    with pytest.raises(IGPError) as info:
        to_ison(sample(), Limits(max_policy_bytes=len(ORACLE) - 1))
    assert (info.value.code, info.value.field, info.value.step) == ("PROJECTION_LIMIT_EXCEEDED", "max_policy_bytes", "Q0")

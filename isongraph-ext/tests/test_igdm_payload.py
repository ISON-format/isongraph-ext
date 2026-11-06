import pytest
from igdm_helpers import REFERENCE_TEXT, SHA_T, payload

from isongraph_ext.igdm.errors import IGDMError
from isongraph_ext.igdm.payload import DatamaticsPayload
from isongraph_ext.igdm.records import EdgeHints, Group, LayoutHints, Limits, Member, NodeHints
from isongraph_ext.igpv.records import EdgeAddress, NodeRef
from isongraph_ext.igx.digest import sha256_hex


def test_to_ison_matches_spec_literal_oracle():
    assert payload().to_ison() == REFERENCE_TEXT


def test_roundtrip_and_digest():
    p = payload()
    text = p.to_ison()
    q = DatamaticsPayload.from_ison(text)
    assert q == p and q.to_ison() == text and p.digest == sha256_hex(text.encode("utf-8"))
    assert DatamaticsPayload.from_ison(text.encode("utf-8")) == p


def _rejects(text, field=None, code="MALFORMED_DATAMATICS", limits=None):
    with pytest.raises(IGDMError) as info:
        DatamaticsPayload.from_ison(text, **({"limits": limits} if limits else {}))
    assert (info.value.code, info.value.step) == (code, "D1"), info.value
    if field:
        assert info.value.field == field, info.value
    return info.value


def test_canonical_form_and_blocks():
    text = payload().to_ison()
    _rejects(text + "\n", "canonical_form")
    _rejects(text.replace("\n", "\r\n"), "canonical_form")
    _rejects(text.replace("cluster 1 order\nregion 1 order", "region 1 order\ncluster 1 order"), "canonical_form")
    _rejects(text + "\n\nmeta.extra\na\n1", "meta.extra")
    _rejects(text.replace("IGDM/1", "IGDM/2"), "meta.igdm.datamatics_spec")
    _rejects(text.replace("table.members", "table.memberz"), "table.memberz")
    _rejects(b"\xff", "document")


def test_bare_boolean_rejected():
    # Review Focus 1: booleans are "true"/"false" string tokens; a bare ISON boolean is malformed, never coerced.
    text = payload().to_ison()
    _rejects(text.replace('"true" document', "true document"), "table.nodes.order:1.selectable")
    _rejects(text.replace('null "false" region', "null false region"), "table.groups.region.collapsed")


def test_x_namespace_only_where_allowed():
    # Review Focus 2: x- values are legal in role-like columns only.
    def bad(field, **kw):
        with pytest.raises(IGDMError) as info:
            payload(**kw).check()
        assert (info.value.code, info.value.step, info.value.field) == ("MALFORMED_DATAMATICS", "D1", field), info.value

    payload(nodes=(NodeHints(NodeRef("order", 1), role="x-betterify-risk", shape_role="x-blob", ring="x-r", a11y_role="x-a"),) + payload().nodes[1:]).check()
    payload(edges=(EdgeHints(payload().edges[0].edge, pattern_role="x-wavy"),)).check()
    payload(layout=LayoutHints("x-hex", None, None)).check()
    bad("table.nodes.order:1.emphasis", nodes=(NodeHints(NodeRef("order", 1), emphasis="x-huge"),) + payload().nodes[1:])
    bad("table.nodes.order:1.visibility", nodes=(NodeHints(NodeRef("order", 1), visibility="x-ghost"),) + payload().nodes[1:])
    bad("table.edges.order:1-knows-order:s1#0.direction_display", edges=(EdgeHints(payload().edges[0].edge, direction_display="x-loop"),))
    bad("table.groups.region.intent", groups=(Group("region", "x-blob"), payload().groups[1]))
    bad("meta.layout.direction", layout=LayoutHints("layered", "x-diag", None))


def test_field_rules():
    def bad(field, **kw):
        with pytest.raises(IGDMError) as info:
            payload(**kw).check()
        assert (info.value.code, info.value.step, info.value.field) == ("MALFORMED_DATAMATICS", "D1", field), info.value

    n1 = payload().nodes[1]
    bad("meta.igdm.target_artifact_sha256", target_artifact_sha256="XY" * 32)
    bad("meta.layout.direction", layout=LayoutHints(None, "LR", None))
    bad("table.nodes.order:1.magnitude", nodes=(NodeHints(NodeRef("order", 1), magnitude=1.5), n1))
    bad("table.nodes.order:1.magnitude", nodes=(NodeHints(NodeRef("order", 1), magnitude=True), n1))
    bad("table.nodes.order:1.magnitude", nodes=(NodeHints(NodeRef("order", 1), magnitude="nan"), n1))
    bad("table.nodes.order:1.lod_min", nodes=(NodeHints(NodeRef("order", 1), lod_min=1025), n1))
    bad("table.nodes.order:1.lod_min", nodes=(NodeHints(NodeRef("order", 1), lod_min=-1), n1))
    bad("table.nodes.order:1.badge", nodes=(NodeHints(NodeRef("order", 1), badge="x" * 17), n1))
    bad("table.nodes.order:1.badge", nodes=(NodeHints(NodeRef("order", 1), badge="a\nb"), n1))
    bad("table.nodes.order:1.badge", nodes=(NodeHints(NodeRef("order", 1), badge="a\x7fb"), n1))        # DEL is Cc
    bad("table.nodes.order:1.badge", nodes=(NodeHints(NodeRef("order", 1), badge="a\u0085b"), n1))      # C1 control is Cc
    payload(nodes=(NodeHints(NodeRef("order", 1), badge="a b"), n1)).check()                             # a space is Zs, allowed
    bad("table.nodes.order:1.label", nodes=(NodeHints(NodeRef("order", 1), label=""), n1))
    bad("table.nodes.order:1.selectable", nodes=(NodeHints(NodeRef("order", 1), selectable="yes"), n1))
    bad("table.nodes.order:1.temporal_order", nodes=(NodeHints(NodeRef("order", 1), temporal_order=-1), n1))
    bad("table.nodes.order:9223372036854775808.node_id", nodes=(NodeHints(NodeRef("order", 2**63), role="active"), n1))   # key is the address as written
    bad("table.nodes.a:b:1.node_type", nodes=(NodeHints(NodeRef("a:b", 1), role="active"), n1))
    bad("table.nodes.order:1.0.node_id", nodes=(NodeHints(NodeRef("order", 1.0), role="active"), n1))
    bad("table.edges.order:1-knows-order:s1#01.ordinal", edges=(EdgeHints(EdgeAddress(NodeRef("order", 1), "knows", NodeRef("order", "s1"), "01"), role="neutral"),))
    bad("table.groups.-g.group_id", groups=(Group("-g", "hull"),) + payload().groups)
    bad("table.groups.region.lod_min", groups=(Group("region", "hull", lod_min=2000), payload().groups[1]))
    bad("table.members.region/a b:1.node_type", members=(payload().members[0], Member("region", NodeRef("a b", 1)), payload().members[2]))


def test_budgets():
    text = payload().to_ison()
    assert _rejects(text, code="DATAMATICS_LIMIT_EXCEEDED", limits=Limits(max_payload_bytes=8)).field == "max_payload_bytes"
    assert _rejects(text, code="DATAMATICS_LIMIT_EXCEEDED", limits=Limits(max_rows_per_table=2)).field == "max_rows_per_table"

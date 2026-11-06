from isongraph_ext.igdm import records as R
from isongraph_ext.igdm.errors import IGDMError
from isongraph_ext.igpv.records import EdgeAddress, NodeRef


def test_error_shape():
    e = IGDMError("MALFORMED_DATAMATICS", "table.nodes.p:1.role", "bad", "D1")
    assert str(e) == "D1 MALFORMED_DATAMATICS table.nodes.p:1.role: bad" and (e.code, e.step) == ("MALFORMED_DATAMATICS", "D1")


def test_vocabularies_and_grammars():
    assert "emphasis-high" in R.ROLES and "document" in R.SHAPE_ROLES and "double" in R.PATTERN_ROLES
    assert R.X_TOKEN.fullmatch("x-betterify-risk") and not R.X_TOKEN.fullmatch("X-Bad") and not R.X_TOKEN.fullmatch("x-") and not R.X_TOKEN.fullmatch("x-a\n")
    assert (R.LOD_MAX, R.BADGE_MAX) == (1024, 16)
    assert R.NODE_FIELDS[:2] == ("node_type", "node_id") and R.EDGE_FIELDS[:6] == ("source_type", "source_id", "relation", "target_type", "target_id", "ordinal")
    assert "selectable" in R.NODE_HINTS and "ordinal" not in R.EDGE_HINTS
    assert R.BOOL_COLUMNS == {"selectable", "focusable", "expandable", "drilldown", "layout_anchor", "collapsed"}
    assert (R.DATAMATICS_SPEC, R.CAPABILITY, R.CAPABILITY_VERSION, R.CAPABILITY_RANGE) == ("IGDM/1", "igdm", "1.0.0", "^1")


def test_records_defaults_and_limits():
    n = R.NodeHints(NodeRef("p", 1))
    assert n.role is None and n.selectable is None and R.EdgeHints(EdgeAddress(NodeRef("p", 1), "r", NodeRef("p", 2))).lod_min is None
    assert R.Group("g", "hull").parent_group_id is None and R.Member("g", NodeRef("p", 1)).group_id == "g"
    assert R.LayoutHints() == R.LayoutHints(None, None, None)
    lim = R.DEFAULT_LIMITS
    assert (lim.max_payload_bytes, lim.max_graph_bytes, lim.max_rows_per_table, lim.max_group_depth) == (64 * 2**20, 256 * 2**20, 1_048_576, 64)

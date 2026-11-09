from igp_helpers import pol

from isongraph_ext.igp import DEFAULT_LIMITS, IGP_IMPLEMENTATION_VERSION, IGP_SPEC, IGPError, Limits
from isongraph_ext.igpv import DEFAULT_LIMITS as IGPV_LIMITS


def test_constants_limits_and_error_shape():
    assert (IGP_SPEC, IGP_IMPLEMENTATION_VERSION) == ("IGP/1", "1.0.0")
    assert (DEFAULT_LIMITS.max_policy_bytes, DEFAULT_LIMITS.max_source_bytes) == (16 * 2**20, 256 * 2**20)
    assert (DEFAULT_LIMITS.max_rows_per_table, DEFAULT_LIMITS.max_depth) == (1_048_576, 1_048_576) and DEFAULT_LIMITS.lineage == IGPV_LIMITS
    assert Limits(max_policy_bytes=1).max_source_bytes == DEFAULT_LIMITS.max_source_bytes
    e = IGPError("POLICY_MALFORMED", "table.anchors", "at least one anchor required", "Q0")
    assert str(e) == "Q0 POLICY_MALFORMED table.anchors: at least one anchor required" and (e.code, e.field, e.step) == ("POLICY_MALFORMED", "table.anchors", "Q0")


def test_policy_records_are_held_in_canonical_order_and_frozen():
    import dataclasses

    import pytest
    p = pol(("p", "b"), ("p", 2), ("a", "z"), node_types=("zeta", "alpha"), relations=("s", "r"))
    assert [(a.node_type, a.node_id) for a in p.anchors] == [("a", "z"), ("p", 2), ("p", "b")]        # type, then INT64 before STRING
    assert p.node_types == ("alpha", "zeta") and p.relations == ("r", "s")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.depth = 5

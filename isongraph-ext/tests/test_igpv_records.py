from isongraph_ext.igpv import records as R
from isongraph_ext.igpv.errors import IGPVError


def test_error_shape_matches_igx():
    e = IGPVError("MALFORMED_PROVENANCE", "table.objects.n1.node_id", "float", "P1")
    assert str(e) == "P1 MALFORMED_PROVENANCE table.objects.n1.node_id: float"
    assert (e.code, e.field, e.detail, e.step) == ("MALFORMED_PROVENANCE", "table.objects.n1.node_id", "float", "P1")


def test_grammars_use_fullmatch_semantics():
    assert R.KEY_TOKEN.fullmatch("a") and R.KEY_TOKEN.fullmatch("A0._-" + "x" * 59)
    assert not R.KEY_TOKEN.fullmatch("-a") and not R.KEY_TOKEN.fullmatch("a" * 65) and not R.KEY_TOKEN.fullmatch("a\n")
    assert R.ORDINAL.fullmatch("0") and R.ORDINAL.fullmatch("10") and not R.ORDINAL.fullmatch("01") and not R.ORDINAL.fullmatch("-1")
    assert R.X_LOCATOR.fullmatch("x-pdf-page/1") and not R.X_LOCATOR.fullmatch("x-pdf-page/0") and not R.X_LOCATOR.fullmatch("bytes/1")
    assert R.MEDIA_TYPE.fullmatch("text/markdown") and not R.MEDIA_TYPE.fullmatch("text")
    assert R.is_identifier("knows") and not R.is_identifier("a:b") and not R.is_identifier("a b") and not R.is_identifier("") and not R.is_identifier('a"b')
    assert R.is_int(1) and not R.is_int(True) and not R.is_int(1.0) and R.is_str("1") and not R.is_str(1)


def test_records_are_frozen_and_defaults_match_spec():
    import dataclasses
    import pytest
    lim = R.DEFAULT_LIMITS
    assert (lim.max_payload_bytes, lim.max_graph_bytes, lim.max_sources_bytes) == (64 * 2**20, 256 * 2**20, 2**30)
    assert (lim.max_rows_per_table, lim.max_lineage_depth, lim.max_lineage_visits) == (1_048_576, 64, 1_048_576)
    ref = R.NodeRef("p", 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.node_id = 2
    assert R.EdgeAddress(ref, "knows", R.NodeRef("p", "s1")).ordinal == "0"
    assert hash(R.EdgeAddress(ref, "knows", ref)) == hash(R.EdgeAddress(ref, "knows", ref))
    assert (R.PROVENANCE_SPEC, R.CAPABILITY, R.CAPABILITY_VERSION, R.CAPABILITY_RANGE) == ("IGPV/1", "igpv", "1.0.0", "^1")

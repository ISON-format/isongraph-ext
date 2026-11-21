# isongraph-ext/tests/test_igdc_hints.py
# isongraph-ext/tests/test_igdc_hints.py
import copy

import pytest
from ison_parser import Block, Document, dumps_canonical

from isongraph_ext.igdc.errors import IGDCError
from isongraph_ext.igdc.hints import EDGE_COLUMNS, GROUP_COLUMNS, LAYOUT_COLUMNS, MEMBER_COLUMNS, META_COLUMNS, NODE_COLUMNS, HintSet
from isongraph_ext.igdc.verify import verify_hints

SHA_P, SHA_T = "b0" * 32, "a0" * 32


def _row(cols, **kw):
    r = {c: None for c in cols}
    r.update(kw)
    return r


def doc(directed="true", multigraph="false", nodes=None, edges=None, groups=None, members=None, layout=None):
    nodes = nodes if nodes is not None else [_row(NODE_COLUMNS, node_type="n", node_id="i:1", role="active"),
                                             _row(NODE_COLUMNS, node_type="n", node_id="s:a", role_x="x-risk")]
    edges = edges if edges is not None else [_row(EDGE_COLUMNS, source_type="n", source_id="i:1", relation="r", target_type="n",
                                                  target_id="s:a", ordinal="0", pattern_role="dashed")]
    groups = groups if groups is not None else [_row(GROUP_COLUMNS, group_id="g", intent="hull", role="neutral")]
    members = members if members is not None else [_row(MEMBER_COLUMNS, group_id="g", node_type="n", node_id="i:1")]
    meta = {"consumption_spec": "IGDC/1", "address_scheme": "igs-addr/1", "igdm_payload_sha256": SHA_P, "target_artifact_sha256": SHA_T,
            "target_directed": directed, "target_multigraph": multigraph, "target_serialization_profile": "ison-v1"}
    return Document(blocks=[Block("meta", "igdc", list(META_COLUMNS), [meta]),
                            Block("meta", "layout", list(LAYOUT_COLUMNS), [layout or _row(LAYOUT_COLUMNS)]),
                            Block("table", "nodes", list(NODE_COLUMNS), nodes), Block("table", "edges", list(EDGE_COLUMNS), edges),
                            Block("table", "groups", list(GROUP_COLUMNS), groups), Block("table", "members", list(MEMBER_COLUMNS), members)])


def text(**kw) -> str:
    return dumps_canonical(doc(**kw))


def expect(code, step, **kw):
    with pytest.raises(IGDCError) as e:
        verify_hints(text(**kw))
    assert (e.value.code, e.value.step) == (code, step), e.value


def test_valid_document_round_trips_byte_for_byte():
    t = text()
    h = verify_hints(t)
    assert h.to_ison() == t and len(h.nodes) == 2 and len(h.members) == 1
    assert HintSet.from_ison(t.encode()).digest == h.digest


# ---- C0 / C1 ----
def test_noncanonical_text_rejected():
    with pytest.raises(IGDCError) as e:
        verify_hints(text().replace("\n\n", "\n\n\n", 1))
    assert (e.value.code, e.value.field, e.value.step) == ("MALFORMED_CONSUMPTION", "canonical_form", "C0")


def test_cr_rejected():
    with pytest.raises(IGDCError) as e:
        verify_hints(text().replace("\n", "\r\n"))
    assert e.value.step == "C0"


def test_unexpected_and_duplicate_blocks_rejected():
    d = doc()
    d.blocks.append(Block("table", "extra", ["a"], []))
    with pytest.raises(IGDCError) as e:
        verify_hints(dumps_canonical(d))
    assert e.value.code == "MALFORMED_CONSUMPTION"
    d = doc()
    d.blocks.append(d.blocks[-1])
    with pytest.raises(IGDCError):
        verify_hints(dumps_canonical(d))


def test_bare_boolean_rejected():
    rows = [_row(NODE_COLUMNS, node_type="n", node_id="i:1", selectable=True)]
    expect("MALFORMED_CONSUMPTION", "C1", nodes=rows, members=[])


def test_closed_value_outside_vocabulary_rejected():
    expect("MALFORMED_CONSUMPTION", "C1", nodes=[_row(NODE_COLUMNS, node_type="n", node_id="i:1", emphasis="huge")], members=[], edges=[])


def test_x_token_in_closed_column_rejected():
    expect("MALFORMED_CONSUMPTION", "C1", nodes=[_row(NODE_COLUMNS, node_type="n", node_id="i:1", role="x-risk")], members=[], edges=[])


def test_malformed_x_token_rejected():
    expect("MALFORMED_CONSUMPTION", "C1", nodes=[_row(NODE_COLUMNS, node_type="n", node_id="i:1", role_x="risk")], members=[], edges=[])


def test_closed_and_x_both_set_rejected():
    expect("MALFORMED_CONSUMPTION", "C1", nodes=[_row(NODE_COLUMNS, node_type="n", node_id="i:1", role="active", role_x="x-risk")], members=[], edges=[])


def test_layout_family_x_split():
    verify_hints(text(layout=_row(LAYOUT_COLUMNS, family_x="x-radial-ish")))
    with pytest.raises(IGDCError):
        verify_hints(text(layout=_row(LAYOUT_COLUMNS, family="x-radial-ish")))


# ---- C2 ----
@pytest.mark.parametrize("bad", ["1", "i:007", "i:-0", "i:9223372036854775808", "x:1", "i:"])
def test_untagged_or_noncanonical_id_rejected(bad):
    expect("INVALID_ADDRESS", "C2", nodes=[_row(NODE_COLUMNS, node_type="n", node_id=bad, role="active")], members=[], edges=[])


def test_twin_ids_rejected_across_tables():
    nodes = [_row(NODE_COLUMNS, node_type="n", node_id="i:7", role="active")]
    members = [_row(MEMBER_COLUMNS, group_id="g", node_type="n", node_id="s:7")]
    expect("TWIN_IDS", "C2", nodes=nodes, edges=[], members=members)


def test_s007_is_not_a_twin_of_i7():
    nodes = [_row(NODE_COLUMNS, node_type="n", node_id="i:7", role="active"), _row(NODE_COLUMNS, node_type="n", node_id="s:007", role="active")]
    verify_hints(text(nodes=nodes, edges=[], members=[]))


def test_simple_graph_ordinal_must_be_zero_and_ordinal_canonical():
    e = [_row(EDGE_COLUMNS, source_type="n", source_id="i:1", relation="r", target_type="n", target_id="i:2", ordinal="1", role="neutral")]
    expect("INVALID_ADDRESS", "C2", edges=e, nodes=[], members=[])
    verify_hints(text(edges=e, nodes=[], members=[], multigraph="true"))
    for bad in ("01", "-1", ""):
        e2 = [dict(e[0], ordinal=bad)]
        expect("INVALID_ADDRESS", "C2", edges=e2, nodes=[], members=[], multigraph="true")


def test_undirected_endpoints_must_be_canonical():
    e = [_row(EDGE_COLUMNS, source_type="n", source_id="s:a", relation="r", target_type="n", target_id="i:5", ordinal="0", role="neutral")]
    expect("INVALID_ADDRESS", "C2", edges=e, nodes=[], members=[], directed="false")
    verify_hints(text(edges=e, nodes=[], members=[], directed="true"))   # the same row is fine in a directed graph


def test_duplicate_node_rows_rejected():
    n = _row(NODE_COLUMNS, node_type="n", node_id="i:1", role="active")
    expect("INVALID_ADDRESS", "C2", nodes=[n, dict(n, label="x")], edges=[], members=[])


# ---- C3 ----
def test_unknown_parent_and_member_group_rejected():
    expect("UNRESOLVED_REFERENCE", "C3", groups=[_row(GROUP_COLUMNS, group_id="g", intent="hull", parent_group_id="nope")], members=[])
    expect("UNRESOLVED_REFERENCE", "C3", members=[_row(MEMBER_COLUMNS, group_id="nope", node_type="n", node_id="i:1")])


def test_group_cycle_rejected():
    g = [_row(GROUP_COLUMNS, group_id="a", intent="hull", parent_group_id="b"), _row(GROUP_COLUMNS, group_id="b", intent="hull", parent_group_id="a")]
    expect("GROUP_CYCLE", "C3", groups=g, members=[])


def test_group_depth_budget_is_iterative():
    from isongraph_ext.igdm.records import Limits
    chain = [_row(GROUP_COLUMNS, group_id=f"g{i}", intent="hull", parent_group_id=None if i == 0 else f"g{i-1}") for i in range(2000)]
    with pytest.raises(IGDCError) as e:      # a long acyclic chain: a limit error, never RecursionError
        verify_hints(text(groups=chain, members=[]), limits=Limits(max_group_depth=64))
    assert e.value.code == "DATAMATICS_LIMIT_EXCEEDED"


# ---- rev 2 (finding F3): repeated declarations, unconsumed rows, byte budget ------------------------------------------
from isongraph_ext.igdm.records import Limits  # noqa: E402

_ALL_BLOCKS = [(b.kind, b.name, c) for b in doc().blocks for c in b.fields]


@pytest.mark.parametrize("kind,name,col", _ALL_BLOCKS, ids=lambda v: str(v))
def test_no_column_can_be_declared_twice(kind, name, col):
    d = doc()
    block = next(b for b in d.blocks if (b.kind, b.name) == (kind, name))
    block.fields.append(col)                                   # the writer emits it as a canonical-looking repeated header
    t = dumps_canonical(d)
    with pytest.raises(IGDCError) as e:
        verify_hints(t)
    assert (e.value.code, e.value.step) == ("MALFORMED_CONSUMPTION", "C1"), e.value
    assert e.value.field.endswith(col), e.value


def test_summary_typed_computed_and_reference_cells_are_refused():
    t = text()
    with pytest.raises(IGDCError):
        verify_hints(t + "\n---\nrows 2")
    head, body = t.split("table.groups\n", 1)
    for decl in ("group_id:int", "group_id:computed"):
        with pytest.raises(IGDCError) as e:
            verify_hints(head + "table.groups\n" + body.replace("group_id", decl, 1))
        assert e.value.code == "MALFORMED_CONSUMPTION"
    with pytest.raises(IGDCError):
        verify_hints(t.replace("i:1 n\n", ":user:1 n\n", 1))


def test_meta_blocks_with_an_extra_row_are_refused():
    d = doc()
    meta = next(b for b in d.blocks if b.name == "igdc")
    meta.rows.append(dict(meta.rows[0]))
    with pytest.raises(IGDCError) as e:
        verify_hints(dumps_canonical(d))
    assert (e.value.code, e.value.step) == ("MALFORMED_CONSUMPTION", "C1")


def test_byte_budget_is_applied_before_parsing():
    with pytest.raises(IGDCError) as e:
        verify_hints(b"\xff" * 64, limits=Limits(max_payload_bytes=10))     # not UTF-8, but never decoded: the budget wins
    assert (e.value.code, e.value.field, e.value.step) == ("DATAMATICS_LIMIT_EXCEEDED", "max_payload_bytes", "C0")


def test_row_budget():
    with pytest.raises(IGDCError) as e:
        verify_hints(text(), limits=Limits(max_rows_per_table=1))
    assert (e.value.code, e.value.field, e.value.step) == ("DATAMATICS_LIMIT_EXCEEDED", "max_rows_per_table", "C1")


def test_int64_hint_values_survive_exactly():
    big = 9007199254740993                                      # 2**53 + 1: a JavaScript Number cannot hold it
    n = [_row(NODE_COLUMNS, node_type="n", node_id="i:9007199254740993", temporal_order=big, layout_rank=2**63 - 1)]
    h = verify_hints(text(nodes=n, edges=[], members=[]))
    assert h.nodes[0]["temporal_order"] == big and h.nodes[0]["node_id"] == "i:9007199254740993"


# ---- C2 diagnostic fields follow the row-key form `table.<block>.<row key>.<column>` (26 section 4) -------------------------
def _c2_field(**kw):
    with pytest.raises(IGDCError) as e:
        verify_hints(text(**kw))
    assert (e.value.code, e.value.step) == ("INVALID_ADDRESS", "C2"), e.value
    return e.value.field


def test_c2_node_type_field_is_a_row_path():
    n = [_row(NODE_COLUMNS, node_type="a b", node_id="i:1", role="active")]
    assert _c2_field(nodes=n, edges=[], members=[]) == "table.nodes.a b:i:1.node_type"


def test_c2_edge_fields_are_row_paths():
    row = "table.edges.n:i:1/r/n:i:2/{}"
    e = [_row(EDGE_COLUMNS, source_type="n", source_id="i:1", relation="r", target_type="n", target_id="i:2", ordinal="1", role="neutral")]
    assert _c2_field(edges=e, nodes=[], members=[]) == row.format("1") + ".ordinal"                       # simple graph, ordinal 1
    bad = [dict(e[0], ordinal="01")]
    assert _c2_field(edges=bad, nodes=[], members=[], multigraph="true") == row.format("01") + ".ordinal"
    rel = [dict(e[0], relation="a b", ordinal="0")]
    assert _c2_field(edges=rel, nodes=[], members=[]) == "table.edges.n:i:1/a b/n:i:2/0.relation"
    und = [_row(EDGE_COLUMNS, source_type="n", source_id="s:a", relation="r", target_type="n", target_id="i:5", ordinal="0", role="neutral")]
    assert _c2_field(edges=und, nodes=[], members=[], directed="false") == "table.edges.n:s:a/r/n:i:5/0.source_id"


def test_c2_member_node_type_field_is_a_row_path():
    m = [_row(MEMBER_COLUMNS, group_id="g", node_type="a b", node_id="i:1")]
    assert _c2_field(nodes=[], edges=[], members=m) == "table.members.g/a b:i:1.node_type"

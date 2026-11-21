# isongraph-ext/tests/test_igdc_address.py
import pytest

from isongraph_ext.igdc.address import TypedNode, edge_address, node_address, parse_id, semantic_key, tag_id
from isongraph_ext.igdc.errors import IGDCError
from isongraph_ext.igpv.records import EdgeAddress, NodeRef

I64_MIN, I64_MAX = -(2**63), 2**63 - 1


@pytest.mark.parametrize("value,tag", [
    (7, "i:7"), ("7", "s:7"), ("007", "s:007"), ("-0", "s:-0"), ("1e3", "s:1e3"), ("+5", "s:+5"),
    (0, "i:0"), (-1, "i:-1"), (I64_MIN, f"i:{I64_MIN}"), (I64_MAX, f"i:{I64_MAX}"),
    ("", "s:"), ("é", "s:é"), ("e\u0301", "s:e\u0301"), ("😀", "s:😀"),
])
def test_tag_id(value, tag):
    assert tag_id(value) == tag
    assert parse_id(tag) == value and type(parse_id(tag)) is type(value)


def test_string_that_looks_tagged():
    assert tag_id("i:7") == "s:i:7" and parse_id("s:i:7") == "i:7"
    assert tag_id("s:7") == "s:s:7" and parse_id("s:s:7") == "s:7"
    assert tag_id(7) != tag_id("7")


@pytest.mark.parametrize("bad", [True, False, 1.5, None, I64_MAX + 1, I64_MIN - 1, b"7", "\ud800"])
def test_tag_id_rejects_non_ids(bad):
    with pytest.raises(IGDCError) as e:
        tag_id(bad)
    assert (e.value.code, e.value.step) == ("INVALID_ADDRESS", "C2")


@pytest.mark.parametrize("bad", ["7", "i:007", "i:-0", "i:+5", "i:", "i:1.0", "i: 7", "i:7 ", "x:7", "", "s", "i",
                                 f"i:{I64_MAX + 1}", f"i:{I64_MIN - 1}", "i:\u0663", None, 7])
def test_parse_id_rejects(bad):
    with pytest.raises(IGDCError) as e:
        parse_id(bad)
    assert e.value.code == "INVALID_ADDRESS"


def test_semantic_order():
    ids = [(t, v) for t in ("b", "a") for v in (10, 2, -1, 0, "é", "a", "~", "😀")]
    tagged = [(t, tag_id(v)) for t, v in ids]
    by_semantic = sorted(tagged, key=lambda x: semantic_key(*x))
    # type bytes first; within a type every INT64 precedes every STRING; ints numeric; strings by UTF-8 bytes
    assert by_semantic[:8] == [("a", f) for f in ("i:-1", "i:0", "i:2", "i:10", "s:a", "s:~", "s:é", "s:😀")]
    # as plain text 'i:10' sorts before 'i:2': the two orders differ, which is why file order is never semantic order
    assert sorted(["i:2", "i:10"]) == ["i:10", "i:2"] and sorted(["i:2", "i:10"], key=lambda t: semantic_key("a", t)) == ["i:2", "i:10"]


def test_utf8_byte_order_not_utf16():
    # U+FF5E (BMP) sorts after U+1F600 in UTF-16 but before it in UTF-8 (IGS/1 hazard section 5.5)
    assert semantic_key("a", "s:\uff5e") < semantic_key("a", "s:\U0001f600")


def test_node_address():
    assert node_address(NodeRef("order", 7)) == TypedNode("order", "i:7")
    assert node_address(NodeRef("order", "7")) == TypedNode("order", "s:7")


@pytest.mark.parametrize("t", ["", "a b", "a:b", "a|b", 'a"b', "a\\b"])
def test_node_type_must_be_identifier(t):
    with pytest.raises(IGDCError) as e:
        node_address(NodeRef(t, 1))
    assert e.value.code == "INVALID_ADDRESS"


def _edge(a, b, rel="knows", ordinal="0"):
    return EdgeAddress(NodeRef("n", a), rel, NodeRef("n", b), ordinal)


def test_edge_directed_keeps_endpoints_as_written():
    e = edge_address(_edge(9, 1), directed=True, multigraph=False)
    assert (e.source.node_id, e.target.node_id, e.ordinal) == ("i:9", "i:1", "0")


def test_edge_undirected_requires_canonical_order_int_before_string():
    ok = edge_address(_edge(5, "a"), directed=False, multigraph=False)
    assert (ok.source.node_id, ok.target.node_id) == ("i:5", "s:a")
    with pytest.raises(IGDCError) as e:
        edge_address(_edge("a", 5), directed=False, multigraph=False)
    assert e.value.code == "INVALID_ADDRESS"
    edge_address(_edge(3, 3), directed=False, multigraph=False)          # a self-loop is one edge


@pytest.mark.parametrize("ordinal,multigraph,ok", [("0", False, True), ("1", False, False), ("0", True, True), ("1", True, True),
                                                   ("10", True, True), ("01", True, False), ("-1", True, False), ("", True, False)])
def test_ordinals(ordinal, multigraph, ok):
    if ok:
        assert edge_address(_edge(1, 2, ordinal=ordinal), directed=True, multigraph=multigraph).ordinal == ordinal
    else:
        with pytest.raises(IGDCError):
            edge_address(_edge(1, 2, ordinal=ordinal), directed=True, multigraph=multigraph)

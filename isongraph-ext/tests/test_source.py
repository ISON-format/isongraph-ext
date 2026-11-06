from conftest import graph_bytes

from isongraph_ext.igx.source import as_bytes, classify_eligibility, derive_canonical


def test_as_bytes_keeps_str_exactly():
    assert as_bytes("a\r\n") == b"a\r\n" and as_bytes(b"x") == b"x"


def test_python_canonical_true():
    assert derive_canonical(graph_bytes("ids/positive-int.ison"), "ison-v1", "python") == "true"


def test_python_without_trailing_newline_is_still_canonical():
    assert derive_canonical(graph_bytes("ids/positive-int.ison").rstrip(b"\n"), "ison-v1", "python") == "true"


def test_non_python_is_unverified_even_when_canonical():
    assert derive_canonical(graph_bytes("ids/positive-int.ison"), "ison-v1", "ts") == "unverified"


def test_python_noncanonical_order_is_false():
    assert derive_canonical(graph_bytes("serialization/non-canonical-order.ison"), "ison-v1", "python") == "false"


def test_derive_canonical_crlf_is_false():
    # Review Focus 2
    crlf = graph_bytes("ids/positive-int.ison").replace(b"\n", b"\r\n")
    assert derive_canonical(crlf, "ison-v1", "python") == "false"


def test_profile_mismatch_derives_false():
    # Review Focus 5: ISON bytes declared as isonl-v1, and ISONL bytes declared as ison-v1.
    assert derive_canonical(graph_bytes("ids/positive-int.ison"), "isonl-v1", "python") == "false"
    assert derive_canonical(graph_bytes("serialization/negative-int.isonl"), "ison-v1", "python") == "false"


def test_isonl_profile_true():
    assert derive_canonical(graph_bytes("serialization/negative-int.isonl"), "isonl-v1", "python") == "true"


def test_multigraph_document_uses_multigraph_loader():
    assert derive_canonical(graph_bytes("structure/multigraph-document.ison"), "ison-v1", "python") == "true"


def test_garbage_is_false_for_python():
    assert derive_canonical(b"\xff\xfe", "ison-v1", "python") == "false"
    assert derive_canonical(b"not ison :::", "ison-v1", "python") == "false"


def test_eligible():
    assert classify_eligibility(graph_bytes("ids/positive-int.ison"), "ison-v1") == ("eligible", None)
    assert classify_eligibility(graph_bytes("serialization/negative-int.isonl"), "isonl-v1") == ("eligible", None)


def test_lossy_domain_is_still_eligible():
    # 1.0 vs 1 is a consumer-fidelity concern (TS/JS), not a Semantic/2 domain violation (17 §4.1).
    assert classify_eligibility(graph_bytes("values/int-vs-integral-float.ison"), "ison-v1") == ("eligible", None)


def test_integer_value_beyond_int64_is_ineligible():
    assert classify_eligibility(graph_bytes("values/int-beyond-int64.ison"), "ison-v1") == ("ineligible", "INTEGER_OUT_OF_INT64")


def test_node_id_beyond_int64_is_ineligible():
    text = b"nodes.p\nid\n9223372036854775808\n"
    assert classify_eligibility(text, "ison-v1") == ("ineligible", "INTEGER_OUT_OF_INT64")


def test_int64_extremes_are_eligible():
    text = b"nodes.p\nid x\n-9223372036854775808 9223372036854775807\n"
    assert classify_eligibility(text, "ison-v1") == ("eligible", None)


def test_edge_property_beyond_int64_is_ineligible():
    text = b"edges.R\nsource target w\n:p:1 :p:2 100000000000000000000\n\nnodes.p\nid\n1\n2\n"
    assert classify_eligibility(text, "ison-v1") == ("ineligible", "INTEGER_OUT_OF_INT64")


def test_multigraph_is_ineligible_before_anything_else():
    assert classify_eligibility(graph_bytes("structure/multigraph-document.ison"), "ison-v1") == ("ineligible", "MULTIGRAPH_DOCUMENT")


def test_unloadable_is_unclassified():
    assert classify_eligibility(b"\xff\xfe", "ison-v1") == ("unclassified", None)
    assert classify_eligibility(graph_bytes("ids/positive-int.ison"), "isonl-v1") in (("unclassified", None), ("eligible", None))


def test_bools_are_not_integers():
    text = b"nodes.p\nid flag\n1 true\n"
    assert classify_eligibility(text, "ison-v1") == ("eligible", None)

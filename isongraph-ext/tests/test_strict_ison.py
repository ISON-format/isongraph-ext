"""The shared strict reader: every silent-loss path that ison-py 1.2.0 accepts must be refused (rev 2 finding F3)."""
import pytest
from ison_parser import Block, Document, dumps_canonical

from isongraph_ext.strict_ison import BlockShape, StrictError, read_canonical

SHAPES = (BlockShape("meta", "m", ("a", "b"), single_row=True), BlockShape("table", "t", ("x", "y")))
BIG = 1 << 20


def good() -> str:
    return dumps_canonical(Document(blocks=[Block("meta", "m", ["a", "b"], [{"a": 1, "b": "two"}]),
                                            Block("table", "t", ["x", "y"], [{"x": 1, "y": None}, {"x": 2, "y": "q"}])]))


def read(text, **kw):
    return read_canonical(text, SHAPES, max_bytes=kw.pop("max_bytes", BIG), max_rows=kw.pop("max_rows", 100))


def refused(text, stage, kind="malformed", field=None, **kw):
    with pytest.raises(StrictError) as e:
        read(text, **kw)
    assert (e.value.stage, e.value.kind) == (stage, kind), e.value
    if field is not None:
        assert e.value.field == field, e.value
    return e.value


def test_good_document_is_returned_with_its_rows():
    text, blocks = read(good())
    assert text == good() and blocks[("meta", "m")] == [{"a": 1, "b": "two"}] and len(blocks[("table", "t")]) == 2
    assert read(good().encode())[0] == good()


# ---- bytes stage -------------------------------------------------------------------------------------------------
def test_budget_is_checked_before_anything_is_parsed():
    junk = b"\xff" * 64                                       # would be a UTF-8 error if it were decoded first
    e = refused(junk, "bytes", "limit", "size", max_bytes=10)
    assert "64" in e.detail


def test_non_utf8_cr_bom_and_noncanonical():
    refused(b"\xff\xfe", "bytes", field="document")
    refused(good().replace("\n", "\r\n"), "bytes", field="canonical_form")
    refused("﻿" + good(), "bytes", field="canonical_form")
    refused(good().replace("\n\n", "\n\n\n", 1), "bytes", field="canonical_form")
    refused("table.t\nx y\n1 2 3\n", "bytes", field="document")          # row wider than its header: a parse error


def test_non_bytes_input_is_a_programmer_error():
    with pytest.raises(TypeError):
        read(None)


# ---- shape stage: the silent-loss cases ---------------------------------------------------------------------------
def doc_with(**table):
    """A canonical document whose table block is built by hand so it can carry what a real writer input would not."""
    return dumps_canonical(Document(blocks=[Block("meta", "m", ["a", "b"], [{"a": 1, "b": "two"}]),
                                            Block("table", "t", table["fields"], table["rows"])]))


def test_repeated_column_declaration_is_refused_even_when_it_is_canonical():
    text = doc_with(fields=["x", "x", "y"], rows=[{"x": 5, "y": None}])
    assert "x x y" in text                                    # the writer happily emits it: C0/R0 alone would pass this
    refused(text, "shape", field="table.t.x")


def test_repeated_column_cannot_overwrite_a_value_silently():
    # last-wins in the parsed row: the first cell (1) would be lost; the reader must refuse before anyone can read 3
    refused("table.t\nx y x\n1 2 3\n", "bytes")               # not canonical (fields unsorted) ...
    refused(doc_with(fields=["x", "x", "y"], rows=[{"x": 3, "y": 2}]), "shape", field="table.t.x")   # ... and canonical


@pytest.mark.parametrize("fields", [["x"], ["x", "y", "z"], ["x", "z"]])
def test_missing_or_unexpected_columns_refused(fields):
    refused(doc_with(fields=fields, rows=[]), "shape")


def test_proto_named_column_is_just_an_unexpected_column():
    refused(doc_with(fields=["__proto__", "x", "y"], rows=[]), "shape")


def test_summary_row_refused():
    text = good() + "\n---\nsum 3"
    refused(text, "shape")


def test_typed_and_computed_column_declarations_refused():
    for decl in ("x:int", "x:computed"):
        t = good().replace("table.t\nx y", f"table.t\n{decl} y")
        refused(t, "shape")


def test_reference_cell_refused():
    t = good().replace("\n2 q", "\n:7 q")
    assert ":7" in t
    refused(t, "shape")


def test_short_row_is_padded_by_the_parser_so_only_reemission_catches_it():
    t = good().replace("\n2 q", "\n2")
    refused(t, "bytes", field="canonical_form")


def test_missing_unexpected_duplicate_wrong_kind_blocks():
    d = Document(blocks=[Block("meta", "m", ["a", "b"], [{"a": 1, "b": 2}])])
    refused(dumps_canonical(d), "shape", field="table.t")                       # missing
    d2 = Document(blocks=[Block("meta", "m", ["a", "b"], [{"a": 1, "b": 2}]), Block("table", "t", ["x", "y"], []), Block("table", "extra", ["q"], [])])
    refused(dumps_canonical(d2), "shape", field="table.extra")                  # unexpected
    d3 = Document(blocks=[Block("meta", "m", ["a", "b"], [{"a": 1, "b": 2}]), Block("meta", "m", ["a", "b"], [{"a": 1, "b": 2}]), Block("table", "t", ["x", "y"], [])])
    refused(dumps_canonical(d3), "shape", field="meta.m")                       # duplicate
    d4 = Document(blocks=[Block("table", "m", ["a", "b"], [{"a": 1, "b": 2}]), Block("table", "t", ["x", "y"], [])])
    refused(dumps_canonical(d4), "shape")                                       # a table where a meta block must be


def test_meta_block_needs_exactly_one_row():
    for rows in ([], [{"a": 1, "b": 2}, {"a": 3, "b": 4}]):
        d = Document(blocks=[Block("meta", "m", ["a", "b"], rows), Block("table", "t", ["x", "y"], [])])
        refused(dumps_canonical(d), "shape")


def test_row_budget_is_a_limit_not_a_malformed_document():
    e = refused(good(), "shape", "limit", "max_rows_per_table", max_rows=1)
    assert "table.t" in e.detail


def test_float_cells_must_be_finite():
    d = Document(blocks=[Block("meta", "m", ["a", "b"], [{"a": float("inf"), "b": 1}]), Block("table", "t", ["x", "y"], [])])
    with pytest.raises(StrictError):
        read(dumps_canonical(d))

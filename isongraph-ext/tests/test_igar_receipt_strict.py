# isongraph-ext/tests/test_igar_receipt_strict.py
"""IGAR/1 receipts through the strict reader (rev 2 finding F3): no repeated declaration, summary, typed column,
reference cell or oversize input may produce a valid receipt; budgets apply before parsing."""
import pytest
from igar_helpers import verified
from ison_parser import dumps_canonical

from isongraph_ext.igar.errors import IGARError
from isongraph_ext.igar.receipt import Receipt
from isongraph_ext.igdm.records import Limits

_ALL = [(b.kind, b.name, c) for b in verified().to_document().blocks for c in b.fields]


def codes(fn, *a, **k):
    with pytest.raises(IGARError) as e:
        fn(*a, **k)
    return e.value.code, e.value.step


@pytest.mark.parametrize("kind,name,col", _ALL, ids=lambda v: str(v))
def test_no_receipt_column_can_be_declared_twice(kind, name, col):
    d = verified().to_document()
    next(b for b in d.blocks if (b.kind, b.name) == (kind, name)).fields.append(col)       # a canonical-looking repeated header
    with pytest.raises(IGARError) as e:
        Receipt.from_ison(dumps_canonical(d))
    assert (e.value.code, e.value.step) == ("MALFORMED_RECEIPT", "R1"), e.value
    assert e.value.field.endswith(col)


def test_summary_typed_computed_and_reference_cells_refused():
    t = verified().to_ison()
    assert codes(Receipt.from_ison, t + "\n---\nrows 1") == ("MALFORMED_RECEIPT", "R1")
    assert codes(Receipt.from_ison, t.replace("receipt_spec", "receipt_spec:int", 1)) == ("MALFORMED_RECEIPT", "R1")
    assert codes(Receipt.from_ison, t.replace("receipt_spec", "receipt_spec:computed", 1)) == ("MALFORMED_RECEIPT", "R1")
    assert codes(Receipt.from_ison, t.replace("IGAR/1", ":igar:1", 1)) == ("MALFORMED_RECEIPT", "R1")


def test_meta_block_extra_row_refused():
    d = verified().to_document()
    b = next(b for b in d.blocks if b.name == "failure")
    b.rows.append(dict(b.rows[0]))
    assert codes(Receipt.from_ison, dumps_canonical(d)) == ("MALFORMED_RECEIPT", "R1")


def test_byte_budget_applies_before_parsing_and_bom_is_refused():
    assert codes(Receipt.from_ison, b"\xff" * 64) == ("MALFORMED_RECEIPT", "R0")              # default budget: decoded, not UTF-8
    with pytest.raises(IGARError) as e:
        Receipt.from_ison(b"\xff" * 64, limits=Limits(max_payload_bytes=10))                   # never decoded: the budget wins
    assert (e.value.code, e.value.field, e.value.step) == ("RECEIPT_LIMIT_EXCEEDED", "max_payload_bytes", "R0")
    assert codes(Receipt.from_ison, "\ufeff" + verified().to_ison()) == ("MALFORMED_RECEIPT", "R0")


def test_row_budget():
    r = verified(unrecognized=("nodes.role:x-a", "nodes.role:x-b"))
    with pytest.raises(IGARError) as e:
        Receipt.from_ison(r.to_ison(), limits=Limits(max_rows_per_table=1))
    assert (e.value.code, e.value.field, e.value.step) == ("RECEIPT_LIMIT_EXCEEDED", "max_rows_per_table", "R1")

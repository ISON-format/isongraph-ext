# isongraph-ext/tests/test_vectors_igdc.py   (address part)
"""Runner for vectors/igs-addr (26 §5). Every table is executed; a row whose kind the runner does not know FAILS (no silent skip)."""
import hashlib
from collections import defaultdict

import pytest
from conftest import ROOT
from ison_parser import loads

from isongraph_ext.igdc.address import TwinGuard, TypedEdge, TypedNode, edge_address, edge_semantic_key, node_address, parse_id, semantic_key, tag_id
from isongraph_ext.igdc.errors import IGDCError
from isongraph_ext.igpv.records import EdgeAddress, NodeRef

ADDR = ROOT / "vectors" / "igs-addr"
TABLE_COUNTS = {"vectors": 71, "edges": 19, "order": 33, "edge_order": 11, "twins": 8}     # the claim a port makes: ALL of these rows pass


def lit(s: str):
    """Typed literal -> Python value; the TYPE is stated, never inferred from the digits."""
    kind, _, rest = s.partition(":")
    if kind == "int":
        return int(rest)
    if kind == "str":
        return rest
    if kind == "bool":
        return rest == "true"
    if kind == "float":
        return float(rest)
    if kind == "null":
        return None
    if kind == "surrogate":
        return chr(int(rest, 16))
    if kind == "tagged":
        return rest
    if kind == "tagged-lone":
        return "s:" + chr(int(rest, 16))
    raise AssertionError(f"unknown typed literal {s!r}")


def tables():
    doc = loads((ADDR / "manifest.ison").read_text(encoding="utf-8"))
    return {b.name: b.rows for b in doc.blocks if b.kind == "table"}


T = tables()


def expect_reject(fn, code, *a, **k):
    with pytest.raises(IGDCError) as e:
        fn(*a, **k)
    assert (e.value.code, e.value.step) == (code, "C2"), e.value


def test_manifest_counts_and_checksums():
    assert {name: len(rows) for name, rows in T.items()} == TABLE_COUNTS
    for line in (ADDR / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        assert hashlib.sha256((ADDR / name).read_bytes()).hexdigest() == digest, name
    assert not [n for n in ("manifest.ison", "README.md") if not (ADDR / n).exists()]


def test_vector_ids_are_unique_within_each_table_that_has_one_row_per_id():
    for name in ("vectors", "edges", "twins"):
        ids = [r["id"] for r in T[name]]
        assert len(ids) == len(set(ids)), name


@pytest.mark.parametrize("row", T["vectors"], ids=lambda r: r["id"])
def test_vectors_table(row):
    kind, expect = row["kind"], row["expect"]
    if kind == "tag":
        if expect.startswith("reject:"):
            expect_reject(tag_id, expect.removeprefix("reject:"), lit(row["input"]))
        else:
            v = lit(row["input"])
            assert tag_id(v) == expect
            assert parse_id(expect) == v and type(parse_id(expect)) is type(v)           # lossless, and the type comes back
    elif kind == "parse":
        if expect.startswith("reject:"):
            expect_reject(parse_id, expect.removeprefix("reject:"), lit(row["input"]))
        else:
            got, want = parse_id(lit(row["input"])), lit(expect)
            assert got == want and type(got) is type(want)
    elif kind in ("node_type", "relation"):
        v = lit(row["input"])
        ref = NodeRef(v, 1) if kind == "node_type" else None
        call = (lambda: node_address(ref)) if kind == "node_type" else (lambda: edge_address(EdgeAddress(NodeRef("t", 1), v, NodeRef("t", 2), "0"), directed=True, multigraph=False))
        if expect == "ok":
            call()
        else:
            expect_reject(call, expect.removeprefix("reject:"))
    else:
        pytest.fail(f"unknown kind {kind!r}")


@pytest.mark.parametrize("row", T["edges"], ids=lambda r: r["id"])
def test_edges_table(row):
    e = EdgeAddress(NodeRef(row["source_type"], lit(row["source_id"])), row["relation"], NodeRef(row["target_type"], lit(row["target_id"])), row["ordinal"])
    kw = {"directed": row["directed"] == "true", "multigraph": row["multigraph"] == "true"}
    if row["expect"] == "ok":
        got = edge_address(e, **kw)
        assert (got.source.node_id, got.target.node_id, got.ordinal) == (row["expect_source"], row["expect_target"], row["ordinal"])
    else:
        expect_reject(edge_address, row["expect"].removeprefix("reject:"), e, **kw)


def _groups(rows):
    g = defaultdict(list)
    for r in rows:
        g[r["id"]].append(r)
    return g


@pytest.mark.parametrize("vid,rows", _groups(T["order"]).items(), ids=lambda v: v if isinstance(v, str) else "")
def test_order_table(vid, rows):
    items = [(r["node_type"], tag_id(lit(r["node_id"])), int(r["position"])) for r in rows]
    # sort a REVERSED copy: the file already lists rows in text order, so a constant key would otherwise hand back file order
    by_semantic = sorted(reversed(items), key=lambda x: semantic_key(x[0], x[1]))
    assert [x[2] for x in by_semantic] == list(range(len(items))), vid                   # the stated ranks ARE the semantic order
    trap = {r["trap"] for r in rows}
    assert len(trap) == 1
    trap = trap.pop()
    if trap == "text":
        assert sorted(items, key=lambda x: (x[0], x[1])) != by_semantic, f"{vid}: file/text order must differ from semantic order"
    elif trap == "utf16":
        assert sorted(items, key=lambda x: (x[0].encode("utf-16-be"), x[1].encode("utf-16-be", "surrogatepass"))) != by_semantic
    else:
        assert trap == "none", f"unknown trap {trap!r}"


@pytest.mark.parametrize("vid,rows", _groups(T["edge_order"]).items(), ids=lambda v: v if isinstance(v, str) else "")
def test_edge_order_table(vid, rows):
    def typed(r):
        return TypedEdge(TypedNode(r["source_type"], tag_id(lit(r["source_id"]))), r["relation"],
                         TypedNode(r["target_type"], tag_id(lit(r["target_id"]))), r["ordinal"])
    items = [(typed(r), int(r["position"])) for r in rows]
    # sort a reversed copy (see test_order_table): a constant key must not be able to pass by returning file order
    assert [p for _e, p in sorted(reversed(items), key=lambda x: edge_semantic_key(x[0]))] == list(range(len(items))), vid


@pytest.mark.parametrize("row", T["twins"], ids=lambda r: r["id"])
def test_twins_table(row):
    guard = TwinGuard()
    guard.see(NodeRef(row["type_a"], lit(row["id_a"])), "a")
    if row["expect"] == "ok":
        guard.see(NodeRef(row["type_b"], lit(row["id_b"])), "b")
    else:
        expect_reject(guard.see, row["expect"].removeprefix("reject:"), NodeRef(row["type_b"], lit(row["id_b"])), "b")


# =====================================================================================================================
# vectors/igdc1: every row runs; `op` (never the presence of a column) selects what is executed.
# =====================================================================================================================
from conftest import all_baselines  # noqa: E402

from isongraph_ext.igdc.derive import consume  # noqa: E402
from isongraph_ext.igdc.verify import verify_derivation, verify_hints  # noqa: E402
from isongraph_ext.igdm.errors import IGDMError  # noqa: E402
from isongraph_ext.igdm.records import Limits  # noqa: E402
from isongraph_ext.igx.binding import ExtensionBinding  # noqa: E402
from isongraph_ext.igx.errors import IGXError  # noqa: E402

CONS = ROOT / "vectors" / "igdc1"
CONSUMPTION_COUNTS = {"consume:ok": 19, "consume:reject": 7, "verify:ok": 1, "verify:reject": 53, "derivation:reject": 6}


def cons_rows():
    doc = loads((CONS / "manifest.ison").read_text(encoding="utf-8"))
    return [r for b in doc.blocks if (b.kind, b.name) == ("table", "vectors") for r in b.rows]


def _read(rel):
    return (CONS / rel).read_bytes() if rel else None


def _kw(detail):
    kw = {}
    for item in (detail or "").split(";"):
        k, _, v = item.strip().partition(":")
        if k == "limits":
            name, _, num = v.partition("=")
            kw["limits"] = Limits(**{**Limits().__dict__, name: int(num)})
        elif k == "baselines":
            assert v == "all"
            kw["baselines"] = all_baselines()
    return kw


def _inputs(row):
    return _read(row["payload"]), ExtensionBinding.from_ison(_read(row["binding"]).decode("utf-8")), _read(row["target"])


def test_consumption_manifest_counts_and_checksums():
    rows = cons_rows()
    got = {}
    for r in rows:
        got[f"{r['op']}:{r['expect']}"] = got.get(f"{r['op']}:{r['expect']}", 0) + 1
    assert got == CONSUMPTION_COUNTS
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for line in (CONS / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        assert hashlib.sha256((CONS / name).read_bytes()).hexdigest() == digest, name


_CONSUME_ERROR = {"V": IGXError, "D": IGDMError, "P": IGDCError}


def test_consume_error_types_are_unrelated():
    assert not any(issubclass(a, b) for a in _CONSUME_ERROR.values() for b in _CONSUME_ERROR.values() if a is not b)


@pytest.mark.parametrize("row", cons_rows(), ids=lambda r: r["id"])
def test_consumption_vector(row):
    op, expect, kw = row["op"], row["expect"], _kw(row["detail"])
    if op == "consume":
        payload, binding, target = _inputs(row)
        if expect == "ok":
            got = consume(payload, binding, target, **kw)
            assert got.to_ison().encode("utf-8") == _read(row["hints"]), row["id"]            # byte-exact with the INDEPENDENT reference deriver
            verify_hints(_read(row["hints"]))
            verify_derivation(_read(row["hints"]), payload, binding, target, **kw)
            assert got.meta["target_directed"] in ("true", "false")
        else:
            want = _CONSUME_ERROR[row["step"][0]]                                              # V* -> igx, D* -> igdm, P* -> igdc: no other type
            with pytest.raises(Exception) as e:
                consume(payload, binding, target, **kw)
            assert type(e.value) is want, (type(e.value).__name__, want.__name__, e.value)
            assert (e.value.code, e.value.step) == (row["code"], row["step"]), e.value
    elif op == "verify":
        if expect == "ok":
            verify_hints(_read(row["hints"]), **kw)
        else:
            with pytest.raises(IGDCError) as e:
                verify_hints(_read(row["hints"]), **kw)
            assert (e.value.code, e.value.step) == (row["code"], row["step"]), e.value
    elif op == "derivation":
        payload, binding, target = _inputs(row)
        assert expect == "reject"
        with pytest.raises(IGDCError) as e:
            verify_derivation(_read(row["hints"]), payload, binding, target, **kw)
        assert (e.value.code, e.value.step) == (row["code"], row["step"]), e.value
    else:
        pytest.fail(f"unknown op {op!r}")


def test_int_id_ordering_trap_file_order_differs_from_semantic_order():
    from isongraph_ext.igdc.hints import HintSet
    row = next(r for r in cons_rows() if r["id"] == "ok/int-id-ordering-trap")
    h = HintSet.from_ison(_read(row["hints"]))
    ids = [(r["node_type"], r["node_id"]) for r in h.nodes]
    assert ids != sorted(ids, key=lambda x: semantic_key(*x)) and ids.index(("t", "i:10")) < ids.index(("t", "i:2"))

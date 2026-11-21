# scripts/make_vectors_igdc.py   (address part; Task 6 appends the consumption part and replaces main)
"""Generate the IGDC/1 vector sets (26 §5). Independent of the production package: this file imports ONLY ison_parser.

    python scripts/make_vectors_igdc.py --addr     # vectors/igs-addr  (hand-written literals; Task 2)
    python scripts/make_vectors_igdc.py            # also vectors/igdc1 (reference deriver; Task 5)

Typed literals keep a value's TYPE explicit so no reader ever infers it from digits:
    int:7  str:7  bool:true  float:1.5  null:  surrogate:d800 (a one-character str holding a lone surrogate)
    tagged:i:7  tagged-lone:d800 (the text "s:" followed by a lone surrogate)
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical, loads

ROOT = Path(__file__).resolve().parents[1]
I64_MIN, I64_MAX = -(2**63), 2**63 - 1
BAD = "reject:INVALID_ADDRESS"

# ---- table.vectors: id | kind | input | expect --------------------------------------------------------------------------
TAG = [  # kind "tag": a value's type decides its tag; spelling never does
    ("ok/int-7", "int:7", "i:7"), ("ok/string-7", "str:7", "s:7"), ("ok/int-zero", "int:0", "i:0"), ("ok/int-negative-one", "int:-1", "i:-1"),
    ("ok/int64-min", f"int:{I64_MIN}", f"i:{I64_MIN}"), ("ok/int64-max", f"int:{I64_MAX}", f"i:{I64_MAX}"),
    ("ok/string-007", "str:007", "s:007"), ("ok/string-minus0", "str:-0", "s:-0"), ("ok/string-1e3", "str:1e3", "s:1e3"),
    ("ok/string-leading-plus", "str:+5", "s:+5"), ("ok/string-looks-tagged-i", "str:i:7", "s:i:7"), ("ok/string-looks-tagged-s", "str:s:7", "s:s:7"),
    ("ok/string-beyond-int64", f"str:{I64_MAX + 1}", f"s:{I64_MAX + 1}"), ("ok/string-arabic-indic-digit", "str:\u0663", "s:\u0663"),
    ("ok/string-nfc", "str:\u00e9", "s:\u00e9"), ("ok/string-nfd", "str:e\u0301", "s:e\u0301"), ("ok/string-astral", "str:\U0001f600", "s:\U0001f600"),
    ("ok/string-fullwidth-tilde", "str:\uff5e", "s:\uff5e"), ("ok/string-with-quote", 'str:q"q', 's:q"q'),
    ("ok/string-empty-is-valid-syntax", "str:", "s:"),
    ("reject/int64-overflow", f"int:{I64_MAX + 1}", BAD), ("reject/int64-underflow", f"int:{I64_MIN - 1}", BAD),
    ("reject/bool-true-id", "bool:true", BAD), ("reject/bool-false-id", "bool:false", BAD), ("reject/float-id", "float:1.5", BAD),
    ("reject/float-integral-id", "float:7.0", BAD), ("reject/null-id", "null:", BAD), ("reject/lone-surrogate-id", "surrogate:d800", BAD),
]
PARSE = [  # kind "parse": the inverse; expect is a typed literal
    ("ok/parse-i-7", "tagged:i:7", "int:7"), ("ok/parse-s-7", "tagged:s:7", "str:7"), ("ok/parse-s-007", "tagged:s:007", "str:007"),
    ("ok/parse-s-looks-tagged", "tagged:s:i:7", "str:i:7"), ("ok/parse-s-empty", "tagged:s:", "str:"),
    ("ok/parse-i-min", f"tagged:i:{I64_MIN}", f"int:{I64_MIN}"), ("ok/parse-i-max", f"tagged:i:{I64_MAX}", f"int:{I64_MAX}"),
    ("reject/parse-bare-7", "tagged:7", BAD), ("reject/parse-i-leading-zero", "tagged:i:007", BAD), ("reject/parse-i-minus-zero", "tagged:i:-0", BAD),
    ("reject/parse-i-plus", "tagged:i:+5", BAD), ("reject/parse-i-empty", "tagged:i:", BAD), ("reject/parse-i-decimal-point", "tagged:i:1.0", BAD),
    ("reject/parse-i-space", "tagged:i: 7", BAD), ("reject/parse-i-trailing-space", "tagged:i:7 ", BAD),
    ("reject/parse-i-arabic-indic-digit", "tagged:i:\u0663", BAD), ("reject/parse-i-overflow", f"tagged:i:{I64_MAX + 1}", BAD),
    ("reject/parse-i-underflow", f"tagged:i:{I64_MIN - 1}", BAD), ("reject/parse-unknown-tag", "tagged:x:7", BAD),
    ("reject/parse-uppercase-tag", "tagged:I:7", BAD), ("reject/parse-empty", "tagged:", BAD), ("reject/parse-tag-without-colon", "tagged:i", BAD),
    ("reject/parse-s-lone-surrogate", "tagged-lone:d800", BAD),
]
IDENT = [  # kinds "node_type" and "relation" share Core's identifier rule: non-empty, no whitespace, none of : | " \
    *[(f"ok/{k}-{n}", k, v, "ok") for k in ("node_type", "relation") for n, v in (("plain", "order"), ("unicode", "\u00e9tude"), ("punctuation", "a-b_c.d"))],
    *[(f"reject/{k}-{n}", k, v, BAD) for k in ("node_type", "relation") for n, v in
      (("empty", "str:"), ("space", "str:a b"), ("colon", "str:a:b"), ("pipe", "str:a|b"), ("quote", 'str:a"b'), ("backslash", "str:a\\b"), ("tab", "str:a\tb"))],
]
IDENT = [(i, k, v if v.startswith("str:") else f"str:{v}", e) for i, k, v, e in IDENT]

# ---- table.edges: one logical edge; directed / multigraph decide which ordinals and endpoint orders are legal ---------------
# id | source_type source_id | relation | target_type target_id | ordinal | directed multigraph | expect | expect_source expect_target
EDGES = [
    ("ok/directed-as-written", "a", "int:9", "r", "a", "int:1", "0", "true", "false", "ok", "i:9", "i:1"),
    ("ok/directed-string-to-int", "a", "str:x", "r", "a", "int:1", "0", "true", "false", "ok", "s:x", "i:1"),
    ("ok/undirected-canonical-int-before-string", "a", "int:5", "r", "a", "str:a", "0", "false", "false", "ok", "i:5", "s:a"),
    ("ok/undirected-canonical-ints-numeric", "a", "int:3", "r", "a", "int:5", "0", "false", "false", "ok", "i:3", "i:5"),
    ("ok/undirected-canonical-negative-first", "a", "int:-1", "r", "a", "int:0", "0", "false", "false", "ok", "i:-1", "i:0"),
    ("ok/undirected-canonical-type-bytes", "a", "int:9", "r", "b", "int:1", "0", "false", "false", "ok", "i:9", "i:1"),
    ("ok/undirected-self-loop", "a", "int:3", "r", "a", "int:3", "0", "false", "false", "ok", "i:3", "i:3"),
    ("ok/multigraph-ordinal-0", "a", "int:1", "r", "a", "int:2", "0", "true", "true", "ok", "i:1", "i:2"),
    ("ok/multigraph-ordinal-1", "a", "int:1", "r", "a", "int:2", "1", "true", "true", "ok", "i:1", "i:2"),
    ("ok/multigraph-ordinal-10", "a", "int:1", "r", "a", "int:2", "10", "true", "true", "ok", "i:1", "i:2"),
    ("reject/undirected-string-before-int", "a", "str:a", "r", "a", "int:5", "0", "false", "false", BAD, "", ""),
    ("reject/undirected-ints-out-of-order", "a", "int:5", "r", "a", "int:3", "0", "false", "false", BAD, "", ""),
    ("reject/undirected-type-bytes-out-of-order", "b", "int:1", "r", "a", "int:9", "0", "false", "false", BAD, "", ""),
    ("reject/simple-graph-ordinal-1", "a", "int:1", "r", "a", "int:2", "1", "true", "false", BAD, "", ""),
    ("reject/ordinal-leading-zero", "a", "int:1", "r", "a", "int:2", "01", "true", "true", BAD, "", ""),
    ("reject/ordinal-double-zero", "a", "int:1", "r", "a", "int:2", "00", "true", "true", BAD, "", ""),
    ("reject/ordinal-negative", "a", "int:1", "r", "a", "int:2", "-1", "true", "true", BAD, "", ""),
    ("reject/ordinal-empty", "a", "int:1", "r", "a", "int:2", "", "true", "true", BAD, "", ""),
    ("reject/ordinal-not-ascii-digit", "a", "int:1", "r", "a", "int:2", "\u0663", "true", "true", BAD, "", ""),
]

# ---- table.order: a set of node addresses and the rank each must have in SEMANTIC order ----------------------------------
# id | set | trap | node_type | node_id | position.  `id` names the vector, its rows are the members of one set.
# trap=text: sorting (node_type, tagged id) as plain text gives a DIFFERENT order; trap=utf16: sorting by UTF-16 code units does; none: no claim.
ORDER = [
    *[("ok/order-mixed", "mixed", "text", t, v, p) for t, v, p in
      [("a", "int:-1", 0), ("a", "int:0", 1), ("a", "int:2", 2), ("a", "int:10", 3), ("a", "str:a", 4), ("a", "str:~", 5), ("a", "str:\u00e9", 6),
       ("a", "str:\U0001f600", 7), ("b", "int:1", 8), ("b", "str:a", 9)]],
    *[("ok/order-ints-numeric-not-text", "ints", "text", "t", v, p) for v, p in [("int:-10", 0), ("int:-2", 1), ("int:0", 2), ("int:2", 3), ("int:10", 4), ("int:100", 5)]],
    *[("ok/order-every-int-before-every-string", "intstr", "none", "t", v, p) for v, p in [("int:9223372036854775807", 0), ("str:", 1), ("str:0", 2)]],
    *[("ok/order-int64-extremes", "extremes", "text", "t", v, p) for v, p in [(f"int:{I64_MIN}", 0), ("int:-1", 1), ("int:0", 2), (f"int:{I64_MAX}", 3)]],
    *[("ok/order-utf8-not-utf16", "utf8", "utf16", "t", v, p) for v, p in [("str:\uff5e", 0), ("str:\U0001f600", 1)]],
    *[("ok/order-type-bytes-first", "types", "none", t, v, p) for t, v, p in [("a", "int:9", 0), ("a", "str:z", 1), ("b", "int:1", 2), ("\u00e9", "int:0", 3)]],
    *[("ok/order-string-bytes-not-case-folded", "strings", "none", "t", v, p) for v, p in [("str:A", 0), ("str:B", 1), ("str:a", 2), ("str:b", 3)]],
]
# ---- table.edge_order: source, relation bytes, target, ordinal bytes ---------------------------------------------------------
# id | set | source_type source_id | relation | target_type target_id | ordinal | position
EDGE_ORDER = [
    *[("ok/edge-order-ordinal-bytes", "ordinals", "t", "int:1", "r", "t", "int:2", o, p) for o, p in [("0", 0), ("1", 1), ("10", 2), ("2", 3)]],
    *[("ok/edge-order-relation-bytes", "relations", "t", "int:1", r, "t", "int:2", "0", p) for r, p in [("a", 0), ("b", 1), ("c", 2)]],
    *[("ok/edge-order-source-then-relation", "srcrel", "t", s, r, "t", "int:9", "0", p) for s, r, p in
      [("int:1", "z", 0), ("int:2", "a", 1), ("int:2", "b", 2), ("str:a", "a", 3)]],
]
# ---- table.twins: ID-TWIN-INVARIANT ---------------------------------------------------------------------------------------
# id | type_a id_a | type_b id_b | expect
TWINS = [
    ("reject/twin-i7-s7", "a", "int:7", "a", "str:7", "reject:TWIN_IDS"), ("reject/twin-s7-i7-reversed", "a", "str:7", "a", "int:7", "reject:TWIN_IDS"),
    ("reject/twin-i0-s0", "a", "int:0", "a", "str:0", "reject:TWIN_IDS"), ("reject/twin-negative", "a", "int:-7", "a", "str:-7", "reject:TWIN_IDS"),
    ("ok/twin-not-s007-vs-i7", "a", "int:7", "a", "str:007", "ok"), ("ok/twin-not-s-minus0-vs-i0", "a", "int:0", "a", "str:-0", "ok"),
    ("ok/twin-not-across-types", "a", "int:7", "b", "str:7", "ok"), ("ok/twin-not-two-ints", "a", "int:7", "a", "int:8", "ok"),
]


def _vec_rows():
    rows = [{"id": i, "kind": "tag", "input": a, "expect": e} for i, a, e in TAG]
    rows += [{"id": i, "kind": "parse", "input": a, "expect": e} for i, a, e in PARSE]
    rows += [{"id": i, "kind": k, "input": a, "expect": e} for i, k, a, e in IDENT]
    return rows


TABLES = (
    ("vectors", ["id", "kind", "input", "expect"], _vec_rows),
    ("edges", ["id", "source_type", "source_id", "relation", "target_type", "target_id", "ordinal", "directed", "multigraph", "expect", "expect_source", "expect_target"],
     lambda: [dict(zip(["id", "source_type", "source_id", "relation", "target_type", "target_id", "ordinal", "directed", "multigraph", "expect", "expect_source", "expect_target"], r)) for r in EDGES]),
    ("order", ["id", "trap", "node_type", "node_id", "position"], lambda: [dict(zip(["id", "trap", "node_type", "node_id", "position"], r[:1] + r[2:])) for r in ORDER]),
    ("edge_order", ["id", "source_type", "source_id", "relation", "target_type", "target_id", "ordinal", "position"],
     lambda: [dict(zip(["id", "source_type", "source_id", "relation", "target_type", "target_id", "ordinal", "position"], r[:1] + r[2:])) for r in EDGE_ORDER]),
    ("twins", ["id", "type_a", "id_a", "type_b", "id_b", "expect"], lambda: [dict(zip(["id", "type_a", "id_a", "type_b", "id_b", "expect"], r)) for r in TWINS]),
)

README = """# vectors/igs-addr — IGDC/1 typed-address vectors (26 §1, §5)

Hand-written literals, independent of `isongraph_ext.igdc`. Every row of every table is normative: a port claims conformance by passing ALL rows
(the manifest row counts are part of the claim). Values are typed literals (`int:7` is an integer, `str:7` a string, `surrogate:d800` a lone
surrogate); no reader may infer a type from digits. `SHA256SUMS` pins the files; `manifest.ison` is canonical ison-py output.

Tables: `vectors` (tag, parse, node_type, relation) · `edges` · `order` · `edge_order` · `twins`.
"""


def write_set(directory: Path, tables, readme: str) -> dict[str, int]:
    directory.mkdir(parents=True, exist_ok=True)
    blocks, counts, ids = [], {}, set()
    for name, cols, rows_fn in tables:
        rows = rows_fn()
        for r in rows:
            assert set(r) == set(cols), (name, r)
        counts[name] = len(rows)
        blocks.append(Block("table", name, cols, rows))
    text = dumps_canonical(Document(blocks=blocks))
    again = loads(text)
    for b, (name, cols, rows_fn) in zip(sorted(again.blocks, key=lambda b: b.name), sorted(tables, key=lambda t: t[0])):    # cells survive the writer
        key = lambda r: repr(sorted(r.items()))  # noqa: E731  (the writer orders rows; compare as sets of rows)
        assert sorted(b.rows, key=key) == sorted(rows_fn(), key=key), f"table {name} did not round-trip through the canonical writer"
    (directory / "manifest.ison").write_bytes(text.encode("utf-8"))
    (directory / "README.md").write_bytes(readme.encode("utf-8"))
    sums = "".join(f"{hashlib.sha256((directory / n).read_bytes()).hexdigest()}  {n}\n" for n in sorted(p.name for p in directory.iterdir() if p.name != "SHA256SUMS"))
    (directory / "SHA256SUMS").write_bytes(sums.encode("utf-8"))
    return counts


def main(argv: list[str]) -> None:
    counts = write_set(ROOT / "vectors" / "igs-addr", TABLES, README)
    print("igs-addr", counts, "total", sum(counts.values()))


if __name__ == "__main__":
    main(sys.argv[1:])

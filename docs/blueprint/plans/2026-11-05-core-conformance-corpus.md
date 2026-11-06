# Core Conformance Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an executable, Core-owned conformance corpus (`vectors/`) to `ISON-format/isongraph` with Python, TypeScript and JavaScript runners, a corpus digest and a per-port Core Conformance Receipt, so "same document → same meaning in every port" is tested on every push and Ext can pin it.

**Architecture:** `vectors/manifest.ison` (plain ISON, parsed by each port's own parser) indexes ~31 `.ison`/`.isonl` documents under `vectors/{ids,values,structure,serialization}/`. Each port has one parametrized test file inside its existing suite that loads every document and checks the per-port expectation (`pass` / `pass:canonicalized` / `pass:lossy` / `defect` / `reject:<Error>` / `todo`). Two small Python scripts compute the corpus digest and the receipt. No new CI job: the existing per-port jobs run the runners.

**Tech Stack:** Python 3.12 + pytest + ison-py 1.2 (reference runner); TypeScript + vitest + ison-ts; JavaScript + vitest + ison-parser; git.

**Spec:** `isongraphext/isongraphext/docs/isongraph-ext-blueprint/15-CORE-CONFORMANCE-CORPUS.md` (sections referenced as §N). Companion: `13-SEMANTIC-2.md` §6.1 (postures), `14-E0-FORENSICS.md` (prior findings).

**Repo:** `d:/Goldmine/ISON/ison_dev/isongraphossworking/isongraph` (clone of `ISON-format/isongraph`, `main` at `027fb77` = v1.4.1). Work on branch `feat/conformance-corpus`.

## Global Constraints

- Every vector file is UTF-8 without BOM, LF-only, and ends in exactly one `\n`. Comparison is always `to_ison() + "\n"` against the file bytes (§5).
- `.gitattributes` must force LF for `vectors/**` so Windows checkouts cannot break byte comparisons (§3).
- Expectations are set from **observed** behaviour of the released port; a contradiction with `13-SEMANTIC-2.md` becomes a Findings row, never a weakened vector (§5).
- Port runner admission is atomic: a port column contains `todo` iff that port's runner file does not exist (§5). This iteration admits `python`, `ts`, `js`; `rust`, `cs`, `cpp` stay `todo`.
- `digest` column is `null` for every row (§2).
- Each port reads only its own column; error names are that port's own (§4).
- The corpus tests documents only; no API-level vectors (§2).
- No new dependencies in any port. TS already has `@types/node`; JS tests use `node:fs` at runtime only.
- Commit messages follow the repo's style: imperative first line explaining the *why*, body in plain prose, and end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Run tests from the package directory as CI does: `cd ison-graph && python -m pytest -q`, `cd ison-graph-ts && npx vitest run`, `cd ison-graph-js && npx vitest run`.

## Review Focus

1. A Windows checkout with `core.autocrlf=true` turns LF into CRLF and every `pass` vector fails for a non-reason → `.gitattributes` rule (Task 1) and the meta-test asserting no `\r` byte in any vector file (Task 1).
2. An editor strips or adds the final newline of a vector → meta-test asserts every file ends with exactly one `\n` and not `\n\n` (Task 1).
3. A manifest row names a file or canonical sibling that does not exist, or two rows share an id → meta-test (Task 1).
4. A row says `pass` but also carries a `canonical` sibling, or `pass:canonicalized` without one → meta-test asserts `canonical` is non-null iff some port column is `pass:canonicalized` (Task 1).
5. A port column says `defect` with no Findings entry, so a known divergence silently stops being documented → meta-test parses `vectors/README.md` for a `| <vector id> |` row in the Findings table for every `defect` cell (Task 1, exercised from Task 4 on).

---

### Task 1: Harness — gitattributes, manifest skeleton, Python runner and meta-test with the first two vectors

**Files:**
- Modify: `.gitattributes` (append one rule)
- Create: `vectors/manifest.ison`
- Create: `vectors/ids/positive-int.ison`, `vectors/ids/twin-int-string.ison`
- Create: `vectors/README.md` (minimal; Task 10 completes it)
- Create: `ison-graph/tests/test_vectors.py`

**Interfaces:**
- Produces: `vectors/manifest.ison` schema — `meta.corpus` block (`version`, `semantic_spec`) and `table.vectors` block with columns `id file semantic reason directed nodes edges canonical digest python ts js rust cs cpp`. Later tasks append rows to `table.vectors` only.
- Produces: `test_vectors.py` helpers `VECTORS: Path`, `ROWS: list[dict]`, `_read(rel) -> str`, `_load(rel, text) -> ISONGraph`, `_emit(g) -> str`, `RUNNERS: dict[str, str]`.

- [ ] **Step 1: Create the branch**

```bash
cd d:/Goldmine/ISON/ison_dev/isongraphossworking/isongraph
git checkout main && git pull -q && git checkout -b feat/conformance-corpus
```

- [ ] **Step 2: Force LF for the corpus**

Append to `.gitattributes` (after the `*.yaml text eol=lf` line):

```
# Conformance vectors are compared byte-for-byte by every port's test suite
vectors/** text eol=lf
```

- [ ] **Step 3: Write the two first vector files and the manifest skeleton**

Run this Python snippet from the repo root (it writes exact bytes; do not create these files in an editor):

```python
from pathlib import Path
V = Path("vectors")
def w(rel, text):
    p = V / rel; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))

w("ids/positive-int.ison", "edges.R\nsource target\n:p:1 :p:2\n\nnodes.p\nid\n1\n2\n")
w("ids/twin-int-string.ison", "nodes.p\nid\n1\n\"1\"\n")
w("manifest.ison",
  "meta.corpus\n"
  "version semantic_spec\n"
  "1 \"ISONGraph-Semantic/2-draft\"\n"
  "\n"
  "table.vectors\n"
  "id file semantic reason directed nodes edges canonical digest python ts js rust cs cpp\n"
  "ids/positive-int ids/positive-int.ison identifiable null true 2 1 null null pass todo todo todo todo todo\n"
  "ids/twin-int-string ids/twin-int-string.ison out_of_domain AMBIGUOUS_NODE_REFERENCE true 0 0 null null \"reject:DuplicateNodeError\" todo todo todo todo todo\n")
w("README.md",
  "# ISONGraph Core Conformance Corpus\n\n"
  "Executable vectors proving \"same document -> same meaning in every port\". Owned by Core; "
  "consumed by ISONGraphExt and downstream at a pinned commit, never copied.\n\n"
  "See `manifest.ison` for the index. Full design: ISONGraphExt blueprint `15-CORE-CONFORMANCE-CORPUS.md`.\n\n"
  "## Findings\n\n"
  "| vector | ports | observed | spec says | status |\n"
  "|---|---|---|---|---|\n")
print("ok")
```

- [ ] **Step 4: Write the failing runner + meta-test**

Create `ison-graph/tests/test_vectors.py`:

```python
"""Core Conformance Corpus runner - Python is the reference port.

Reads vectors/manifest.ison with ison-py, loads every vector document and
checks this port's expectation column. The grammar of that column and the
meaning of every other column are in vectors/README.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ison_parser import loads

from ison_graph import ISONGraph

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "vectors"
PORT = "python"

#: Runner file per port, relative to the repo root. A port column may say
#: 'todo' only while its runner does not exist - admission is atomic.
RUNNERS = {
    "python": "ison-graph/tests/test_vectors.py",
    "ts": "ison-graph-ts/src/vectors.test.ts",
    "js": "ison-graph-js/src/vectors.test.js",
    "rust": "ison-graph-rs/tests/vectors.rs",
    "cs": "ison-graph-cs/tests/IsonGraph.Tests/VectorsTests.cs",
    "cpp": "ison-graph-cpp/tests/test_vectors.cpp",
}
PORTS = tuple(RUNNERS)
EXPECTATIONS = ("pass", "pass:canonicalized", "pass:lossy", "defect", "todo")


def _read(rel: str) -> str:
    # newline='' keeps '\n' exactly; read_text would translate on Windows.
    with open(VECTORS / rel, encoding="utf-8", newline="") as f:
        return f.read()


def _manifest() -> list[dict]:
    doc = loads(_read("manifest.ison"))
    rows = [r for b in doc.blocks if b.kind == "table" and b.name == "vectors" for r in b.rows]
    assert rows, "manifest.ison has no table.vectors rows"
    return rows


ROWS = _manifest()


def _load(rel: str, text: str) -> ISONGraph:
    return ISONGraph.from_isonl(text) if rel.endswith(".isonl") else ISONGraph.from_ison(text)


def _emit(graph: ISONGraph) -> str:
    return graph.to_ison() + "\n"


def _findings_ids() -> set[str]:
    text = _read("README.md")
    return set(re.findall(r"^\| (\S+) \|", text, flags=re.M)) - {"vector", "---"}


# =============================================================================
# Meta-test: the manifest and files are what the runners assume they are.
# =============================================================================

def test_manifest_integrity():
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids)), "duplicate vector ids"

    findings = _findings_ids()
    for row in ROWS:
        assert row["semantic"] in ("identifiable", "out_of_domain"), row["id"]
        assert (row["semantic"] == "identifiable") == (row["reason"] is None), row["id"]
        assert row["digest"] is None, row["id"]
        assert isinstance(row["directed"], bool), row["id"]
        assert isinstance(row["nodes"], int) and isinstance(row["edges"], int), row["id"]

        for key in ("file", "canonical"):
            rel = row[key]
            if rel is None:
                continue
            path = VECTORS / rel
            assert path.is_file(), f"{row['id']}: {key} {rel} missing"
            data = path.read_bytes()
            assert b"\r" not in data, f"{rel}: CRLF"
            assert not data.startswith(b"\xef\xbb\xbf"), f"{rel}: BOM"
            assert data.endswith(b"\n") and not data.endswith(b"\n\n"), f"{rel}: must end in exactly one LF"
            data.decode("utf-8")  # raises on invalid UTF-8

        cells = {p: row[p] for p in PORTS}
        for port, cell in cells.items():
            assert isinstance(cell, str) and cell, f"{row['id']}: {port} empty"
            assert cell in EXPECTATIONS or cell.startswith("reject:"), f"{row['id']}: {port}={cell!r}"
            runner_exists = (ROOT / RUNNERS[port]).is_file()
            assert (cell == "todo") == (not runner_exists), (
                f"{row['id']}: {port} is {cell!r} but runner "
                f"{'exists' if runner_exists else 'is missing'}"
            )
            if cell == "defect":
                assert row["id"] in findings, f"{row['id']}: {port}=defect needs a README Findings row"

        wants_canonical = any(c == "pass:canonicalized" for c in cells.values())
        assert (row["canonical"] is not None) == wants_canonical, (
            f"{row['id']}: canonical must be set iff some port is pass:canonicalized"
        )


# =============================================================================
# Runner
# =============================================================================

@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_vector(row):
    expectation = row[PORT]
    text = _read(row["file"])

    if expectation.startswith("reject:"):
        with pytest.raises(Exception) as info:
            _load(row["file"], text)
        assert type(info.value).__name__ == expectation[len("reject:"):]
        return

    graph = _load(row["file"], text)
    assert graph.directed == row["directed"]
    assert graph.node_count() == row["nodes"]
    assert graph.edge_count() == row["edges"]

    out = _emit(graph)
    if expectation == "defect":
        # Contradicts the spec (see README Findings) - but pin what the port
        # does so a wrong reading cannot drift into a different wrong one.
        assert _emit(ISONGraph.from_ison(out)) == out
    elif expectation == "pass":
        assert out == text
    elif expectation == "pass:canonicalized":
        assert out == _read(row["canonical"])
        assert _emit(ISONGraph.from_ison(out)) == out
    elif expectation == "pass:lossy":
        assert _emit(ISONGraph.from_ison(out)) == out
    else:
        pytest.fail(f"unknown expectation {expectation!r} for {PORT}")
```

- [ ] **Step 5: Run it — expect the meta-test to pass and both vectors to pass**

```bash
cd ison-graph && python -m pytest tests/test_vectors.py -v
```

Expected: `test_manifest_integrity PASSED`, `test_vector[ids/positive-int] PASSED`, `test_vector[ids/twin-int-string] PASSED`. (This is the only task whose first run is expected green: the two documents were chosen because 1.4.1's behaviour on them is already pinned by unit tests. If `ids/positive-int` fails on the byte comparison, print `ISONGraph.from_ison(text).to_ison()` and compare — the file must be exactly Python's canonical form; fix the file, not the test.)

- [ ] **Step 6: Prove the meta-test bites — temporarily break a rule, then restore**

```bash
printf '\n' >> vectors/ids/positive-int.ison      # second trailing LF
python -m pytest tests/test_vectors.py::test_manifest_integrity -q    # expected: FAIL "must end in exactly one LF"
git checkout vectors/ids/positive-int.ison 2>/dev/null || python -c "open('vectors/ids/positive-int.ison','wb').write(b'edges.R\nsource target\n:p:1 :p:2\n\nnodes.p\nid\n1\n2\n')"
python -m pytest tests/test_vectors.py -q         # expected: 3 passed
```

- [ ] **Step 7: Run the full Python suite to make sure nothing else is affected**

```bash
python -m pytest -q
```
Expected: previous 498 + 3 = 501 passed.

- [ ] **Step 8: Commit**

```bash
cd .. && git add .gitattributes vectors ison-graph/tests/test_vectors.py
git commit -F - <<'EOF'
Start the Core conformance corpus with its Python runner

One golden fixture and prose were all that said the six ports agree on
what a document means. vectors/manifest.ison now indexes executable
documents, each with a per-port expectation, and ison-graph/tests/
test_vectors.py runs them as part of the Python suite. A meta-test pins
the rules the runners assume: LF-only files ending in one newline,
unique ids, existing files, and that a port says 'todo' exactly when it
has no runner, so a port cannot be half-admitted.

Two vectors to start; the rest follow by group.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 2: `ids/` vectors

**Files:**
- Create: `vectors/ids/negative-int.ison`, `string-numeric.ison`, `string-negative.ison`, `int64-extremes.ison`, `twin-negative.ison`, `float-id.ison`, `bool-id.ison`
- Modify: `vectors/manifest.ison` (append 7 rows)

**Interfaces:**
- Consumes: manifest schema and runner from Task 1.

- [ ] **Step 1: Write the files**

```python
from pathlib import Path
V = Path("vectors")
def w(rel, text): (V / rel).write_bytes(text.encode("utf-8"))

w("ids/negative-int.ison", "edges.R\nsource target\n:p:-1 :p:2\n:p:2 :p:-1\n\nnodes.p\nid\n-1\n2\n")
w("ids/string-numeric.ison", "edges.R\nsource target\n:p:1 :p:2\n\nnodes.p\nid\n\"1\"\n\"2\"\n")
w("ids/string-negative.ison", "edges.R\nsource target\n:p:-1 :p:2\n\nnodes.p\nid\n\"-1\"\n2\n")
w("ids/int64-extremes.ison", "edges.R\nsource target\n:p:-9223372036854775808 :p:9223372036854775807\n\nnodes.p\nid\n-9223372036854775808\n9223372036854775807\n")
w("ids/twin-negative.ison", "nodes.p\nid\n-1\n\"-1\"\n")
w("ids/float-id.ison", "nodes.p\nid\n1.5\n")
w("ids/bool-id.ison", "nodes.p\nid\ntrue\n")
print("ok")
```

- [ ] **Step 2: Append the predicted rows to `table.vectors` in `vectors/manifest.ison`**

```
ids/negative-int ids/negative-int.ison identifiable null true 2 2 null null pass todo todo todo todo todo
ids/string-numeric ids/string-numeric.ison identifiable null true 2 1 null null pass todo todo todo todo todo
ids/string-negative ids/string-negative.ison identifiable null true 2 1 null null pass todo todo todo todo todo
ids/int64-extremes ids/int64-extremes.ison identifiable null true 2 1 null null pass todo todo todo todo todo
ids/twin-negative ids/twin-negative.ison out_of_domain AMBIGUOUS_NODE_REFERENCE true 0 0 null null "reject:DuplicateNodeError" todo todo todo todo todo
ids/float-id ids/float-id.ison out_of_domain INVALID_NODE_ID_TYPE true 0 0 null null "reject:InvalidIdentifierError" todo todo todo todo todo
ids/bool-id ids/bool-id.ison out_of_domain INVALID_NODE_ID_TYPE true 0 0 null null "reject:InvalidIdentifierError" todo todo todo todo todo
```

- [ ] **Step 3: Run the runner**

```bash
cd ison-graph && python -m pytest tests/test_vectors.py -q
```
Expected: 10 passed. If a `pass` vector fails on bytes: run `python -c "from ison_graph import ISONGraph;print(repr(ISONGraph.from_ison(open('../vectors/ids/<name>.ison',encoding='utf-8',newline='').read()).to_ison()))"`. If the only difference is row/column order or quoting, the file was not canonical: replace the file with that output plus `\n` (Python is the reference writer). If the difference is semantic (a value changed type or sign), that is a Core defect: set the cell to the observed grammar value and add a row to the README Findings table — do not change the file.

- [ ] **Step 4: Commit**

```bash
cd .. && git add vectors && git commit -F - <<'EOF'
Add the id vectors: sign, type and twin behaviour on the wire

Positive, negative, numeric-string and int64-extreme ids round-trip;
int/string twins and float/bool ids are refused as 1.4.1 promises.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 3: `values/` vectors

**Files:**
- Create: `vectors/values/int-vs-integral-float.ison`, `negative-zero.ison`, `fractional-float.ison`, `int64-extreme-values.ison`, `int-beyond-int64.ison`, `nonfinite-as-text.ison`, `nonfinite-as-text.canonical.ison`, `null-elision.ison`, `nfd-vs-nfc.ison`, `string-looks-typed.ison`, `quoting.ison`
- Modify: `vectors/manifest.ison` (append 10 rows)

- [ ] **Step 1: Write the files**

```python
from pathlib import Path
V = Path("vectors"); (V / "values").mkdir(exist_ok=True)
def w(rel, text): (V / rel).write_bytes(text.encode("utf-8"))

w("values/int-vs-integral-float.ison", "nodes.p\nid x\n1 1\n2 1.0\n")
w("values/negative-zero.ison", "nodes.p\nid x\n1 -0.0\n")
w("values/fractional-float.ison", "nodes.p\nid x\n1 1.5\n2 2.25\n3 0.1\n")
w("values/int64-extreme-values.ison", "nodes.p\nid x\n1 9223372036854775807\n2 -9223372036854775808\n")
w("values/int-beyond-int64.ison", "nodes.p\nid x\n1 100000000000000000000\n")
# Bare nan/inf on the wire are STRINGs. ison-py's writer quotes them back
# out (they would otherwise reparse as floats in some readers); the
# canonical sibling is that quoted form.
w("values/nonfinite-as-text.ison", "nodes.p\nid x\n1 nan\n2 inf\n")
w("values/nonfinite-as-text.canonical.ison", "nodes.p\nid x\n1 \"nan\"\n2 \"inf\"\n")
w("values/null-elision.ison", "nodes.p\nid x\n1 null\n2 1\n")
# U+0065 U+0301 (decomposed) vs U+00E9 (precomposed): distinct values.
w("values/nfd-vs-nfc.ison", "nodes.p\nid x\n1 e\u0301\n2 \u00e9\n")
w("values/string-looks-typed.ison", "nodes.p\nid x\n1 \"true\"\n2 \"1\"\n3 \"1.5\"\n4 \"null\"\n")
w("values/quoting.ison", "nodes.d\nid a b c d e f\n1 \"Hello World\" a|b \"say \\\"hi\\\"\" \"l1\\nl2\" \"\" \"#x\"\n")
print("ok")
```

- [ ] **Step 2: Append the predicted rows**

```
values/int-vs-integral-float values/int-vs-integral-float.ison identifiable null true 2 0 null null pass todo todo todo todo todo
values/negative-zero values/negative-zero.ison identifiable null true 1 0 null null pass todo todo todo todo todo
values/fractional-float values/fractional-float.ison identifiable null true 3 0 null null pass todo todo todo todo todo
values/int64-extreme-values values/int64-extreme-values.ison identifiable null true 2 0 null null pass todo todo todo todo todo
values/int-beyond-int64 values/int-beyond-int64.ison out_of_domain INTEGER_OUT_OF_INT64 true 1 0 null null pass todo todo todo todo todo
values/nonfinite-as-text values/nonfinite-as-text.ison identifiable null true 2 0 values/nonfinite-as-text.canonical.ison null "pass:canonicalized" todo todo todo todo todo
values/null-elision values/null-elision.ison identifiable null true 2 0 null null pass todo todo todo todo todo
values/nfd-vs-nfc values/nfd-vs-nfc.ison identifiable null true 2 0 null null pass todo todo todo todo todo
values/string-looks-typed values/string-looks-typed.ison identifiable null true 4 0 null null pass todo todo todo todo todo
values/quoting values/quoting.ison identifiable null true 1 0 null null pass todo todo todo todo todo
```

- [ ] **Step 3: Run the runner; resolve by the Task 2 Step 3 rule**

```bash
cd ison-graph && python -m pytest tests/test_vectors.py -q
```
Expected: 20 passed. Known non-obvious points: `nonfinite-as-text` must pass via its canonical sibling (observed on 1.4.1: Python writes `"nan"` quoted); `nfd-vs-nfc` must come back with both values distinct — if the meta-test reports invalid UTF-8 the file was written through a non-UTF-8 editor, rewrite it with the snippet.

- [ ] **Step 4: Commit**

```bash
cd .. && git add vectors && git commit -F - <<'EOF'
Add the value vectors: numeric normal form, null, Unicode and quoting

Pins what the wire carries for 1 vs 1.0, -0.0, int64 edges and beyond,
bare nan/inf (strings, which ison-py quotes back out), null elision,
NFD vs NFC (kept distinct), typed-looking strings and the quoting rules.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 4: `structure/` vectors (includes the first `defect` placeholder rule check)

**Files:**
- Create: `vectors/structure/directed-two-way.ison`, `undirected-basic.ison`, `undirected-mirror-conflict.ison`, `directed-duplicate-row.ison`, `explicit-directed-true.ison`, `explicit-directed-true.canonical.ison`, `self-loop.ison`, `multigraph-document.ison`, `unknown-block-kind.ison`, `unknown-block-kind.canonical.ison`, `empty.ison`
- Modify: `vectors/manifest.ison` (append 9 rows)

- [ ] **Step 1: Write the files**

```python
from pathlib import Path
V = Path("vectors"); (V / "structure").mkdir(exist_ok=True)
def w(rel, text): (V / rel).write_bytes(text.encode("utf-8"))

w("structure/directed-two-way.ison", "edges.R\nsource target\n:p:1 :p:2\n:p:2 :p:1\n\nnodes.p\nid\n1\n2\n")
w("structure/undirected-basic.ison", "edges.R\nsource target w\n:p:1 :p:2 1\n:p:2 :p:1 1\n\nmeta.graph\ndirected\nfalse\n\nnodes.p\nid\n1\n2\n")
# Same logical edge stored twice with different w: Semantic/2 calls this a
# conflict; Core keeps the first mirror, so canonical == undirected-basic.
w("structure/undirected-mirror-conflict.ison", "edges.R\nsource target w\n:p:1 :p:2 1\n:p:2 :p:1 2\n\nmeta.graph\ndirected\nfalse\n\nnodes.p\nid\n1\n2\n")
w("structure/directed-duplicate-row.ison", "edges.R\nsource target\n:p:1 :p:2\n:p:1 :p:2\n\nnodes.p\nid\n1\n2\n")
w("structure/explicit-directed-true.ison", "meta.graph\ndirected\ntrue\n\nnodes.p\nid\n1\n")
w("structure/explicit-directed-true.canonical.ison", "nodes.p\nid\n1\n")
w("structure/self-loop.ison", "edges.R\nsource target\n:p:1 :p:1\n\nnodes.p\nid\n1\n")
w("structure/multigraph-document.ison", "edges.R\nkey source target\n0 :p:1 :p:1\n\nmeta.graph\ndirected format version\ntrue ison-graph-multigraph-v1 1\n\nnodes.p\nid\n1\n")
w("structure/unknown-block-kind.ison", "table.x\na\n1\n\nnodes.p\nid\n1\n")
w("structure/unknown-block-kind.canonical.ison", "nodes.p\nid\n1\n")
w("structure/empty.ison", "\n")
print("ok")
```

- [ ] **Step 2: Append the predicted rows**

```
structure/directed-two-way structure/directed-two-way.ison identifiable null true 2 2 null null pass todo todo todo todo todo
structure/undirected-basic structure/undirected-basic.ison identifiable null false 2 2 null null pass todo todo todo todo todo
structure/undirected-mirror-conflict structure/undirected-mirror-conflict.ison out_of_domain UNDIRECTED_EDGE_CONFLICT false 2 2 structure/undirected-basic.ison null "pass:canonicalized" todo todo todo todo todo
structure/directed-duplicate-row structure/directed-duplicate-row.ison out_of_domain INVALID_EDGE_ADDRESS true 0 0 null null "reject:DuplicateEdgeError" todo todo todo todo todo
structure/explicit-directed-true structure/explicit-directed-true.ison identifiable null true 1 0 structure/explicit-directed-true.canonical.ison null "pass:canonicalized" todo todo todo todo todo
structure/self-loop structure/self-loop.ison identifiable null true 1 1 null null pass todo todo todo todo todo
structure/multigraph-document structure/multigraph-document.ison out_of_domain MULTIGRAPH_DOCUMENT true 1 1 null null "reject:ValueError" todo todo todo todo todo
```
(`nodes 1 edges 1` are what the *defective* TS/JS reading produces - a `defect` cell pins them; Python rejects and ignores them.)
```
structure/unknown-block-kind structure/unknown-block-kind.ison identifiable null true 1 0 structure/unknown-block-kind.canonical.ison null "pass:canonicalized" todo todo todo todo todo
structure/empty structure/empty.ison identifiable null true 0 0 null null pass todo todo todo todo todo
```

- [ ] **Step 3: Run the runner; resolve by the Task 2 Step 3 rule**

```bash
cd ison-graph && python -m pytest tests/test_vectors.py -q
```
Expected: 29 passed. `structure/empty` loads `"\n"` as zero blocks and emits `""`, so `"" + "\n"` equals the file. `multigraph-document` must be `reject:ValueError` in Python (`_reject_if_multigraph`).

- [ ] **Step 4: Commit**

```bash
cd .. && git add vectors && git commit -F - <<'EOF'
Add the structure vectors: directedness, mirrors, duplicates, foreign blocks

Directed two-way vs undirected mirror pairs no longer share bytes; a
mirror pair with conflicting properties is kept as the first mirror; an
explicit 'directed true' and an unknown block kind canonicalize away; a
MultiGraph document is refused by the simple graph.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 5: `serialization/` vectors (non-canonical input, ISONL twins)

**Files:**
- Create: `vectors/serialization/non-canonical-order.ison`, `non-canonical-order.canonical.ison`, `undirected-basic.isonl`, `negative-int.isonl`
- Modify: `vectors/manifest.ison` (append 3 rows)

- [ ] **Step 1: Write the files**

```python
from pathlib import Path
V = Path("vectors"); (V / "serialization").mkdir(exist_ok=True)
def w(rel, text): (V / rel).write_bytes(text.encode("utf-8"))

w("serialization/non-canonical-order.ison", "nodes.p\nname id\nBob 2\nAlice 1\n\nedges.R\ntarget source\n:p:2 :p:1\n")
w("serialization/non-canonical-order.canonical.ison", "edges.R\nsource target\n:p:1 :p:2\n\nnodes.p\nid name\n1 Alice\n2 Bob\n")
w("serialization/undirected-basic.isonl", "edges.R|source target w|:p:1 :p:2 1\nedges.R|source target w|:p:2 :p:1 1\nmeta.graph|directed|false\nnodes.p|id|1\nnodes.p|id|2\n")
w("serialization/negative-int.isonl", "edges.R|source target|:p:-1 :p:2\nedges.R|source target|:p:2 :p:-1\nnodes.p|id|-1\nnodes.p|id|2\n")
print("ok")
```

- [ ] **Step 2: Append the predicted rows**

```
serialization/non-canonical-order serialization/non-canonical-order.ison identifiable null true 2 1 serialization/non-canonical-order.canonical.ison null "pass:canonicalized" todo todo todo todo todo
serialization/undirected-basic-isonl serialization/undirected-basic.isonl identifiable null false 2 2 structure/undirected-basic.ison null "pass:canonicalized" todo todo todo todo todo
serialization/negative-int-isonl serialization/negative-int.isonl identifiable null true 2 2 ids/negative-int.ison null "pass:canonicalized" todo todo todo todo todo
```

- [ ] **Step 3: Run the runner; resolve by the Task 2 Step 3 rule**

```bash
cd ison-graph && python -m pytest tests/test_vectors.py -q
```
Expected: 32 passed (31 vectors + meta-test).

- [ ] **Step 4: Run the whole Python suite and commit**

```bash
python -m pytest -q      # expected: 530 passed
cd .. && git add vectors && git commit -F - <<'EOF'
Add the serialization vectors: canonical ordering and ISONL twins

A deliberately unsorted document canonicalizes to its sibling, and the
ISONL spelling of two existing vectors loads to the same canonical ISON.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 6: TypeScript runner and the `ts` column

**Files:**
- Create: `ison-graph-ts/src/vectors.test.ts`
- Modify: `vectors/manifest.ison` (replace every `ts` cell)
- Modify: `vectors/README.md` (Findings rows as observed)

**Interfaces:**
- Consumes: `ISONGraph.fromIson/fromIsonl/toIson/nodeCount/edgeCount/directed` from `./index`; `parse` from `ison-ts`.

- [ ] **Step 1: Write the runner**

Create `ison-graph-ts/src/vectors.test.ts`:

```ts
/**
 * Core Conformance Corpus runner for the TypeScript port.
 * Reads vectors/manifest.ison with ison-ts and checks the 'ts' column.
 * Grammar and columns: vectors/README.md.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'ison-ts';
import { ISONGraph } from './index';

const VECTORS = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'vectors');
const PORT = 'ts';

type Row = Record<string, any>;

const read = (rel: string): string => readFileSync(resolve(VECTORS, rel), 'utf8');
const rows: Row[] = parse(read('manifest.ison')).blocks
  .filter((b: any) => b.kind === 'table' && b.name === 'vectors')
  .flatMap((b: any) => b.rows as Row[]);
const load = (rel: string, text: string): ISONGraph =>
  rel.endsWith('.isonl') ? ISONGraph.fromIsonl(text) : ISONGraph.fromIson(text);
const emit = (g: ISONGraph): string => g.toIson() + '\n';

describe('Core Conformance Corpus (ts)', () => {
  it('manifest has rows', () => {
    expect(rows.length).toBeGreaterThan(0);
  });

  it('is admitted: no todo in its column', () => {
    expect(rows.filter(r => r[PORT] === 'todo').map(r => r.id)).toEqual([]);
  });

  describe.each(rows.map(r => [r.id as string, r] as const))('%s', (_id, row) => {
    it('behaves as the manifest says', () => {
      const expectation = row[PORT] as string;
      const text = read(row.file);

      if (expectation.startsWith('reject:')) {
        let name = '';
        try {
          load(row.file, text);
        } catch (e: any) {
          name = e.name ?? e.constructor.name;
        }
        expect(name).toBe(expectation.slice('reject:'.length));
        return;
      }
      const g = load(row.file, text);
      expect(g.directed).toBe(row.directed);
      expect(g.nodeCount()).toBe(row.nodes);
      expect(g.edgeCount()).toBe(row.edges);

      const out = emit(g);
      if (expectation === 'defect') {
        // Contradicts the spec (README Findings) - pin what the port does.
        expect(emit(ISONGraph.fromIson(out))).toBe(out);
      } else if (expectation === 'pass') {
        expect(out).toBe(text);
      } else if (expectation === 'pass:canonicalized') {
        expect(out).toBe(read(row.canonical));
        expect(emit(ISONGraph.fromIson(out))).toBe(out);
      } else if (expectation === 'pass:lossy') {
        expect(emit(ISONGraph.fromIson(out))).toBe(out);
      } else {
        throw new Error(`unknown expectation ${JSON.stringify(expectation)} for ${PORT}`);
      }
    });
  });
});
```

- [ ] **Step 2: Run it once with the column still `todo` — expect only the admission test to fail**

```bash
cd ison-graph-ts && npx vitest run src/vectors.test.ts
```
Expected: `is admitted` FAILS (lists all 31 ids); every per-vector test FAILS with `unknown expectation "todo"`. This confirms the runner reads the manifest.

- [ ] **Step 3: Set the `ts` column from the predictions, then correct from observation**

Replace the `ts` cell (10th value) of every row with the prediction below, run `npx vitest run src/vectors.test.ts`, and for each failure apply the rule: if the port's output is a legitimate canonical form that merely differs from Python's writer → `pass:canonicalized` only if it equals the `canonical` file, otherwise it is a writer divergence → keep the Python-canonical file, set the cell to what the behaviour *is* (`pass:lossy` when the port stabilises, `defect` when it contradicts the spec, `reject:<Name>` when it throws), and add a Findings row. Never edit a vector file to make TS pass.

Predicted `ts` cells (already observed on 1.4.1 where marked ✓):

```
ids/positive-int                 pass
ids/twin-int-string              reject:DuplicateNodeError   ✓
ids/negative-int                 pass
ids/string-numeric               pass
ids/string-negative              pass
ids/int64-extremes               pass:lossy                  ✓ (ids become 9223372036854776000)
ids/twin-negative                reject:DuplicateNodeError
ids/float-id                     reject:InvalidIdentifierError ✓
ids/bool-id                      reject:InvalidIdentifierError
values/int-vs-integral-float     pass:lossy                  ✓ (1.0 -> 1)
values/negative-zero             pass                        ✓ (-0.0 preserved)
values/fractional-float          pass
values/int64-extreme-values      pass:lossy                  ✓
values/int-beyond-int64          pass                        ✓
values/nonfinite-as-text         pass                        ✓ (ison-ts writes nan bare; Python quotes it -> Findings: writer divergence)
values/null-elision              pass
values/nfd-vs-nfc                pass
values/string-looks-typed        pass                        (observe quoting of "true"/"null")
values/quoting                   pass                        (observe)
structure/directed-two-way       pass
structure/undirected-basic       pass
structure/undirected-mirror-conflict  pass:canonicalized
structure/directed-duplicate-row reject:DuplicateEdgeError
structure/explicit-directed-true pass:canonicalized
structure/self-loop              pass
structure/multigraph-document    defect                      ✓ (loads; key becomes a property) -> Findings
structure/unknown-block-kind     pass:canonicalized          ✓
structure/empty                  pass                        ✓
serialization/non-canonical-order     pass:canonicalized
serialization/undirected-basic-isonl  pass:canonicalized
serialization/negative-int-isonl      pass:canonicalized
```

Findings rows to add to `vectors/README.md` (append under the table header; `status` is `open` until a Core fix ships):

```
| structure/multigraph-document | ts, js | loads the document and treats `key` as an edge property | Python, Rust, C# and C++ refuse an `ison-graph-multigraph-v1` document | open - CORE_BLOCKING_DIVERGENCE |
| values/nonfinite-as-text | ts, js | writer emits the strings `nan` / `inf` bare | ison-py quotes them (`"nan"`), so the same graph has two canonical byte forms | open - ISONCS writer divergence, needs an ison-ts/ison-js decision |
| ids/int64-extremes | ts, js | ids beyond 2^53 are read as binary64 and re-emitted rounded | 13-SEMANTIC-2 §1.2 JS binding rule: such input must arrive as BigInt or an exact integer token | known limitation - pass:lossy |
| values/int64-extreme-values | ts, js | as above for property values | as above | known limitation - pass:lossy |
| values/int-vs-integral-float | ts, js | `1.0` is re-emitted as `1` | CHANGELOG 1.4.0 known limitation; Semantic/2 treats both as INT64(1) | known limitation - pass:lossy |
```

(Add a row only when the observation is confirmed by the run; delete a predicted row that does not reproduce.)

- [ ] **Step 4: Run TS + Python; both must be green**

```bash
npx vitest run                       # expected: 221 + 33 = 254 passed
npx tsc --noEmit -p .                # expected: no output
cd ../ison-graph && python -m pytest tests/test_vectors.py -q   # meta-test now requires ts != todo
```

- [ ] **Step 5: Commit**

```bash
cd .. && git add vectors ison-graph-ts/src/vectors.test.ts && git commit -F - <<'EOF'
Admit the TypeScript port to the conformance corpus

Same runner shape as Python, reading the manifest with ison-ts. Setting
the ts column from what the port does today records three things worth
knowing: it loads a MultiGraph document that every other port refuses,
ison-ts writes the string "nan" bare where ison-py quotes it, and ids or
values beyond 2^53 come back rounded. Each is in README Findings.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 7: JavaScript runner and the `js` column

**Files:**
- Create: `ison-graph-js/src/vectors.test.js`
- Modify: `vectors/manifest.ison` (replace every `js` cell)
- Modify: `vectors/README.md` (Findings `ports` cells already say `ts, js`; confirm)

- [ ] **Step 1: Write the runner**

Create `ison-graph-js/src/vectors.test.js`:

```js
/**
 * Core Conformance Corpus runner for the JavaScript port.
 * Reads vectors/manifest.ison with ison-parser and checks the 'js' column.
 * Grammar and columns: vectors/README.md.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loads as parse } from 'ison-parser';
import { ISONGraph } from './index.js';

const VECTORS = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'vectors');
const PORT = 'js';

const read = (rel) => readFileSync(resolve(VECTORS, rel), 'utf8');
const rows = parse(read('manifest.ison')).blocks
  .filter((b) => b.kind === 'table' && b.name === 'vectors')
  .flatMap((b) => b.rows);
const load = (rel, text) =>
  rel.endsWith('.isonl') ? ISONGraph.fromIsonl(text) : ISONGraph.fromIson(text);
const emit = (g) => g.toIson() + '\n';

describe('Core Conformance Corpus (js)', () => {
  it('manifest has rows', () => {
    expect(rows.length).toBeGreaterThan(0);
  });

  it('is admitted: no todo in its column', () => {
    expect(rows.filter((r) => r[PORT] === 'todo').map((r) => r.id)).toEqual([]);
  });

  describe.each(rows.map((r) => [r.id, r]))('%s', (_id, row) => {
    it('behaves as the manifest says', () => {
      const expectation = row[PORT];
      const text = read(row.file);

      if (expectation.startsWith('reject:')) {
        let name = '';
        try {
          load(row.file, text);
        } catch (e) {
          name = e.name ?? e.constructor.name;
        }
        expect(name).toBe(expectation.slice('reject:'.length));
        return;
      }
      const g = load(row.file, text);
      expect(g.directed).toBe(row.directed);
      expect(g.nodeCount()).toBe(row.nodes);
      expect(g.edgeCount()).toBe(row.edges);

      const out = emit(g);
      if (expectation === 'defect') {
        // Contradicts the spec (README Findings) - pin what the port does.
        expect(emit(ISONGraph.fromIson(out))).toBe(out);
      } else if (expectation === 'pass') {
        expect(out).toBe(text);
      } else if (expectation === 'pass:canonicalized') {
        expect(out).toBe(read(row.canonical));
        expect(emit(ISONGraph.fromIson(out))).toBe(out);
      } else if (expectation === 'pass:lossy') {
        expect(emit(ISONGraph.fromIson(out))).toBe(out);
      } else {
        throw new Error(`unknown expectation ${JSON.stringify(expectation)} for ${PORT}`);
      }
    });
  });
});
```

- [ ] **Step 2: Set the `js` column** — copy the final `ts` cells from Task 6 as the prediction (the two ports share one writer design), run `cd ison-graph-js && npx vitest run src/vectors.test.js`, and correct from observation by the Task 6 Step 3 rule. Any JS-only difference from TS is itself a Findings row (`ports: js`).

- [ ] **Step 3: Run JS + Python**

```bash
npx vitest run                        # expected: 221 + 33 = 254 passed
cd ../ison-graph && python -m pytest tests/test_vectors.py -q
```

- [ ] **Step 4: Commit**

```bash
cd .. && git add vectors ison-graph-js/src/vectors.test.js && git commit -F - <<'EOF'
Admit the JavaScript port to the conformance corpus

Mirror of the TypeScript runner against ison-parser. The js column
matches ts everywhere, which is the point: the two ports share one
writer design and the corpus now proves it per document.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 8: `scripts/corpus_digest.py`

**Files:**
- Create: `scripts/corpus_digest.py`
- Create: `ison-graph/tests/test_corpus_scripts.py`

**Interfaces:**
- Produces: `corpus_digest(root: Path) -> str` (64-char lowercase hex). CLI: `python scripts/corpus_digest.py [vectors-dir]` prints the hex.

- [ ] **Step 1: Write the failing tests**

Create `ison-graph/tests/test_corpus_scripts.py`:

```python
"""Tests for the repo-level corpus scripts (scripts/corpus_digest.py and
scripts/corpus_receipt.py). They live outside the package, so they are
imported by path."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _import(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


digest_mod = _import("corpus_digest")


def _make(tmp_path: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return tmp_path


def test_digest_is_sha256_over_sorted_path_and_bytes(tmp_path):
    root = _make(tmp_path, {"b/two.ison": b"2\n", "a.ison": b"1\n"})
    expected = hashlib.sha256(b"a.ison\0" + b"1\n" + b"\0" + b"b/two.ison\0" + b"2\n" + b"\0").hexdigest()
    assert digest_mod.corpus_digest(root) == expected


def test_digest_ignores_creation_order(tmp_path):
    a = _make(tmp_path / "x", {"a.ison": b"1\n", "b.ison": b"2\n"})
    b = _make(tmp_path / "y", {"b.ison": b"2\n", "a.ison": b"1\n"})
    assert digest_mod.corpus_digest(a) == digest_mod.corpus_digest(b)


def test_digest_changes_when_a_byte_changes(tmp_path):
    root = _make(tmp_path, {"a.ison": b"1\n"})
    before = digest_mod.corpus_digest(root)
    (root / "a.ison").write_bytes(b"1 \n")
    assert digest_mod.corpus_digest(root) != before


def test_real_corpus_digest_is_stable_across_two_calls():
    d1 = digest_mod.corpus_digest(ROOT / "vectors")
    d2 = digest_mod.corpus_digest(ROOT / "vectors")
    assert d1 == d2 and len(d1) == 64
```

- [ ] **Step 2: Run to verify failure**

```bash
cd ison-graph && python -m pytest tests/test_corpus_scripts.py -q
```
Expected: ERROR at import — `FileNotFoundError: scripts/corpus_digest.py`.

- [ ] **Step 3: Write the script**

Create `scripts/corpus_digest.py`:

```python
#!/usr/bin/env python3
"""Print the digest ISONGraphExt pins as core_vector_corpus_digest.

    sha256( concat over sorted relative paths of: path + "\\0" + bytes + "\\0" )

Sorted by POSIX relative path so the result is the same on every platform
and independent of checkout order. Usage:

    python scripts/corpus_digest.py            # defaults to <repo>/vectors
    python scripts/corpus_digest.py some/dir
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def corpus_digest(root: Path) -> str:
    h = hashlib.sha256()
    # Sort by the exact key that is hashed - the POSIX relative path - so the
    # order never depends on platform path semantics or Path ordering rules.
    files = sorted(
        (p for p in root.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        h.update(rel + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "vectors"
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    print(corpus_digest(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

Note: `sorted(Path)` orders by path components; `rglob` of `vectors/` contains no directories we want to skip. If a future `__pycache__` appears there, the meta-test's "every file referenced" rule will not catch it — keep scripts out of `vectors/`.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_corpus_scripts.py -q      # expected: 4 passed
python ../scripts/corpus_digest.py                    # expected: a 64-hex line
```

- [ ] **Step 5: Commit**

```bash
cd .. && git add scripts/corpus_digest.py ison-graph/tests/test_corpus_scripts.py && git commit -F - <<'EOF'
Add the corpus digest ISONGraphExt pins

SHA-256 over the sorted (path, bytes) of vectors/**, so a consumer can
state exactly which corpus it was proven against without copying it.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 9: `scripts/corpus_receipt.py` — the Core Conformance Receipt

**Files:**
- Create: `scripts/corpus_receipt.py`
- Modify: `ison-graph/tests/test_corpus_scripts.py` (append tests)

**Interfaces:**
- Consumes: `corpus_digest(root)` from Task 8.
- Produces: `posture(cells: list[str], runner_exists: bool) -> str`; `build_receipt(root: Path, port: str) -> dict`; CLI `python scripts/corpus_receipt.py --port python` prints ISON.

- [ ] **Step 1: Append failing tests**

Append to `ison-graph/tests/test_corpus_scripts.py`:

```python
receipt_mod = _import("corpus_receipt")


@pytest.mark.parametrize("cells,runner,expected", [
    (["pass", "reject:X", "pass:canonicalized"], True, "FULL"),
    (["pass", "pass:lossy"], True, "LOSSY_KNOWN"),
    (["pass", "defect"], True, "KNOWN_DEFECT"),
    (["pass:lossy", "defect"], True, "KNOWN_DEFECT"),
    (["todo", "todo"], False, "PARTIAL"),
    (["pass", "todo"], True, "INCONCLUSIVE"),
    (["pass"], False, "INCONCLUSIVE"),
])
def test_posture(cells, runner, expected):
    assert receipt_mod.posture(cells, runner) == expected


def test_receipt_for_python_is_full_and_counts_add_up():
    r = receipt_mod.build_receipt(ROOT, "python")
    assert r["port"] == "python"
    assert r["core_format"] == "isongraph"
    assert r["semantic_spec"] == "ISONGraph-Semantic/2-draft"
    assert r["corpus_version"] == 1
    assert len(r["corpus_digest"]) == 64
    assert re.fullmatch(r"[0-9a-f]{40}", r["core_commit"])
    assert re.fullmatch(r"[0-9a-f]{40}", r["corpus_commit"])
    assert r["posture"] == "FULL"
    assert r["total"] == r["pass"] + r["canonicalized"] + r["lossy"] + r["defect"] + r["rejected_as_expected"] + r["todo"]
    assert r["todo"] == 0


def test_receipt_for_ts_is_known_defect():
    r = receipt_mod.build_receipt(ROOT, "ts")
    assert r["posture"] == "KNOWN_DEFECT"
    assert r["defect"] >= 1 and r["lossy"] >= 1


def test_receipt_for_rust_is_partial():
    r = receipt_mod.build_receipt(ROOT, "rust")
    assert r["posture"] == "PARTIAL" and r["todo"] == r["total"]


def test_receipt_cli_prints_ison(capsys):
    assert receipt_mod.main(["corpus_receipt.py", "--port", "python"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("meta.core_conformance_receipt\n")
    assert " FULL" in out
```

- [ ] **Step 2: Run to verify failure**

```bash
cd ison-graph && python -m pytest tests/test_corpus_scripts.py -q
```
Expected: ERROR — `scripts/corpus_receipt.py` not found.

- [ ] **Step 3: Write the script**

Create `scripts/corpus_receipt.py`:

```python
#!/usr/bin/env python3
"""Emit the Core Conformance Receipt for one port, as ISON.

The receipt is computed from vectors/manifest.ison - whose expectations are
observed behaviour by the corpus rules - plus the port's declared version
and the repo's git state. The port's runner is what makes the manifest
trustworthy, so a receipt is only meaningful for a commit whose CI is
green. Posture is derived, never hand-set:

    FULL          runner exists, no todo, no pass:lossy, no defect
    LOSSY_KNOWN   runner exists, no todo, no defect, some pass:lossy
    KNOWN_DEFECT  runner exists, no todo, some defect (contradicts the spec)
    PARTIAL       no runner (every cell todo)
    INCONCLUSIVE  manifest and runner disagree about admission

Commits are full SHAs: the receipt is a long-lived pin.

Usage:
    python scripts/corpus_receipt.py --port python
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical, loads

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_digest import corpus_digest  # noqa: E402

RUNNERS = {
    "python": "ison-graph/tests/test_vectors.py",
    "ts": "ison-graph-ts/src/vectors.test.ts",
    "js": "ison-graph-js/src/vectors.test.js",
    "rust": "ison-graph-rs/tests/vectors.rs",
    "cs": "ison-graph-cs/tests/IsonGraph.Tests/VectorsTests.cs",
    "cpp": "ison-graph-cpp/tests/test_vectors.cpp",
}

VERSION_FILES = {
    "python": ("ison-graph/pyproject.toml", r'^version = "([^"]+)"'),
    "ts": ("ison-graph-ts/package.json", None),
    "js": ("ison-graph-js/package.json", None),
    "rust": ("ison-graph-rs/Cargo.toml", r'^version = "([^"]+)"'),
    "cs": ("ison-graph-cs/src/IsonGraph/IsonGraph.csproj", r"<Version>([^<]+)</Version>"),
    "cpp": ("ison-graph-cpp/CMakeLists.txt", r"VERSION ([0-9.]+) "),
}


def posture(cells: list[str], runner_exists: bool) -> str:
    todo = sum(c == "todo" for c in cells)
    if not runner_exists:
        return "PARTIAL" if todo == len(cells) else "INCONCLUSIVE"
    if todo:
        return "INCONCLUSIVE"
    if any(c == "defect" for c in cells):
        return "KNOWN_DEFECT"
    if any(c == "pass:lossy" for c in cells):
        return "LOSSY_KNOWN"
    return "FULL"


def port_version(root: Path, port: str) -> str:
    rel, pattern = VERSION_FILES[port]
    text = (root / rel).read_text(encoding="utf-8")
    if pattern is None:
        return json.loads(text)["version"]
    m = re.search(pattern, text, flags=re.M)
    if not m:
        raise SystemExit(f"no version in {rel}")
    return m.group(1)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def build_receipt(root: Path, port: str) -> dict:
    manifest = loads((root / "vectors" / "manifest.ison").read_text(encoding="utf-8"))
    meta = next(b for b in manifest.blocks if b.kind == "meta" and b.name == "corpus").rows[0]
    rows = [r for b in manifest.blocks if b.kind == "table" and b.name == "vectors" for r in b.rows]
    cells = [r[port] for r in rows]
    runner_exists = (root / RUNNERS[port]).is_file()
    return {
        "core_format": "isongraph",
        "core_version": port_version(root, "python"),
        "core_commit": git(root, "rev-parse", "HEAD"),
        "semantic_spec": meta["semantic_spec"],
        "corpus_version": meta["version"],
        "corpus_commit": git(root, "log", "-1", "--format=%H", "--", "vectors") or git(root, "rev-parse", "HEAD"),
        "corpus_digest": corpus_digest(root / "vectors"),
        "port": port,
        "port_version": port_version(root, port),
        "total": len(cells),
        "pass": sum(c == "pass" for c in cells),
        "canonicalized": sum(c == "pass:canonicalized" for c in cells),
        "lossy": sum(c == "pass:lossy" for c in cells),
        "defect": sum(c == "defect" for c in cells),
        "rejected_as_expected": sum(c.startswith("reject:") for c in cells),
        "todo": sum(c == "todo" for c in cells),
        "posture": posture(cells, runner_exists),
    }


def to_ison(receipt: dict) -> str:
    block = Block(kind="meta", name="core_conformance_receipt", fields=list(receipt), rows=[receipt])
    return dumps_canonical(Document(blocks=[block]))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, choices=sorted(RUNNERS))
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv[1:])
    print(to_ison(build_receipt(Path(args.root), args.port)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

Note on `dumps_canonical`: it sorts fields within the block, so the printed column order is alphabetical, not the dict order; the test only asserts the header line and the posture token. If `Block(...)` rejects keyword construction in the installed ison-py, construct it the way `ison_graph/__init__.py` does in `_document()` (`Block(kind=..., name=..., fields=[...], rows=[...])` — that form is in use there, so it works).

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_corpus_scripts.py -q       # expected: 14 passed
python ../scripts/corpus_receipt.py --port ts           # eyeball: posture KNOWN_DEFECT, lossy >= 1, defect 1
```

- [ ] **Step 5: Commit**

```bash
cd .. && git add scripts/corpus_receipt.py ison-graph/tests/test_corpus_scripts.py && git commit -F - <<'EOF'
Emit a Core Conformance Receipt per port

A corpus digest says which corpus a port was proven against, not how it
did. The receipt adds the port's posture - FULL, LOSSY_KNOWN, PARTIAL or
INCONCLUSIVE - derived from the manifest it is bound to, with the counts
behind it, so a downstream consumer can refuse identity claims through a
lossy port instead of discovering the loss later.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
```

---

### Task 10: README, changelog, final verification, PR

**Files:**
- Modify: `vectors/README.md` (full content)
- Modify: `CHANGELOG.md` (add `[Unreleased]` section above `## [1.4.1]`)

- [ ] **Step 1: Write the full `vectors/README.md`** — keep the Findings table exactly as it stands after Tasks 6–7 (the meta-test depends on its rows); replace everything above it with:

```markdown
# ISONGraph Core Conformance Corpus

Executable vectors proving **"same document → same meaning in every port"**.
Owned by Core. ISONGraphExt, ISONGraph Visualize and products consume it at a
pinned commit through the Core Conformance Receipt; they never copy or fork
it. A missing vector is added here.

## What it tests

Documents. Each vector is an ISON or ISONL text; each port loads it, checks
directedness and counts, writes it back and compares bytes. Construction-time
API refusals (NaN at `add_node`, float ids, property-name rules) cannot be
carried on the wire and are each port's unit tests, not this corpus.

Expected Semantic/2 digests are not yet included; the `digest` column is
reserved and `null`.

## Layout

    manifest.ison       the only index; every port parses it with its own ISON parser
    ids/ values/ structure/ serialization/
    ../scripts/corpus_digest.py    sha256 over sorted (path, bytes) of vectors/**
    ../scripts/corpus_receipt.py   per-port Core Conformance Receipt

Every file is UTF-8 without BOM, LF-only, ending in exactly one newline; the
`.gitattributes` rule `vectors/** text eol=lf` keeps it so on every platform.
Comparison is always `to_ison() + "\n"` against the file. A file ending in
`.isonl` is loaded with `from_isonl`.

## Manifest columns

| column | meaning |
|---|---|
| `id` | `<group>/<name>`, unique |
| `file` | path relative to this directory |
| `semantic` | `identifiable` or `out_of_domain` under ISONGraph-Semantic/2 |
| `reason` | why out of domain; `null` when identifiable |
| `directed` | expected `graph.directed` after load |
| `nodes`, `edges` | expected counts after load; `edges` counts stored records (an undirected edge counts 2) |
| `canonical` | sibling file holding the canonical output when the input is deliberately non-canonical; set iff some port is `pass:canonicalized` |
| `digest` | reserved; `null` |
| `python` `ts` `js` `rust` `cs` `cpp` | per-port expectation, below |

## Per-port expectation grammar

| value | the runner checks |
|---|---|
| `pass` | loads; directed and counts match; output is byte-identical to the file |
| `pass:canonicalized` | loads; counts match; output equals the `canonical` file and is idempotent |
| `pass:lossy` | loads; counts match; output differs for a documented port limitation; idempotent |
| `defect` | loads without raising but contradicts the spec; directed and counts are pinned to what the port does and output must be idempotent; a Findings row below must name the vector |
| `reject:<ErrorName>` | loading raises that port's error class of that name |
| `todo` | no runner for this port yet |

Rules. Expectations are set from **observed** behaviour of the released port;
an observation that contradicts Semantic/2 becomes a Findings row, never a
weakened vector. **Port runner admission is atomic**: a column contains
`todo` iff the port's runner file is absent, so a port is either fully in or
not in. **Three postures never collapse**: `python = pass` on
`values/int-beyond-int64` says the port loads it; `semantic = out_of_domain`
says Semantic/2 assigns it no identity. `pass:lossy` is not conformance — a
consumer needing cross-port identity treats that port as `CORE_LOSSY` for the
input.

## Receipt

`python scripts/corpus_receipt.py --port <name>` prints one `meta.core_conformance_receipt`
row: core commit and version, semantic spec, corpus version/commit/digest,
port and version, the counts per expectation kind, and the derived posture
(`FULL`, `LOSSY_KNOWN`, `KNOWN_DEFECT`, `PARTIAL`, `INCONCLUSIVE`). Commits are
full SHAs. `NONCONFORMANT` is CI's verdict, not the script's: a receipt is
only meaningful for a green commit.

## Findings
```

- [ ] **Step 2: Add the changelog entry** above `## [1.4.1] — 2026-11-05`:

```markdown
## [Unreleased]

### Added

- **Core Conformance Corpus** (`vectors/`): 31 executable ISON/ISONL
  documents with a per-port expectation each, run by the Python, TypeScript
  and JavaScript suites on every push. One golden fixture used to be the only
  thing saying the ports agree; the corpus says it per document, and records
  where they still do not (`vectors/README.md` § Findings): TS/JS accept a
  MultiGraph document the other four ports refuse, ison-ts/ison-js write the
  string `nan` bare where ison-py quotes it, and ids or values beyond 2^53
  come back rounded in TS/JS. Rust, C# and C++ columns are `todo` until each
  gets a runner - admission is all-or-nothing per port.
- `scripts/corpus_digest.py` and `scripts/corpus_receipt.py`, which produce
  what ISONGraphExt pins: the corpus digest and a per-port Core Conformance
  Receipt with a derived posture.
```

- [ ] **Step 3: Full verification across the three admitted ports**

```bash
cd ison-graph && python -m pytest -q                 # expected: 498 + 32 + 14 = 544 passed
cd ../ison-graph-ts && npx vitest run && npx tsc --noEmit -p .   # 254 passed; tsc silent
cd ../ison-graph-js && npx vitest run                # 254 passed
cd .. && python .github/scripts/check_cross_port_goldens.py      # the existing six-port golden fixture still passes (the corpus itself records where ports disagree)
python scripts/corpus_receipt.py --port python | head -3
git status --short                                   # only intended files
```

- [ ] **Step 4: Commit and open the PR**

```bash
git add vectors/README.md CHANGELOG.md
git commit -F - <<'EOF'
Document the corpus and record what it found

README carries the manifest schema, the expectation grammar and the
Findings table the meta-test enforces; the changelog entry names the
three divergences the corpus surfaced on day one.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
git push -u origin feat/conformance-corpus
gh pr create --base main --head feat/conformance-corpus --title "Core Conformance Corpus with Python, TS and JS runners" --body-file - <<'EOF'
## Summary

Adds `vectors/`, an executable Core-owned conformance corpus: 31 ISON/ISONL documents indexed by `vectors/manifest.ison` (plain ISON, parsed by each port's own parser), each with a per-port expectation (`pass` / `pass:canonicalized` / `pass:lossy` / `defect` / `reject:<Error>` / `todo`). Python, TypeScript and JavaScript each get a ~60-line parametrized runner inside their existing suites, so CI runs the corpus with no new job. A Python meta-test pins the corpus rules (LF-only, single trailing newline, unique ids, files exist, `todo` iff no runner, `defect` iff a Findings row).

`scripts/corpus_digest.py` and `scripts/corpus_receipt.py` produce what ISONGraphExt pins: the corpus digest and a per-port **Core Conformance Receipt** with a derived posture.

## What it found

See `vectors/README.md` § Findings. Expectations record observed behaviour; nothing was weakened to go green.

- TS/JS load an `ison-graph-multigraph-v1` document (treating `key` as a property); Python, Rust, C# and C++ refuse it. Marked `defect`; needs a TS/JS fix.
- ison-ts/ison-js write the string `nan` bare; ison-py quotes it. Same graph, two canonical byte forms - an ISONCS writer divergence to settle upstream.
- Ids and values beyond 2^53 come back rounded in TS/JS (`pass:lossy`) - the JS binding rule from Semantic/2.

## Not in this PR

Rust, C# and C++ runners (their columns are `todo`; admission is atomic per port). Semantic/2 digest values (column reserved).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

---

## Self-review

- **Spec coverage:** §2 documents-only (Tasks 2–5 contain no API vectors); §3 layout + gitattributes (Task 1); §4 schema (Task 1 manifest, README Task 10); §5 grammar incl. `defect`, atomic admission, three postures (runner + meta-test Task 1, README Task 10); §6 all 31 vectors (Tasks 2–5: 9 + 10 + 9 + 3 = 31, siblings 3); §7 runners for Python/TS/JS + meta-test (Tasks 1, 6, 7); §8 digest + receipt + posture table (Tasks 8, 9); §9a ownership (README); §10 findings (Tasks 6, 7, 10).
- **Placeholder scan:** none; every file has full content; the "resolve by observation" rule is stated once (Task 2 Step 3) and referenced.
- **Type consistency:** `RUNNERS` keys and paths identical in `test_vectors.py` and `corpus_receipt.py`; `corpus_digest(root: Path) -> str` used by Task 9 as defined in Task 8; expectation strings identical across Python/TS/JS runners and the receipt counters.
- **Review Focus:** all five pinned in Task 1's meta-test; item 5 becomes active once Task 6 introduces the first `defect`.

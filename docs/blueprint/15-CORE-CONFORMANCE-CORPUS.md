# Core Conformance Corpus — Design Spec

Status: **SPEC FOR REVIEW** · Date: 2026-11-05 · Implements G-ID condition 7 and F8 (`13-SEMANTIC-2.md` §7–§8). Lands in `ISON-format/isongraph` as `vectors/`; this file becomes `vectors/README.md` there.

## 1. Purpose

Prove "same document → same meaning in every port" with executable vectors rather than one golden fixture and prose. The corpus is owned by Core (F8). Ext consumes it at a pinned commit and never owns vectors.

Scope of this iteration: Python, TypeScript and JavaScript runners. Rust, C# and C++ get columns now and runners later; their expectations are marked `todo` until a runner sets them from observed behaviour.

Success: every port suite runs its runner on every push; a divergence between ports fails CI; Ext can record `core_vector_corpus_commit` and `core_vector_corpus_digest`.

## 2. What the corpus tests — and what it does not

The corpus tests **documents**: what a port does when it loads a given ISON/ISONL text and writes it back. It does not test construction-time API refusals (NaN at `add_node`, float ids, property-name rules). Those cannot be carried on the wire, so a document corpus cannot exercise them; each port's unit tests already cover them (added in 1.4.1).

Expected Semantic/2 digests are **not** included. The `digest` column exists and is `null` until `13-SEMANTIC-2.md` §3 freezes tag bytes; adding values later changes no structure.

## 3. Layout

```text
vectors/
  README.md                 this spec, condensed
  manifest.ison             the only index; parsed by each port's own ISON parser
  ids/*.ison
  values/*.ison
  structure/*.ison
  serialization/*.ison  *.isonl
scripts/corpus_digest.py    SHA-256 over sorted (path, bytes) of vectors/**
.gitattributes              vectors/** text eol=lf   (byte comparisons must survive Windows checkouts)
```

A vector whose file ends in `.isonl` is loaded with `from_isonl`; everything else with `from_ison`. Output is always compared via `to_ison()`.

## 4. Manifest schema (`manifest.ison`)

```text
meta.corpus
version semantic_spec
1 "ISONGraph-Semantic/2-draft"

table.vectors
id file semantic reason directed nodes edges canonical digest python ts js rust cs cpp
ids/positive-int ids/positive-int.ison identifiable null true 2 1 null null pass pass pass todo todo todo
...
```

| Column | Type | Meaning |
|---|---|---|
| `id` | string | `<group>/<name>`, unique |
| `file` | string | path relative to `vectors/` |
| `semantic` | `identifiable` \| `out_of_domain` | Semantic/2 status of the loaded graph |
| `reason` | string \| null | a `13-SEMANTIC-2.md` §5 code or reason (`INTEGER_OUT_OF_INT64`, `INVALID_NODE_ID_TYPE`, `UNDIRECTED_EDGE_CONFLICT`, `INVALID_EDGE_ADDRESS`, `AMBIGUOUS_NODE_REFERENCE`) or one of the **corpus-level** reasons below; null when identifiable |

Corpus-level reasons (document-level conditions that Semantic/2's API-level taxonomy does not need): `AMBIGUOUS_NODE_REFERENCE` is used for a document carrying an int/string id twin — unreachable through Core's API because of ID-TWIN-INVARIANT, but exactly what such a document presents on the wire, so the corpus is where the reserved code becomes observable; `MULTIGRAPH_DOCUMENT` means the document declares `format ison-graph-multigraph-v1`, which a simple-graph port's class cannot represent (the document may well have a Semantic/2 identity as a multigraph; `semantic` records what the *simple-graph* reading would mean). For a row that every admitted port rejects, `semantic`/`reason` still state the Semantic/2 verdict on the document, and `directed`/`nodes`/`edges` are unused unless some port's cell is `defect`.
| `directed` | bool | expected `graph.directed` after load (only checked on `pass*`) |
| `nodes`, `edges` | int | expected counts after load; `edges` counts stored edge records (an undirected edge counts 2) |
| `canonical` | string \| null | sibling file holding the canonical output when the input is deliberately non-canonical |
| `digest` | null | reserved for Semantic/2 |
| `python` `ts` `js` `rust` `cs` `cpp` | string | per-port expectation, grammar below |

Each port reads only its own column, so error names are that port's own (`DuplicateNodeError` in Python/TS/JS, `DuplicateNode` in Rust, `GraphError` in C#).

## 5. Per-port expectation grammar

| Value | Runner checks |
|---|---|
| `pass` | loads; `directed`, `nodes`, `edges` match; `to_ison() + "\n"` is byte-identical to the file (every vector file ends in exactly one LF) |
| `pass:canonicalized` | loads; counts match; `to_ison() + "\n"` equals the `canonical` file; output is idempotent (`from_ison(out).to_ison() == out`) |
| `pass:lossy` | loads; counts match; output differs because of a documented port limitation (JS int64 precision, `1.0` → `1`); only idempotence is checked |
| `defect` | loads without raising, but the behaviour contradicts the spec (e.g. TS/JS accept a MultiGraph document). The runner still pins what the port *does*: `directed`, `nodes`, `edges` must match the row (set from the defective port's observed values — a rejecting port ignores them) and the output must be idempotent, so a defect cannot drift from one wrong reading to another unnoticed. A `vectors/README.md` Findings row with this vector id MUST exist; the meta-test enforces that |
| `reject:<ErrorName>` | loading raises an error whose class name (Python `type(e).__name__`, TS/JS `e.name`) equals `<ErrorName>` |
| `todo` | no runner yet; the meta-test asserts a port column contains `todo` **iff** that port's runner file does not exist |

A row's `canonical` is non-null iff some port column is `pass:canonicalized`. A `pass` port compares against the file itself, never against `canonical` — so one document can be `pass` for a port whose writer already agrees with it and `pass:canonicalized` for a port whose writer normalizes it (this is exactly how writer divergences such as `"nan"` quoting surface).

Rule: an expectation is set from **observed** behaviour of the released port, and any observation that contradicts `13-SEMANTIC-2.md` is written to `vectors/README.md` §Findings as a Core defect with the vector id. The corpus is a record of what is, annotated with what should be; it is never made green by weakening a vector.

**Port runner admission is atomic.** A port is corpus-enabled only when every vector has an observed expectation in its column. A port that can execute 27 of 31 vectors has no runner and posture `PARTIAL`, not a runner with four `todo`s. This is deliberate: a partially-admitted port would let "corpus-enabled" mean different things for different ports.

**Three postures never collapse into one bit.** `python = pass` on `values/int-beyond-int64` says the port *loads* the document; `semantic = out_of_domain` says Semantic/2 assigns it no identity. Load posture, semantic posture and (downstream) extension posture are separate columns and stay separate in every consumer.

**`pass:lossy` is not conformance.** It records that the port stabilises after a documented loss. A consumer that needs cross-port identity for that input must treat the port as `CORE_LOSSY` for it (see `13-SEMANTIC-2.md` §6.1).

## 6. Vector set

Counts are after load. `canonical` is null unless stated. Expectations below are the *predicted* values; the implementation sets the real ones from runs and records differences as findings.

### ids/

| id | document | semantic | predicted Py / TS / JS |
|---|---|---|---|
| positive-int | nodes `p` 1, 2; edge `R` 1→2 | identifiable | pass |
| negative-int | nodes -1, 2; edges -1→2, 2→-1 | identifiable | pass (regression for 1.4.0 `isdigit` bug) |
| string-numeric | ids `"1"`, `"2"` quoted; edge | identifiable | pass |
| string-negative | id `"-1"` quoted; edge | identifiable | pass |
| int64-extremes | ids 9223372036854775807, -9223372036854775808; edge | identifiable | Py pass; TS/JS pass:lossy (precision) |
| twin-int-string | rows `1` and `"1"` | — | reject:DuplicateNodeError |
| twin-negative | rows `-1` and `"-1"` | — | reject:DuplicateNodeError |
| float-id | row `1.5` | out_of_domain / INVALID_NODE_ID_TYPE | reject:InvalidIdentifierError |
| bool-id | row `true` | out_of_domain / INVALID_NODE_ID_TYPE | reject:InvalidIdentifierError |

### values/

| id | document | semantic | predicted |
|---|---|---|---|
| int-vs-integral-float | `x` = 1 on one node, 1.0 on another | identifiable (both INT64(1)) | Py pass; TS/JS pass:lossy (`1.0` → `1`) |
| negative-zero | `x` = -0.0 | identifiable (INT64(0)) | Py pass; TS/JS pass:lossy |
| fractional-float | 1.5, 2.25, 0.1 | identifiable | pass |
| int64-extreme-values | 9223372036854775807, -9223372036854775808 | identifiable | Py pass; TS/JS pass:lossy |
| int-beyond-int64 | 100000000000000000000 | out_of_domain / INTEGER_OUT_OF_INT64 | Py pass; TS/JS pass:lossy |
| nonfinite-as-text | unquoted `nan`, `inf` | identifiable (they are STRINGs on the wire) | pass |
| null-elision | `x` null on one node, 1 on another | identifiable (null elided) | pass |
| nfd-vs-nfc | `"é"` vs `"é"` as two property values | identifiable, distinct | pass (file is UTF-8, no BOM) |
| string-looks-typed | `"true"`, `"1"`, `"1.5"`, `"null"` quoted | identifiable (STRINGs) | pass |
| quoting | space, `\|`, `"`, newline, empty string, `#` | identifiable | pass |

### structure/

| id | document | semantic | predicted |
|---|---|---|---|
| directed-two-way | A→B and B→A, no meta | identifiable; directed=true; edges 2 | pass |
| undirected-basic | `meta.graph directed false`; mirror rows | identifiable; directed=false; edges 2 | pass |
| undirected-mirror-conflict | mirrors with `w` 1 and 2 | out_of_domain / UNDIRECTED_EDGE_CONFLICT | pass:canonicalized (second mirror skipped; canonical sibling has `w` 1 twice) |
| directed-duplicate-row | same row twice, no meta | — | reject:DuplicateEdgeError |
| explicit-directed-true | `meta.graph directed true` | identifiable; directed=true | pass:canonicalized (canonical sibling has no meta) |
| self-loop | A→A | identifiable; edges 1 | pass |
| multigraph-document | `meta.graph` with `format ison-graph-multigraph-v1`, edge rows with `key` | — | Py reject:ValueError; TS/JS predicted to load silently (`key` becomes a property) → **finding**, expectation records observed behaviour |
| unknown-block-kind | a `table.x` block plus nodes | identifiable | Py pass:canonicalized (block dropped); TS/JS observed |
| empty | empty file | identifiable; 0/0 | pass |

### serialization/

| id | document | semantic | predicted |
|---|---|---|---|
| non-canonical-order | nodes before edges, unsorted columns and rows | identifiable | pass:canonicalized, canonical = `serialization/non-canonical-order.canonical.ison` |
| undirected-basic-isonl | ISONL twin of `structure/undirected-basic` | identifiable | pass:canonicalized, canonical = `structure/undirected-basic.ison` |
| negative-int-isonl | ISONL twin of `ids/negative-int` | identifiable | pass:canonicalized, canonical = `ids/negative-int.ison` |

Total: 31 vectors, 3 canonical siblings.

## 7. Runners

One file per port in its existing test suite; no new CI job.

- `ison-graph/tests/test_vectors.py` — `pytest.mark.parametrize` over manifest rows; reference runner.
- `ison-graph-ts/src/vectors.test.ts` and `ison-graph-js/src/vectors.test.js` — `describe.each`.

Shared logic per runner (~60 lines): read `manifest.ison` with the port's parser; for each row read the file as UTF-8 with LF newlines; pick loader by extension; dispatch on the grammar in §5. A `todo` in that port's column fails the runner, so a runner cannot be added without filling its column.

Python-only meta-test (`test_vectors.py::test_manifest_integrity`): every `file` and `canonical` exists; every file is LF-only and UTF-8 without BOM; ids unique; every row has all six port columns; a port with a runner has no `todo`.

## 8. Pinning for Ext: digest and Core Conformance Receipt

`scripts/corpus_digest.py` prints `sha256(concat(sorted(path + "\0" + bytes + "\0")))` over `vectors/**`.

`scripts/corpus_receipt.py --port <python|ts|js|rust|cs|cpp>` emits a **Core Conformance Receipt** as ISON. It is computed from the manifest (whose expectations are observed behaviour by the rule in §5) plus the port's declared version; the port's runner is what makes the manifest trustworthy, so the receipt is only meaningful for a commit whose CI is green.

```text
meta.core_conformance_receipt
canonicalized core_commit core_format core_version corpus_commit corpus_digest corpus_version defect lossy pass port port_version posture rejected_as_expected semantic_spec todo total
7 <40-hex sha> isongraph 1.4.1 <40-hex sha> <sha256> 1 0 0 19 python 1.4.1 FULL 6 "ISONGraph-Semantic/2-draft" 0 32
```

(The canonical writer sorts fields alphabetically; ISON is name-keyed so the order carries no meaning. Counts above are the 32-vector corpus as implemented: for `ts`/`js` they read `6 … 1 3 17 … KNOWN_DEFECT 5 … 0 32`.)

**Known gap, corpus_version 2:** `pass:lossy` and `defect` cells pin counts, idempotence and (for lossy) that the output differs, but not the observed output bytes — so a defect could change into a different defect with equal counts unnoticed. Version 2 adds a per-port observed-output column (e.g. `<name>.<port>.observed.ison`) for those two cell kinds.

Posture is derived, never hand-set:

| Posture | Rule |
|---|---|
| `FULL` | runner exists, no `todo`, no `pass:lossy`, no `defect` |
| `LOSSY_KNOWN` | runner exists, no `todo`, no `defect`, at least one `pass:lossy` (a representation limit, not a contradiction) |
| `KNOWN_DEFECT` | runner exists, no `todo`, at least one `defect` (the port contradicts the spec on some input; Ext may refuse identity-sensitive work outright without confusing this with ordinary numeric loss) |
| `PARTIAL` | no runner for this port (every row `todo`) |
| `INCONCLUSIVE` | manifest and runner disagree about admission (a runner with `todo` cells, or cells set with no runner), or CI for the commit did not run |
| `NONCONFORMANT` | the runner fails on this commit — CI's verdict, never the script's |

Commits in the receipt are **full** SHAs (`git rev-parse HEAD`, `git log -1 --format=%H -- vectors`): the receipt is a long-lived pin. The corpus digest iterates files sorted by the exact key it hashes, the POSIX relative path, so ordering never depends on platform path semantics.

Ext binds to the receipt, not to a bare hash. The IGX/1 binding (E1) carries at minimum:

```text
core_format core_version core_commit core_semantic_spec
core_vector_corpus_version core_vector_corpus_commit core_vector_corpus_digest
core_port core_port_version core_posture
```

`meta.corpus.version` increments when the manifest schema or grammar changes, not when vectors are added.

Downstream (`ISONGraph Visualize` and products) consume Core conformance through the receipt; they neither rerun the wire vectors as their own responsibility nor copy them. They keep their own corpora for scene/layout/renderer/LOD/timeline/accessibility.

## 9. Out of scope

Rust/C#/C++ runners (next iteration, after the id-typing decision); Semantic/2 digest values; a vector DSL for API-level behaviour; a dedicated CI workflow; a Visualize corpus.

## 9a. Ownership

`ISON-format/isongraph` owns `vectors/`. `isongraph-ext`, Visualize and products consume it at a pinned commit and **never copy or fork it**. If a consumer needs a vector that does not exist, it is added upstream.

## 10. Findings expected from the first run

Recorded in `vectors/README.md` §Findings when confirmed:

1. TS/JS load a MultiGraph document without checking `format` (Rust/C#/C++ and Python refuse it) → Core follow-up: add the check to TS/JS.
2. TS/JS lose precision on int64 ids and values beyond 2^53 — the JS binding rule in `13-SEMANTIC-2.md` §1.2; documented as `pass:lossy`, not a defect of the corpus.
3. Any other divergence the runs reveal.

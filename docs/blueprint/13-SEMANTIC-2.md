# ISONGraph-Semantic/2 — Graph Identity Contract

Status: **DRAFT FOR G-ID FREEZE** · Consolidates the earlier design discussion into one normative document; where it and any earlier discussion disagree, this file wins.

Core baseline: ISONGraph **1.4.1** (tag `v1.4.1` = `027fb77`, released 2026-11-05), which carries the identity-contract fixes described in `14-E0-FORENSICS.md`.

## 0. The law

> **Semantic/2 assigns identity only to the explicitly defined, round-trip-stable semantic subset of ISONGraph. Core acceptance of a value or representation does not imply that Semantic/2 can assign it an identity.**
>
> **Semantic/2 normalizes graph meaning, not graph serialization. Its identity rules are versioned and complete within this specification; no serializer, writer, Unicode normalizer, ISONCS canonicalizer or language-native representation participates implicitly.**

Two consequences that drive everything below:

1. A graph has a **semantic identity** independent of how a writer serialized it. A serialized artifact has a **byte identity** tied to the writer that produced it. These are two digests, never one.
2. A graph may have a valid Semantic/2 identity even when a particular Core implementation cannot persist and reload it correctly. **Semantic conformance** and **persistence conformance** are separate statuses.

There is no "Semantic/1". Core 1.4.0 has no digest at all; the only identity it offers is ISONCS canonical bytes, which is an *artifact* identity. Semantic/2 is numbered `/2` so that a future digest can never be confused with the byte identity that preceded it.

## 1. Value normalization

### 1.1 Value domain

```text
SemanticValue/2 ::= NULL | BOOL | INT64 | FLOAT64 | STRING | REF
```

`LIST` and `MAP` tags are **reserved** and MUST NOT be emitted in v1. The property bag of a node or edge is map-shaped, but `MAP` is not a legal property *value*. Core 1.4.0 serializes a list or dict property as a JSON-text string (`["a","b"]` → `"[\"a\", \"b\"]"`), so such a value is `VALUE_OUT_OF_DOMAIN / CONTAINER_PROPERTY`, not silently re-typed.

### 1.2 Numeric normal form

```text
BOOL?                         → BOOL              (checked before integer)
integer?
    in int64                  → INT64
    otherwise                 → VALUE_OUT_OF_DOMAIN / INTEGER_OUT_OF_INT64
binary64?
    non-finite                → VALUE_OUT_OF_DOMAIN / NONFINITE_FLOAT
    ±0.0                      → INT64(0)
    mathematically integral
        in int64              → INT64
        otherwise             → VALUE_OUT_OF_DOMAIN / INTEGRAL_FLOAT_OUT_OF_INT64
    otherwise                 → FLOAT64, exact IEEE-754 binary64 bits
```

So `1`, `1.0`, `1.000000` → `INT64(1)`; `0`, `0.0`, `-0.0` → `INT64(0)`; `1.5` → `FLOAT64(0x3FF8000000000000)`. No `repr()`/`toString()` spelling participates.

| Question | Decision |
|---|---|
| `1` vs `1.0` | same |
| `-0.0` vs `0` | same |
| `true` vs `1` | different |
| integer domain | signed int64 |
| integer outside int64 | reject |
| NaN / ±Inf | reject |

**JavaScript binding rule.** `Number.isInteger(v) && !Number.isSafeInteger(v)` is a binding violation for untyped numeric input; an integer beyond 2^53 must arrive as `BigInt` or via an ISON integer token preserved exactly. The Core "known limitation" (a JS-authored `1.0` emits as `1`) is harmless here: both normalize to `INT64(1)`.

### 1.3 Null

- A `null` member of a property bag is **elided**: `{a: 1, b: null}` ≡ `{a: 1}`.
- `null` inside a list is preserved (list position is semantic) — moot in v1 because lists are out of domain.
- An empty bag remains `{}`; it is not itself eliminated.

### 1.4 Strings and Unicode

- Strings are exact Unicode scalar sequences. **No NFC/NFD normalization.** `"é"` and `"é"` are different values (verified: Core round-trips them distinctly).
- A lone surrogate → `VALUE_OUT_OF_DOMAIN / INVALID_UNICODE_SCALAR`. (Core 1.4.0 passes `\ud800` through; Semantic/2 rejects it.)
- Applications that want normalized text normalize *before* binding the value into the graph.

### 1.5 Node identity

```text
NodeId/2  ::= INT64 | STRING
NodeRef/2 ::= { node_type: STRING, node_id: NodeId/2 }
```

- `BOOL` and `FLOAT64` are **forbidden** as ids. Core now enforces this at `add_node` (patch).
- `INT64(1)` and `STRING("1")` are different identities and MUST NOT be collapsed via `str(id)`.
- **ID-TWIN-INVARIANT (Core):** within one node type, Core rejects simultaneous integer-id and string-id twins whose canonical decimal spelling is identical (`1`/`"1"`, `-1`/`"-1"`). Verified on Python, TS, JS across `add_node`, `.ison`, `.isonl`. Because of this invariant, reference text `:p:1` has exactly one legal typed candidate, so `AMBIGUOUS_NODE_REFERENCE` is **reserved, not reachable through the API**. It *is* what a twin-carrying *document* presents on the wire, which is why the Core corpus (`15` §4) uses it as the `reason` for `ids/twin-int-string` and `ids/twin-negative` — the only place the code is observable.
- Reference text (`:p:1`) is not identity. It is resolved against the typed node table and only then enters `EdgeAddress/2`.
- Canonical decimal spelling of an integer id is `-?[0-9]+`. Core's reference and pattern parsers now use exactly this (patch); `str.isdigit()` is forbidden in any binding because it drops the sign and admits non-ASCII digits.

## 2. Logical graph normalization

### 2.1 Graph header — mandatory, never inferred

```text
directed:   bool
multigraph: bool
```

No defaults. Source precedence:

```text
if Core document carries meta.graph.directed / format:
    use those; receipt.graph_semantics.source = "core-meta"
else:
    require explicit IGX/1 binding values; receipt.graph_semantics.source = "binding"
```

Core status after the patch: `ISONGraph(directed=False)` writes `meta.graph` with `directed false` and reads it back; a directed simple graph writes nothing (bytes unchanged from 1.4.0 — so for a legacy document with no `meta.graph`, `directed=true` is a *Core* default that the binding must restate explicitly, never an inference from edge structure). `MultiGraph` already wrote `format`, `version`, `directed`. `multigraph` is derived from `meta.graph.format == "ison-graph-multigraph-v1"`.

Never infer directedness from mirror-pair symmetry.

### 2.2 Edge address

```text
EdgeAddress/2 = ( source_ref: NodeRef/2, relation_type: STRING, target_ref: NodeRef/2, ordinal: STRING )
```

- The 3-tuple `(A, R, B)` is API sugar; the digested address is always the 4-tuple with ordinal `"0"` for a simple graph.
- **Ordinal is an opaque STRING compared as unsigned UTF-8 bytes, lexicographically.** `"10" < "2"` is intentional; producers wanting numeric order zero-pad. Ordering governs only deterministic record order, never meaning.
- **Core binding:** `MultiGraph` keys are non-negative integers (`InvalidEdgeKeyError` otherwise) written as decimal. The Semantic/2 ordinal of a MultiGraph edge is the canonical decimal spelling of its key. A future Core release that admits string keys needs no Semantic/2 change.

### 2.3 Undirected graphs — logical-edge reconstruction

For `directed = false`, Core stores and serializes both `A R B` and `B R A`. Normalize to **one logical edge**:

```text
canonical endpoints = ( min(NodeRef(A), NodeRef(B)), max(...) )   # NodeRef ordering: node_type bytes, then id (INT64 < STRING; ints numerically; strings by UTF-8 bytes)
logical address     = ( min_endpoint, relation, max_endpoint, ordinal )
group raw records by logical address:
    1 record                                   → one logical edge
    2 mirror records, identical normalized props → collapse to one
    2 mirror records, differing props          → UNDIRECTED_EDGE_CONFLICT
    > 2 records                                → UNDIRECTED_EDGE_CONFLICT (unless a future profile defines it)
```

Core 1.4.0 loads conflicting mirror rows without complaint (verified); the conflict is a Semantic/2 failure, not a Core one. Directed graphs preserve source/target exactly.

## 3. Digest encoding

Self-contained binary normal form. Illustrative tag bytes, to be frozen at G-ID:

```text
NULL     00
FALSE    01
TRUE     02
INT64    03 + 8-byte signed big-endian
FLOAT64  04 + 8-byte IEEE-754 big-endian
STRING   05 + u32 byte length + UTF-8 bytes
REF      08 + STRING(node_type) + NodeId/2
LIST     06   (reserved)
MAP      07   (reserved)
```

Record layout (all lengths u32 big-endian, all orderings by the comparison rules above):

```text
"ISONGraph-Semantic/2\0"
header   : directed BOOL, multigraph BOOL
nodes    : count, then for each node sorted by NodeRef/2:
             REF, property count, then (STRING name, value) pairs sorted by name UTF-8 bytes, null members elided
edges    : count, then for each logical edge sorted by EdgeAddress/2:
             REF source, STRING relation, REF target, STRING ordinal, property bag as above
digest   = SHA-256(bytes)
```

Independent of: writer implementation/version, whitespace, block order, column order, file extension, physical byte layout, ISON/ISONCS canonicalization rules, and the graph's `name` (Core does not persist it; see forensics).

## 4. Two digests, one receipt

```text
semantic_digest:
    algorithm: ISONGraph-Semantic/2
    value:     <hex>
artifact_digest:
    algorithm: SHA-256
    value:     <hex of exact written bytes>
core_writer:                       # REQUIRED, no "unknown" default, never inferred after the fact
    implementation:        isongraph-python | isongraph-ts | isongraph-js | isongraph-rs | isongraph-cs | isongraph-cpp
    version:               1.4.1
    serialization_profile: ison-v1 | isonl-v1
core_conformance:                  # from the Core Conformance Receipt, 15-CORE-CONFORMANCE-CORPUS.md §8
    core_commit:           027fb77
    semantic_spec:         ISONGraph-Semantic/2
    corpus_version:        1
    corpus_commit:         <sha>
    corpus_digest:         <sha256>
    port_posture:          FULL | LOSSY_KNOWN | KNOWN_DEFECT | PARTIAL | INCONCLUSIVE | NONCONFORMANT
graph_semantics:
    directed:   bool
    multigraph: bool
    source:     core-meta | binding
receipt_posture: OK | CORE_LOSSY | CORE_BLOCKING_DIVERGENCE
```

Writer version 1.2 and 1.3 may legitimately produce different `artifact_digest` for the same `semantic_digest`. The required-field contract is frozen before E3; the receipt implementation lands in E7.

## 5. Failure taxonomy

```text
SemanticIdentityError                   (reachable)
├── VALUE_OUT_OF_DOMAIN                 reason ∈ { NONFINITE_FLOAT, INTEGER_OUT_OF_INT64,
│                                                  INTEGRAL_FLOAT_OUT_OF_INT64, CONTAINER_PROPERTY,
│                                                  INVALID_UNICODE_SCALAR, INVALID_NODE_ID_TYPE }
├── UNDIRECTED_EDGE_CONFLICT
├── INVALID_EDGE_ADDRESS
├── MISSING_GRAPH_SEMANTICS             directed/multigraph absent from both core-meta and binding
└── UNSUPPORTED_SEMANTIC_VERSION
    (reserved, unreachable under ID-TWIN-INVARIANT: AMBIGUOUS_NODE_REFERENCE)

PersistenceConformanceError             (separate contract)
├── REFERENCE_RESOLUTION_FAILURE        e.g. Python 1.4.0 :p:-1 → NodeNotFoundError
├── TYPE_ROUNDTRIP_FAILURE              e.g. NaN → "nan"
├── VALUE_ROUNDTRIP_FAILURE             e.g. list → JSON text
├── GRAPH_SEMANTICS_ROUNDTRIP_FAILURE   e.g. undirected → directed on reload (1.4.0)
└── UNSUPPORTED_PERSISTENCE_VALUE
```

`error code` is the stable machine contract; `reason` is the diagnostic.

The Core corpus adds two **document-level** reasons that this API-level taxonomy does not need: `AMBIGUOUS_NODE_REFERENCE` (a twin-carrying document; see §1.5) and `MULTIGRAPH_DOCUMENT` (a document declaring `format ison-graph-multigraph-v1` read by a simple-graph port — it may have a perfectly good multigraph identity under §2.1; the corpus records the simple-graph verdict). Ext consumers read the corpus `reason` column with that in mind.

## 6. Semantic vs persistence conformance

Every fixture carries two statuses: `SemanticStatus ∈ {IDENTIFIABLE, OUT_OF_DOMAIN}` and a per-port `PersistenceStatus ∈ {PASS, FAIL, REJECTS}`.

```text
SEMANTICALLY_IDENTIFIABLE  does not imply  PERSISTENCE_CONFORMANT
but:
if Persistable_port(G):  Semantic2(G) == Semantic2(load_port(dump_port(G)))
```

That invariant is what E11 tests. Status after the Core patch (Python / TS / JS):

| Fixture | Semantic/2 | Py | TS | JS | Rust/C#/C++ |
|---|---|---|---|---|---|
| positive INT64 id | IDENTIFIABLE | PASS | PASS | PASS | ids are strings — open |
| negative INT64 id | IDENTIFIABLE | PASS (was FAIL) | PASS | PASS | open |
| STRING id | IDENTIFIABLE | PASS | PASS | PASS | PASS |
| int/string twin | n/a | REJECTS | REJECTS | REJECTS | n/a (string-only) |
| FLOAT / BOOL node id | OUT_OF_DOMAIN | REJECTS (was accepted) | REJECTS | REJECTS | n/a |
| undirected round-trip | IDENTIFIABLE | PASS (was FAIL) | PASS | PASS | PASS (was: file refused) |
| list / dict property | OUT_OF_DOMAIN | lossy | lossy | lossy | lossy |
| `10**20` property | OUT_OF_DOMAIN | Core accepts | n/a | n/a | — |
| non-finite float | OUT_OF_DOMAIN | REJECTS (was lossy) | REJECTS | REJECTS | REJECTS |
| fractional FLOAT64 | IDENTIFIABLE | PASS | PASS | PASS | PASS (1.4.0) |
| NFD vs NFC string | IDENTIFIABLE, distinct | PASS | PASS | PASS | PASS |

### 6.1 Three postures, and what Ext may claim

For any input, three postures are tracked separately and never merged:

```text
load posture       did this Core port load the document?            (corpus per-port column)
semantic posture   does Semantic/2 assign the graph an identity?    (corpus `semantic` / `reason`)
extension posture  what may an Ext operation claim about it?        (derived, below)
```

Rules for Ext (E5–E7 receipts):

- An Ext receipt MUST NOT claim cross-port identity equivalence when the producing Core port is `pass:lossy` for the input class. The receipt carries `receipt_posture = CORE_LOSSY`; identity-sensitive operations (revision, delta, projection and DAG receipts, provenance binding) either refuse under policy or mark the result as port-bound.
- A Core divergence where ports disagree on *whether a document is valid* (e.g. Python refuses a MultiGraph document, TS/JS load it) is `CORE_BLOCKING_DIVERGENCE` for every operation that needs cross-port semantic identity, until the Core fix ships and the corpus records agreement.
- `Core loaded it` never implies `semantically identifiable`. Ext checks the semantic posture itself via Semantic/2, not by inference from a successful load.

Ext binds to the Core Conformance Receipt (`15-CORE-CONFORMANCE-CORPUS.md` §8), not to a bare corpus hash, so these postures are available at binding time.

## 7. G-ID — Graph Identity Soundness gate (blocks E3)

| # | Condition | Status |
|---|---|---|
| 1 | `EdgeAddress/2` 4-tuple frozen | spec'd here; freeze pending review |
| 2 | Ordinal opaque STRING, UTF-8 byte order; Core MultiGraph key → decimal ordinal | spec'd |
| 3 | `directed`/`multigraph` mandatory, never inferred; Core writes `directed` for undirected simple graphs | **Core done in all six ports** (PR #1 + parity commit); binding fallback spec'd |
| 4 | Scalar domain + numeric normal form frozen independently of ISONCS | spec'd |
| 5 | Undirected mirror collapse/conflict frozen | spec'd |
| 6 | Semantic digest ≠ artifact digest; writer identity required | spec'd |
| 7 | Pre-E3 golden corpus executes on Python **and** TypeScript, incl. signed int ids | **not started** — vectors listed in §8 |
| 8 | Reachable out-of-domain failures named and present in E0 invariants | this doc + `14-E0-FORENSICS.md` |
| 9 | Semantic vs persistence conformance separated; Core persistence claims require round-trip Semantic/2 invariance | spec'd; Core patch adds the round-trip tests |

Open before freeze:

- **Rust/C#/C++ id typing.** Those ports hold `id: String`. Either they gain `INT64 | STRING` ids (preferred, Core 1.5) or the binding declares `id_typing: string-only` and Semantic/2 treats every id from those ports as STRING — which would make the *same file* digest differently depending on the reading port. The first option is the only one consistent with §0.
- ~~`meta.graph` emission for undirected graphs in Rust/C#/C++~~ — done on `fix/port-parity-1.4.1`.
- Tag byte constants and the u32-length choice in §3.

## 8. Minimum golden corpus (pre-E3)

```text
ids:        +1, -1, "1", "-1", "007", int64 min, int64 max, twin rejection (1/"1", -1/"-1")
values:     1 vs 1.0 collapse, -0.0, 1.5, int64 min/max, out-of-range int, integral float outside int64,
            NaN, Inf, null elision, NFD≠NFC, lone surrogate rejection, list property rejection
structure:  directed vs undirected (must differ), undirected mirror collapse, undirected mirror conflict,
            simple edge ordinal "0", multiedge ordinals "0"/"1"/"10"/"2" ordering, self-loop
receipts:   same graph two writers → same semantic digest, different artifact digest
```

Each vector: ISON text, expected `SemanticStatus`, expected digest (once §3 is frozen), expected per-port `PersistenceStatus`. The corpus is consumed by Ext and **owned upstream** by Core (F8); E11/E12 pin `core_vector_corpus_commit` + `core_vector_corpus_digest`.

# E0 — Format/Runtime Forensics against ISONGraph 1.4.0

Date: 2026-11-05 · Core: `ISON-format/isongraph` @ `3787f22` (1.4.0, 2026-09-05) · ison-py 1.2.0 · Probed live on Python 3.12, Node 24, vitest 4. Rust/C#/C++ were read, not executed (no C++ toolchain on the forensics machine).

Everything marked **verified** was reproduced by running code, not inferred from docs. The probe scripts are reproducible from the fixture list in §3.

## 1. Shipped grammar (E0.1)

```text
nodes.<node_type>             # block kind "nodes", name = node type
id <prop...>                  # header; "id" first, then property names sorted
<id> <values...>              # one row per node; strings quoted when they would reparse as another type

edges.<relation_type>         # block kind "edges", name = relation type
source target <prop...>       # header; props sorted
:<type>:<id> :<type>:<id> ... # references have no quoting and no type marker

meta.graph                    # MultiGraph only in 1.4.0; simple undirected graphs after the patch
directed format version       # MultiGraph: format = ison-graph-multigraph-v1, version = 1
```

- Blocks sort by `kind.name` (so `edges.*` precede `meta.*` precede `nodes.*`); columns sort within a block; rows sort on the full field tuple. All ordering belongs to ison-py's canonical writer (ISONCS), not to ISONGraph. **Verified**: insertion order never changes bytes.
- ISONL is the same block model, one `kind.name|header|row` line per row. **Verified** Py/TS/JS parity.
- Entry points: Python `ISONGraph.to_ison/to_isonl/from_ison/from_isonl/load/save`, `MultiGraph` likewise; TS/JS `toIson/toIsonl/fromIson/fromIsonl/parse`.
- Node id typing on the wire: an **id column** distinguishes `1` from `"1"` by quoting; a **reference** cannot. Core therefore resolves a reference against the loaded node table first and only then guesses from the text.

## 2. Defects found and patched (E0.2–E0.4)

Branch `fix/identity-contract-1.4.1`, unreleased. Python 453 → 498 tests, TS 183 → 221, JS 183 → 221; `check_cross_port_goldens.py` still reports all six ports agree, because a directed graph's bytes are unchanged.

| # | Defect in 1.4.0 | Verified how | Fix |
|---|---|---|---|
| D1 | Negative integer id: `:p:-1` → `NodeNotFoundError` on reload (ISON, ISONL **and** MultiGraph; also `query()` patterns) — `str.isdigit()` drops the sign | probe | `_ref_id` reads `-?[0-9]+`; MultiGraph now uses `_resolve_ref`; patterns accept `-?\w+` |
| D2 | Simple `ISONGraph` writes no `meta.graph`: `directed=False` is lost, the two mirror rows reload as two directed edges, and `{A→B,B→A}` directed is **byte-identical** to `{A—B}` undirected | probe | undirected graphs write `meta.graph / directed false`; loader reads it and skips the reconstructed mirror; directed output unchanged |
| D3 | `1.5`, `True`, `None` accepted as node ids; written as `1.5`/`true`/`null`; every edge to them fails on reload | probe | `add_node` refuses non-`str`/`int` ids (`InvalidIdentifierError` with reason). JS/TS: `1.0` is the integer 1 and stays legal |
| D4 | `float('nan')`/`inf` written bare, read back as the strings `"nan"`/`"inf"` | probe | `InvalidPropertyValueError` on `add_node`/`add_edge`/`update_node`/`ProtectedGraph.update_*` |

Cross-port: Python, TS and JS produce byte-identical ISON and ISONL for `ISONGraph("u", directed=False)` with ids `-1`, `2`, a float property and an edge property — **verified** after the patch.

## 3. Compatibility classification (E0.13)

`Core-legal` means 1.4.0+patch accepts and round-trips it. `Semantic/2` is the identity status from `13-SEMANTIC-2.md`.

| Fixture | Core-legal | Round-trip (Py/TS/JS) | Semantic/2 |
|---|---|---|---|
| int id `1`, `-1`, int64 min/max | yes | yes (after D1) | IDENTIFIABLE |
| string id `"1"`, `"-1"`, `"007"` | yes | yes | IDENTIFIABLE |
| int/string twin in one type | **rejected** (`DuplicateNodeError`) | — | ID-TWIN-INVARIANT holds |
| float / bool / null id | **rejected** (after D3) | — | OUT_OF_DOMAIN |
| property `1.0` | yes | `1.0` (float) in Py; `1` in JS/TS origin | INT64(1) either way |
| property `-0.0` | yes | `-0.0` | INT64(0) |
| property `1.5` | yes | yes | FLOAT64 |
| property `10**20` | yes (Python) | yes (Python) | OUT_OF_DOMAIN / INTEGER_OUT_OF_INT64 |
| property NaN / Inf | **rejected** (after D4) | — | OUT_OF_DOMAIN / NONFINITE_FLOAT |
| property list / dict | yes | **lossy** → JSON text string | OUT_OF_DOMAIN / CONTAINER_PROPERTY |
| property `None` | yes | `null` → `None` | elided |
| string `"1"`, `"true"` | yes | quoted, type kept | STRING |
| `"é"` vs `"é"` | yes | kept distinct | distinct (no NFC) |
| lone surrogate `"\ud800"` | yes (Python) | passes through | OUT_OF_DOMAIN / INVALID_UNICODE_SCALAR |
| undirected graph | yes | yes (after D2) | header `directed=false` |
| undirected mirror rows with differing props | loads silently (as directed) | — | UNDIRECTED_EDGE_CONFLICT |
| directed duplicate row | **rejected** (`DuplicateEdgeError`) | — | — |
| MultiGraph key `"reply"` | **rejected** (`InvalidEdgeKeyError`: non-negative int only) | — | ordinal = decimal spelling of key |
| graph `name` | accepted | **not persisted** — always reloads as `"graph"` | not part of identity |
| unknown `meta.*` / `table.*` block | parses | **dropped** on load, not re-emitted | companion artifact only (ADR-E2 confirmed) |

## 4. Invariants to carry into Ext

- **ID-TWIN-INVARIANT**: per node type, `1`/`"1"` and `-1`/`"-1"` cannot coexist. Verified across `add_node`, `.ison`, `.isonl` in Py/TS/JS.
- **DIRECTED-DEFAULT**: a document with no `meta.graph` is directed. That is a Core default, not an inference; the IGX/1 binding must restate `directed` explicitly.
- **NAME-NOT-IDENTITY**: `graph.name` never reaches the wire. Source binding is by digest only.
- **NO-INLINE-CARRIER**: foreign blocks are discarded on load. v1 extension data lives in a companion artifact bound by digest.
- **ARTIFACT-ONLY-IDENTITY**: Core and ison-py expose no hash. ISONCS bytes are an artifact identity; the semantic digest is new work (`13-SEMANTIC-2.md` §3).

## 5. Port matrix (E0.5–E0.7, from source)

| | Python | TS | JS | Rust | C# | C++ |
|---|---|---|---|---|---|---|
| node id type | `int \| str` | `number \| string` | same | `String` | `string` | `std::string` |
| typed property values | yes | yes | yes | yes (1.4.0) | yes (1.4.0) | yes (1.4.0) |
| MultiGraph | yes | **no** (refuses the file) | **no** | **no** | **no** | **no** |
| ProtectedGraph | yes | no | no | no | no | no |
| `meta.graph` for undirected | patch | patch | patch | patch | patch | patch |
| non-finite float refused | patch | patch | patch | patch | patch | patch |
| negative-id resolution | patch | ok | ok | n/a (string) | n/a | n/a |
| has_cycle / components | yes | yes | yes | ? | ? | ? |
| SCC / topo sort / subgraph | **no** | **no** | **no** | no | no | no |

Before the parity commit, Rust/C#/C++ refused **any** file carrying `meta.graph` as an "unknown block kind" — so every MultiGraph file and (after the Python patch) every undirected graph was unloadable there. They now read `directed`, refuse a MultiGraph file with a message naming it, and the Python-written undirected fixture (`"1"`/`"2"` string ids) is byte-identical in all six ports — **verified** by running cargo, dotnet and MSVC test suites.

Consequences for the PlanMap: E5/E6 build SCC, topological order and subgraph extraction inside Ext from scratch; E11 parity for anything touching MultiGraph or integer ids needs a Core 1.5 in the three string-id ports first.

## 6. Core follow-ups (upstream, before G-ID closes)

1. ~~Release the identity patch~~ — **done**: PR #1 (Py/TS/JS) + PR #2 (Rust/C#/C++ parity + bump) → tag `v1.4.1` = `027fb77`, published 2026-11-05 to PyPI, crates.io, npm (`ison-graph-js`, `ison-graph-ts`) and NuGet (`IsonGraph`).
2. Rust/C#/C++: decide `INT64 | STRING` ids (see `13-SEMANTIC-2.md` §7 open items). Breaking for those ports → Core 1.5.
3. Adopt the §8 golden corpus of `13-SEMANTIC-2.md` as `vectors/semantic` + `vectors/serialization` in Core (F8).
4. Optional: refuse `10**20` and lone surrogates at construction, or document them as "Core-legal, identity-unavailable".

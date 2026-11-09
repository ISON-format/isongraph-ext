# IGP/1 — Structural Projection (design)

Status: **FROZEN (rev 1).** Defines IGP/1, structural projection: given the bytes of a directed ISONGraph and an explicit policy, produce an ordinary ISONGraph and an IGPV/1 lineage payload, deterministically and verifiably. Depends on `17` (IGX/1) and `18` (IGPV/1) only; it uses no Semantic/2 identity, because the source is pinned by artifact digest exactly as IGPV/1 pins origin graphs, and a revision-pinned projection would be a separate future contract. IGP/1 is a deterministic graph-subsetting contract, not a graph query language: it receives explicit selection intent and applies structural traversal under verifiable constraints. Nothing here is a query language, a ranking, a relevance model, an agent policy or a domain vocabulary (`02` laws 1, 3, 9; `11` ADR-E6). Changing §1–§5 after implementation ships is a new spec version (`IGP/2`), never an edit.

## 0. Purpose and invariant

`project(source, policy) → (result graph, lineage payload)`:

- `source` — the bytes of one canonical `ison-v1`, **directed, simple** ISONGraph (the **source graph**, identified by `sha256(bytes)`).
- `policy` — a canonical companion document `<name>.igp.ison` (§1) stating *explicit* structural selection intent.
- `result graph` — an ordinary ISONGraph (law 3): the Core writer's output for the selected subgraph. It loads, verifies and binds like any other graph.
- `lineage payload` — an IGPV/1 payload (`18`) whose derivation rows say, for every node and edge of the result, which object of the source it was carried over from.

> **Invariant.** The same source bytes, the same policy bytes and the same IGP/1 implementation version (§3) produce byte-identical result and payload bytes. Mandatory *nodes* are never silently dropped: if they cannot be kept within budget, projection fails with a named error. A verifier can recompute the projection from the three inputs and confirm the outputs.

Two consumer scenarios define the contract. Neither mentions software, and both are directed graphs:

1. **Institutional context.** From a decision/evidence/meeting graph, take decision `D-4`, everything it is supported by and the meeting it was decided at, within 2 hops, keeping the meeting record mandatory, at most 50 nodes.
2. **Supply-chain impact.** From a supplier/facility/component graph, take supplier `S-ACME` and everything downstream along `supplies` and `produces` within 3 hops, for a bounded impact view.

### 0.1 What a verified projection does not prove

That the selection is *relevant*, complete for any purpose, or correct for the consumer's question. It proves only that the result is the deterministic structural consequence of the stated policy over the stated source bytes. Who chose the anchors, and why (for example a risk-score threshold evaluated on node properties), is the consumer's decision; IGP/1 does not know what a property means and cannot replay that discovery. The policy file **is** the record of the chosen anchors (§1), and its digest is carried in the lineage (§3).

### 0.2 What the budgets guarantee — and do not

`max_nodes` and `max_edges` bound the **size of the output**. They are not execution-work budgets: with `max_nodes = 50` the traversal may still examine every source node reachable within `depth` before pruning. Work is bounded only by the source size limit (`max_source_bytes`, §4.3) and by `O(V + E)` traversal over adjacency indexes built once.

## 1. Policy wire format

A policy is one ISON document, canonical by construction (the ison-py canonical writer's output, no trailing newline; `from_ison` rejects non-canonical bytes as in `18` §1). `policy_sha256 = sha256(file bytes)`. A policy is **source-independent**: it names no source digest, so one policy applies to many graphs and its digest is stable across them.

Blocks (exactly these; anything else is `POLICY_MALFORMED`):

```text
meta.igp
depth direction max_edges max_nodes policy_spec
2 both null 50 IGP/1

table.anchors
node_id node_type
D-4 decision

table.mandatory
node_id node_type
2026-03-12 meeting

table.node_types
node_type
decision
evidence
meeting

table.relations
relation
decided_at
supports
```

(Block order, field order, row order and quoting are the canonical writer's, as in `18` §1; this example is byte-identical to the writer's output for that policy and is the oracle of `tests/test_igp_policy.py`.)

- `meta.igp`: `policy_spec = "IGP/1"`; `direction ∈ { out, in, both }`; `depth` — INT64 in `[0, 1_048_576]` (0 = anchors only); `max_nodes` — null or INT64 `≥ 1`; `max_edges` — null or INT64 `≥ 0`. (Null = bounded only by the source and lineage limits, §4.3.)
- `table.anchors` — at least one row. `(node_type, node_id)` addressed exactly as `18` §1.2 (Core identifier type; INT64 or STRING id; ID-TWIN-INVARIANT applies across anchors and mandatory nodes together; ids beyond INT64 are `POLICY_MALFORMED`). Duplicates are `POLICY_MALFORMED`.
- `table.mandatory` — zero or more node addresses, same rules. A node may be both an anchor and mandatory.
- `table.node_types`, `table.relations` — allow-lists of Core identifiers. **Empty table = no restriction.** Duplicates are `POLICY_MALFORMED`.
- Row order is the writer's (`18` §1 clarification). No free-text, comment or `note` column exists: a policy states intent, not rationale.

## 2. Selection semantics

Let `S` be the accepted source graph (§4.1 Q1). IGP/1 supports **directed simple graphs** only, profile `ison-v1`. All orders below are the `13` §2.3 / `18` §1.2 node-address order (`node_ref_key`: type bytes, INT64 before STRING, ints numerically, strings by UTF-8 bytes); the **edge order** is the tuple `(source address, relation as UTF-8 bytes, target address)` compared in that order.

1. **Resolve.** Every anchor and every mandatory node must exist in `S` (`ANCHOR_NOT_FOUND`, `MANDATORY_NOT_FOUND`; the first missing one in canonical order is reported). The **protected set** `P` = anchors ∪ mandatory nodes.
2. **Traverse.** Multi-source breadth-first search from all anchors over adjacency indexes built once from `S`. A step follows an edge whose relation is allowed (or any, if the allow-list is empty) in the policy's `direction` (`out`: source→target; `in`: target→source; `both`: either). A non-anchor node is entered only if its `node_type` is allowed (or the list is empty). `dist(n)` is the BFS level; nodes with `dist ≤ depth` are **selected**. Anchors have `dist = 0` and are always selected, whatever their type.
3. **Mandatory.** Mandatory nodes are added to the selection regardless of distance or type. A mandatory node not reached by the traversal has `dist = ∞` and does not seed further traversal.
4. **Induced edges.** The result's edges are *every* source edge whose relation is allowed (or any, if the list is empty) and whose two endpoints are both selected — the induced subgraph, not only the edges the traversal walked. Edge properties are carried unchanged.
   - `direction` controls **which nodes the traversal discovers**, not the orientation of the edges that end up in the result. A `direction = out` projection may therefore contain an *incoming* edge between two selected nodes, and an edge between two depth-1 siblings that was never walked. This is intentional: the result is a recognizable structural subset of the source.
   - A `dist` of `∞` makes an edge's distance `∞`.
5. **Node budget.** If `|selected| > max_nodes`: if `|P| > max_nodes` the projection fails with `PROJECTION_BUDGET_UNSATISFIABLE` (field `meta.igp.max_nodes`). Otherwise remove non-protected nodes one at a time — always the node with the greatest `dist` (`∞` is greatest), ties broken by the **greatest** canonical node address — until `|selected| = max_nodes`; then recompute induced edges (step 4). Because removal is farthest-first, every remaining non-protected node keeps a predecessor path at smaller distance.
6. **Edge budget.** If `|edges| > max_edges`, remove edges one at a time — always the edge with the greatest `max(dist(source), dist(target))`, ties broken by the **greatest** edge order — until `|edges| = max_edges`. Edges are never mandatory in IGP/1, so this step cannot fail.
7. **Emit.** The result is a new directed Core graph holding exactly the final nodes and edges, each added with the properties it has in `S` (`add_node` / `add_edge` from the loaded source graph), serialised with Core's `to_ison()`. Core's writer orders its output by content, so selection and insertion order are irrelevant. The result bytes are exactly that output; no other normalisation is applied. (Rebuilding is specified rather than deleting from a copy of the source because Core's node removal is not linear: measured 33 s against 0.11 s at 20,000 nodes, byte-identical output.) The result is directed.

Selection is a pure function of `(S bytes, policy bytes, implementation version)`: no clock, no randomness, no environment, no network, no filesystem resolution.

### 2.1 Mandatory means mandatory nodes

The protection in steps 5–6 applies to **nodes**. It does not protect the node's incident edges or its connectivity to the rest of the result. Consequences, all intentional and covered by conformance cases:

- A mandatory node may survive while every edge that connected it is removed by `max_edges`: the consumer asked for the meeting *record* to be kept, not for the *relationship* between decision and meeting.
- A mandatory node outside the traversal can introduce an induced edge that was never walked (step 4).
- Mandatory edges and mandatory paths do not exist in /1.

### 2.2 Consumer-owned discovery

If a consumer chooses anchors by evaluating node properties (a risk threshold, a date, a label match), that evaluation happens **before** IGP/1 and is outside it. The consumer writes the chosen addresses into `table.anchors`; the resulting policy bytes and their digest are the evidence of what was executed. IGP/1 cannot reproduce the discovery from the structural policy alone, and does not pretend to.

## 3. Output and lineage

The lineage payload is an ordinary IGPV/1 payload for the **result** graph as target (`18` is unchanged and sufficient):

- `meta.igpv.target_artifact_sha256 = sha256(result bytes)`, `target_serialization_profile = "ison-v1"`.
- One artifact: `src` — `kind = isongraph`, `artifact_sha256 = sha256(S bytes)`, `size = len(S bytes)`, `serialization_profile = "ison-v1"`, `media_type`, `revision`, `uri` null.
- One producer: `p0` — `kind = transformation`, `implementation = "isongraph-ext-igp"`, `version = IGP_IMPLEMENTATION_VERSION`, `spec = "IGP/1"`, `policy_sha256 =` the policy digest.
- For the *k*-th result node in canonical order: objects `n<k>` (target graph, the node's address) and `o<k>` (`graph = src`, the same address); derivation `dn<k>`: `derived = n<k>`, `origin = o<k>`, `producer = p0`, `kind = identity`. Edges likewise with `e<k>`, `q<k>`, `de<k>`, ordinal `"0"`.
- No attribution rows (IGP/1 has no document sources). No `rewrite` or `collapse` rows in /1: IGP/1 renames and merges nothing.
- **Byte-identical projection.** If the result bytes equal the source bytes (the policy selected the whole graph and the source was already the Core writer's exact output), IGPV/1 forbids a derivation from a graph to itself (`18` §3: the origin graph's digest must differ from the target's). The lineage is then a **self-attribution**, which `18` §1.1 permits (an artifact carrying the target's digest must be `kind = isongraph`, may be attributed to, and is never a valid origin): artifact `src` as above (its digest equals the target's), producer `p0` as above, one graph-scope object `g0` (`kind = graph`, target graph), one attribution `a0` (`g0`, `src`, `p0`, no locator), and **no derivation rows**. The policy digest and implementation version still travel in `p0`. Consequence: a `Lineage` query for a node of such a result ends at `no_derivation_record` — the payload states that the graph is the source graph as processed by `p0`, not an element-by-element mapping; the mapping is the identity function and carries no information. This is the only case in which a node or edge of the result has no `identity` row.
- **No graph-scope derivation.** A projection is not identical to its source, so a graph-object `identity` row would mislead. The result graph as a whole is related to the source through the artifact identity (`src`) and the recorded transformation (`p0`), and each retained node and edge through its own `identity` row.

### 3.1 The implementation version

`IGP_IMPLEMENTATION_VERSION = "1.0.0"` is a fixed constant of the IGP/1 implementation, **independent of the package version**. It is incremented only when observable projection semantics change (selection, ordering, emission, lineage shape); a package release that does not change them leaves it, and therefore every produced byte, unchanged. The same constant is the `producer.version` above. `verify_projection` reads the version from the supplied payload and refuses with `IMPLEMENTATION_VERSION_MISMATCH` before comparing any bytes if it differs from the running implementation's: recomputation proves the outputs only against the algorithm that produced them.

### 3.2 Binding and size

Binding the result is the existing `igpv.bind(result_bytes, payload, …)`; IGP/1 adds no capability row and no registry entry. The policy digest travels in the producer row, not in a binding.

Both IGPV/1 limits apply to the payload and are checked at Q3, failing with `PROJECTION_LIMIT_EXCEEDED`:

- **Rows.** The payload holds two object rows and one derivation row per result element, so `2 × (nodes + edges) ≤ igpv max_rows_per_table` (default 1,048,576): a projection holds at most **524,288** elements (nodes + edges) by default. (A byte-identical projection has one object row and is not subject to this ceiling.)
- **Bytes.** The serialised payload must be ≤ `igpv max_payload_bytes` (default 64 MiB). Depending on address lengths this can be reached before the row ceiling.

Callers may raise either limit through `Limits.lineage` (an `igpv.Limits`). There is no streaming mode in /1.

## 4. Verification

### 4.1 Steps and codes

`project()` and `verify_projection()` share these steps; first failure wins.

| Step | Check | Code |
|---|---|---|
| **Q0 policy** | canonical size ≤ `max_policy_bytes` (for an in-memory `Policy` its canonical serialisation is measured, not only a parsed file); UTF-8; canonical bytes; exact blocks and columns; `policy_spec`; enums, ranges, identifier/id rules; duplicates; ≥ 1 anchor; row budget | `POLICY_MALFORMED`, `POLICY_VERSION_UNSUPPORTED` (spec ≠ `IGP/1`), `PROJECTION_LIMIT_EXCEEDED` |
| **Q1 source** | size ≤ `max_source_bytes`; **exact source acceptance** (below) | `SOURCE_UNSUPPORTED`, `PROJECTION_LIMIT_EXCEEDED` |
| **Q2 selection** | anchors and mandatory nodes exist; node budget satisfiable | `ANCHOR_NOT_FOUND`, `MANDATORY_NOT_FOUND`, `PROJECTION_BUDGET_UNSATISFIABLE` |
| **Q3 output** | lineage row and byte limits (§3.2) | `PROJECTION_LIMIT_EXCEEDED` |
| **Q4 recompute** (`verify_projection` only) | payload parses; producer version equals `IGP_IMPLEMENTATION_VERSION`; recomputed result bytes equal the supplied result; recomputed payload bytes equal the supplied payload (checked in that order) | `LINEAGE_MISMATCH` (unparseable or different payload), `IMPLEMENTATION_VERSION_MISMATCH`, `RESULT_MISMATCH` |

**Ordering.** `verify_projection` first runs `project()` on the supplied source and policy, so any Q0, Q1, Q2 or Q3 error takes precedence; only then does Q4 parse and validate the supplied lineage and compare the outputs in the order shown. A malformed policy or source combined with an invalid lineage therefore reports the Q0 or Q1 error.

**Exact source acceptance (Q1).** A permissive `ISONGraph.from_ison()` success is not sufficient evidence of the required profile. The source is accepted only if **all** hold, else `SOURCE_UNSUPPORTED` (the first failing condition names the field):

1. the bytes are strict UTF-8;
2. they parse as an ISON document with `ison_parser.loads` (not an ISONL loader);
3. the document is not a MultiGraph document (`meta.graph` `format` ≠ `ison-graph-multigraph-v1`);
4. `ISONGraph.from_ison` loads it (twin ids already fail here as in Core) and the graph is **directed**;
5. **canonical profile:** `ISONGraph.to_ison()` of the loaded graph, UTF-8-encoded, equals the source bytes or the source bytes without one trailing LF — the same test IGX/1 uses for `source_canonical`. This is what excludes ISONL and any other syntactic form a permissive parser might accept;
6. every node id satisfies `NodeRef/2` (`18` §1.2): STRING, or INT64 within `[−2^63, 2^63−1]`.

`IGPError(code, field, detail, step)`, `str` = `"{step} {code} {field}: {detail}"` (same shape as `IGXError`/`IGPVError`). Row-level fields are `table.<name>.<row_key>.<column>`; a missing anchor reports `table.anchors.<type>:<id>`.

### 4.2 Recomputation is the proof

`verify_projection(source, policy, result, payload)` does not trust the outputs: it runs `project()` and compares bytes. A projection is therefore verifiable by anyone holding the source and the policy, with no hidden state. It does not run `igpv.verify`; the caller does, with the result's binding, when they want the IGPV/1 guarantees.

### 4.3 Limits

`Limits(max_policy_bytes = 16 MiB, max_source_bytes = 256 MiB, max_rows_per_table = 1_048_576, max_depth = 1_048_576, lineage = igpv.DEFAULT_LIMITS)`. `max_rows_per_table` applies to the policy's tables. Selection is iterative (no recursion); time and memory are `O(V + E)` plus a sort for budget pruning (`O((V + E) log (V + E))`). See §0.2: these bound work only through the source size.

## 5. API and CLI

```python
isongraph_ext.igp
    IGP_SPEC = "IGP/1"; IGP_IMPLEMENTATION_VERSION = "1.0.0"
    IGPError(code, field, detail, step)
    Policy(anchors, mandatory=(), node_types=(), relations=(), direction="out", depth=1, max_nodes=None, max_edges=None)
    Policy.to_ison() -> str          # canonical; Policy.digest == sha256(bytes); Policy.from_ison(text|bytes, *, limits)
    Projection(result_bytes: bytes, payload: ProvenancePayload, policy_sha256: str, stats: Mapping[str, int|bool])
    project(source: bytes, policy: Policy | str | bytes, *, limits=DEFAULT_LIMITS) -> Projection
    verify_projection(source, policy, result: bytes, payload: str|bytes|ProvenancePayload, *, limits) -> Projection
```

`stats` (not part of any wire format; a read-only mapping):

- `source_nodes`, `source_edges` — counts in the accepted source;
- `selected_nodes`, `result_edges` — counts in the result;
- `pruned_nodes` — nodes removed by the node-budget step (§2.5); nodes never selected by the traversal are **not** counted;
- `pruned_edges` — induced edges removed by the edge-budget step (§2.6);
- `truncated` — true if either budget step removed anything.

CLI `python -m isongraph_ext.igp`:

- `project SOURCE POLICY --out DIR` writes `DIR/result.ison` and `DIR/result.igpv.ison` and prints one ISON `meta.projection` block (`source_sha256`, `policy_sha256`, `result_sha256`, `payload_sha256`, the `stats`). Exit 0 / 1 (`meta.error`) / 64.
- `verify SOURCE POLICY RESULT PAYLOAD` — recompute and compare. Exit 0 / 1 / 64.

IGP/1 writes no binding (the caller may bind with `igpv.bind`).

## 6. Conformance vectors (`vectors/igp1/`)

`manifest.ison` → `table.vectors`: `id source policy expect step detail`; expected result and payload bytes are stored beside each passing vector; generator `scripts/make_vectors_igp.py` asserts every row against the runtime. The 61 vectors cover:

- `ok/` (every successful vector's lineage is additionally admitted by `igpv.bind` + `igpv.verify_and_admit` with the source supplied, in the runner and the generator) anchors-only (depth 0) · depth-1 out · depth-2 both · direction in · relation allow-list · node-type allow-list · both lists · empty allow-lists = unrestricted · string and integer ids · same id under different types · **induced edge between siblings / `out` projection containing an incoming edge** · mandatory node inside / outside the traversal · mandatory also anchor · **mandatory node survives while `max_edges` removes its only edge** · **mandatory node outside the traversal introduces an induced edge** · node budget prunes farthest first with tie-break · edge budget prunes by distance · anchors+mandatory exactly equal to `max_nodes` · property carry-over incl. non-ASCII, int, float, bool and null values · stats definitions (`pruned_nodes` excludes never-selected) · **institutional-context** · **supply-chain-impact** · determinism (two runs equal) · lineage verifies end to end through `igpv.verify` · implementation version recorded.
- `reject/` non-canonical policy · duplicate block / unexpected block · wrong `policy_spec` · bad direction · depth out of range · zero anchors · duplicate anchor · id beyond INT64 · twin ids across anchors/mandatory · unknown node-type identifier · anchor not found · mandatory not found · budget unsatisfiable (`|P| > max_nodes`) · **MultiGraph source · undirected source · ISONL source (the exact bytes of an ISONL document) · non-canonical ISON source · source node id beyond INT64 · a source whose property column is named `node_type` (Core itself cannot load it: `add_node` receives the name twice; recorded as a Core limitation, the projection reports `SOURCE_UNSUPPORTED`)** · oversized source / policy (limits) · lineage row limit · lineage byte limit · tampered result bytes · tampered payload · **payload with a different implementation version** · two-faults-first-wins.

## 7. Repository

New package `isongraph_ext.igp` (`errors`, `records`, `policy`, `source`, `select`, `project`, `__main__`), `tests/test_igp_*.py`, `tests/test_vectors_igp.py`, `scripts/make_vectors_igp.py`, `vectors/igp1/`. It imports **public** names from `igpv` only (`records`, `ProvenancePayload`, `bind`, `Limits`, `resolve.node_ref_key`); it needs no private helper. The first delivery is a straightforward BFS projection library with IGPV emission, not an execution framework.

## 8. Out of scope (each a later spec, each needing two independent consumers)

Undirected sources (logical-edge deduplication, canonical endpoint orientation and mirrored-edge budgets would all have to be specified); property equality filters and any predicate (IGP/2 candidate); state, provenance and temporal filters; hierarchy scope; ranking, scoring, relevance or "best N" selection beyond farthest-first budget pruning; mandatory edges or paths; MultiGraph and ISONL sources; node or edge renaming (`rewrite`); a graph-scope derivation; streaming payloads; receipts and ISONCS binding (a later capability); revision-pinned sources (a later capability that needs a frozen graph-identity contract); any change to Core, IGX/1, IGPV/1 or IGDM/1.

## 9. Changes this spec makes to earlier documents

None. IGX/1, IGPV/1 and IGDM/1 are unchanged, and IGP/1 adds no capability registry entry.

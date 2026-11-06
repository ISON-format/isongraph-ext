# IGPV/1 — Provenance: design for E2

Status: **FROZEN 2026-11-06 (E2, rev 1)** · Implements planmap `01` E2 and the provenance half of `04` in `ISON-format/isongraph-ext`, binding through `17-IGX1-DESIGN.md` (FROZEN rev 3) as the capability `igpv`. Nothing here touches revision, delta, Datamatics, projection or DAG; E5/E6 *emit* IGPV/1 records, E2 *defines and verifies* them. Provenance merge and conflict-resolution rules are explicitly outside this spec (§8). Changing §1–§6 after implementation ships is a new spec version (`IGPV/2`), never an edit.

## 0. What E2 delivers

A companion artifact `<graph>.igpv.ison` that states, for one exact ISONGraph artifact (the **target graph**):

1. **Source attribution** — which content-addressed artifacts (SHA-256 mandatory; revision, URI, media type optional) graph material came from, and where inside them when the producer knows (§2).
2. **Producer attribution** — which extractor or transformation (implementation, version, optional spec and policy digest) asserted it.
3. **Graph-object provenance** — attributions at graph, node and edge scope, addressed by `NodeRef/2` and `EdgeAddress/2` (§1.2).
4. **Derivation lineage** — derived objects in the target graph mapped to origin objects in other exact graph artifacts, one-to-many and many-to-one, as E6 `collapse_scc` and E5 projection need (§3).
5. **Deterministic verification** — canonical bytes, structural validation, reference resolution against the pinned Core runtime, locator verification posture, resource budgets, stable failure codes, bounded lineage traversal (§4, §5).
6. **Conformance vectors** — positive, malformed, mismatched, unresolved, ambiguous, multi-origin and determinism cases (§6).

The E2 acceptance law:

> Every IGPV/1 attribution identifies an exact source artifact, every derivation preserves traceable original graph-object identities, and every provenance claim can be structurally verified without treating source attribution as proof of correctness.

The lineage invariant E5/E6 inherit:

> Every derived graph object produced by E5 Projection or E6 DAG Projection must be traceable through IGPV/1 to its originating graph objects and source revision, without E5/E6 inventing a competing provenance model.

### 0.1 Three questions, never merged

| question | who answers | how |
|---|---|---|
| Does the provenance payload match the digest the IGX/1 binding declares? | IGX/1 binding integrity | `table.capabilities` row `igpv` → `payload_sha256` (§4 P0) |
| Do the records correctly reference graph objects, source artifacts, producers and derivations? | IGPV/1 structural verification | §4 P1–P5 |
| Is the extracted assertion actually true? | downstream domain validation | **not IGPV/1** |

A record saying an extractor produced an edge does not prove the edge is semantically correct. A SHA-256 identifies bytes; it does not authenticate their origin. IGPV/1 carries no confidence, authority or truth field, and a verifier never infers one.

## 1. Wire format and addressing

One companion document `<graph>.igpv.ison`. Its bytes are **exactly** ison-py's canonical writer output (`dumps_canonical`, UTF-8, no trailing newline — `17` §2.1 applies verbatim); any other byte sequence is not an IGPV/1 payload (`MALFORMED_PROVENANCE`, field `canonical_form`). The writer decides block order (by `kind.name`), field order and quoting; the examples below are shown as the writer emits them (string tokens that look typed — `"0"`, `"1"`, `"true"`, `""` — are quoted, integers are bare, so `INT64` and `STRING` ids survive the wire). **Row order is canonical and deterministic**: the canonical writer orders the rows of every table by every column in canonical field order (ordinal UTF-8 bytes, nulls last at each position), so two producers emitting the same set of records obtain the same bytes and the same digest, and a file whose rows are in any other order fails the canonical re-emission check. *Post-freeze clarification (2026-11-06, E2 execution): rev 1 said rows are sorted "by key column"; ison-py 1.2.0's `dumps_canonical` sorts rows itself on all columns, which makes a key-column order unreachable on the wire. The guarantee (same records → same bytes; non-canonical order rejected) is unchanged; only the stated mechanism was wrong. The example below is in the writer's order.* Exactly these six blocks, each **exactly once**; any other block or a duplicate is `MALFORMED_PROVENANCE`. Tables may be empty (header only).

```text
meta.igpv
provenance_spec target_artifact_sha256 target_semantic_digest target_semantic_digest_algorithm target_serialization_profile
IGPV/1 <64hex> null null ison-v1

table.artifacts
artifact_id artifact_sha256 kind media_type revision serialization_profile size uri
g0 <64hex> isongraph null null ison-v1 2210 null
src0 <64hex> document text/markdown 9f1c2e3d null 18422 file:///docs/orders.md

table.producers
implementation kind policy_sha256 producer_id spec version
betterify-ri-extractor extractor null x0 null 2.3.0
isongraph-ext transformation <64hex> t0 IGDAG/1 0.2.0

table.objects
graph kind node_id node_type object_id ordinal relation source_id source_type target_id target_type
g0 node 7 p o7 null null null null null null
g0 node 8 p o8 null null null null null null
g0 node 9 p o9 null null null null null null
null edge null null e1 "0" knows 1 p s1 p
null graph null null G null null null null null null
null node 1 p n1 null null null null null null
null node s1 p n2 null null null null null null

table.attributions
artifact_id attribution_id locator_end locator_start locator_text locator_type object_id producer_id
src0 a0 1240 880 null bytes/1 n1 x0
src0 a1 null null null null n2 x0
src0 a2 42 40 null lines/1 e1 x0

table.derivations
derivation_id derived_object_id kind origin_object_id producer_id
d0 n1 collapse o7 t0
d1 n1 collapse o8 t0
d2 n1 collapse o9 t0
```

### 1.1 Blocks and fields

**`meta.igpv`** — one row.
- `provenance_spec` = `IGPV/1`.
- `target_artifact_sha256` — 64 lowercase hex: `sha256` of the exact target-graph bytes (framing as `17` §2.1: the bytes handed to the runtime, no normalisation). This is the payload's own statement of what it describes; it never relies on the filename or on the IGX/1 binding (§4 P2 requires all three to agree).
- `target_serialization_profile ∈ { ison-v1, isonl-v1 }` — must equal the binding's `serialization_profile`.
- `target_semantic_digest`, `target_semantic_digest_algorithm` — `null` until Semantic/2 freezes; non-null is `MALFORMED_PROVENANCE` (same rule as `17` §2).
- The payload holds **no** IGX binding digest: the binding carries the payload's digest, so a payload carrying the binding's would be circular.

**`table.artifacts`** — the content-addressed things provenance points at. `artifact_id` is the row key (§1.3 token), unique.
- `artifact_sha256` — 64 hex, **mandatory and unique in the table**: one artifact record per content digest, so a digest names exactly one logical artifact inside a payload and `Lineage` (§5.2), which identifies graphs by digest, never meets two records for one graph. A producer that knows several URIs or revision labels for the same bytes records one of them (alternate labels are not representable in IGPV/1; a later revision may add a label table).
- `kind ∈ { document, isongraph }`. `isongraph` means the bytes are an ISONGraph document under `serialization_profile` (non-null iff `kind = isongraph`); only `isongraph` artifacts may be origin graphs (§3). `document` is any other bytes.
- `size` — INT64 ≥ 0, mandatory: the byte length of the artifact. Lets P1 bound byte-range locators without the bytes (a range past `size` is malformed, not merely unverified).
- `media_type` — null or an RFC 6838 `type/subtype` token. `revision` — null or a non-empty string: the producer's revision label for the artifact (git object id, version, timestamp — opaque to Ext). `uri` — null or a non-empty string, opaque. None of these three is identity; `artifact_sha256` is.
- An artifact row whose digest equals `target_artifact_sha256` is permitted only with `kind = isongraph` and is never a valid origin graph (§3 forbids self-derivation); it may be attributed to (a graph may cite itself as the document it was read from, which is a true statement).

**`table.producers`** — who asserted. `producer_id` key, unique.
- `kind ∈ { extractor, transformation }`. `implementation` — non-empty string (e.g. `betterify-ri-extractor`, `isongraph-ext`). `version` — non-empty string, opaque (not required to be SemVer: extractors are not Ext). `spec` — null or the spec the transformation implements (`IGP/1`, `IGDAG/1`, …; opaque token to E2). `policy_sha256` — null or 64 hex: the digest of the policy artifact a transformation ran with (the hook `08` receipt chains use). Cross-field: `extractor ⇒ policy_sha256 null`.

**`table.objects`** — every graph object the payload mentions, once. `object_id` key, unique. `graph` is `null` for an object **in the target graph**, or an `artifact_id` with `kind = isongraph` for an object in an **origin graph**. `kind ∈ { graph, node, edge }`. Address columns by kind (all others null):

| kind | non-null columns |
|---|---|
| `graph` | none (the artifact named by `graph`, or the target) |
| `node` | `node_type`, `node_id` |
| `edge` | `source_type`, `source_id`, `relation`, `target_type`, `target_id`, `ordinal` |

Two rows with the same `graph` and the same address are a duplicate (`MALFORMED_PROVENANCE`). Address rules are §1.2.

**`table.attributions`** — "object came from artifact, said producer". `attribution_id` key, unique. `object_id`, `artifact_id`, `producer_id` are references (§4 P3). Locator columns are §2. The same `(object_id, artifact_id, producer_id, locator)` tuple twice is a duplicate. An object may carry any number of attributions (several sources, several producers): that is multiple origin **support**, not merging — E2 records them side by side and ranks nothing. Attributions may name objects in origin graphs too (a transformation may restate where an origin node came from); nothing requires it.

**`table.derivations`** — "derived object in the target graph was made from origin object", §3. `derivation_id` key, unique.

**Reachability.** Every row must be reachable from an attribution or a derivation, through these references and no others: an attribution references its `object_id`, `artifact_id` and `producer_id`; a derivation references its `derived_object_id`, `origin_object_id` and `producer_id`; an object references the artifact named by its `graph` column. So an origin-graph artifact referenced only through `objects.graph` of an origin object that a derivation uses is reachable; an artifact, producer or object that nothing reaches is `MALFORMED_PROVENANCE` (provenance that cites nothing is noise, and a verifier must not have to guess why it is there). No row is required: a payload whose five tables are all empty is valid and states that nothing is attributed.

### 1.2 Object addressing (pinned to Semantic/2 `13` §1.5, §2.2, §2.3)

```text
NodeRef/2    = ( node_type: STRING, node_id: INT64 | STRING )
EdgeAddress/2 = ( source_ref: NodeRef/2, relation: STRING, target_ref: NodeRef/2, ordinal: STRING )
```

- `node_type`, `relation` (and the endpoint types) are Core identifiers: non-empty, no whitespace, none of `:`, `|`, `"`, `\` — Core's `_check_identifier` rule, enforced at P1 so an unrepresentable address fails before a graph is loaded.
- `node_id` (and `source_id`, `target_id`) is an ISON integer or string **as typed on the wire**: `1` is `INT64(1)`, `"1"` is `STRING("1")`; they are different addresses, and a payload that uses `"1"` where the graph holds `1` does not resolve (P4). Booleans, floats and null are not ids (`MALFORMED_PROVENANCE`). Integers must lie within INT64 (`-2^63 ≤ id ≤ 2^63-1`): the addressing contract is `NodeId/2`, and an id outside it is `MALFORMED_PROVENANCE` — such a graph is `ineligible` under IGX/1 §4.1 and IGPV/1 cannot address its objects.
- **ID-TWIN-INVARIANT** (`13` §1.5): Core rejects, within one node type, an integer id and a string id with the same canonical decimal spelling (`1` / `"1"`, `-1` / `"-1"`). A payload therefore must not address both twins of such a pair in the same graph (same `graph`, same `node_type`): that is `MALFORMED_PROVENANCE` at P1, because no Core graph can hold them. Typed distinction is exercised across separately identified graphs (§6 `ok/typed-ids-distinct-across-graphs`) and by non-resolution (§6 `reject/unresolved-node`), never by twins in one graph.
- `ordinal` is a **string**: the canonical decimal spelling (`0|[1-9][0-9]*`) of the Core MultiGraph key, and exactly `"0"` for an edge of a simple `ISONGraph`. It is quoted on the wire by the writer. Semantic/2 keeps the ordinal opaque; E2 pins the Core binding of it.
- **Undirected target graph** (`meta.graph.directed false`): an edge is addressed by its *logical* address — endpoints in canonical order `(min(NodeRef), max(NodeRef))` with the `13` §2.3 ordering (type bytes, then id with `INT64 < STRING`, ints numerically, strings by UTF-8 bytes). A row whose endpoints are not in canonical order is `UNRESOLVED_OBJECT` at P4 (detail `endpoints not canonical`), never silently normalised. Directed graphs keep source/target as written.
- Objects in origin graphs follow the same rules; the origin graph's directedness is known only when its bytes are supplied (§4 P4), so canonical-order checking of origin edges happens only then.
- Reference text (`:p:1`) never appears in a payload; addresses are typed columns.

### 1.3 Tokens

Row keys (`artifact_id`, `producer_id`, `object_id`, `attribution_id`, `derivation_id`) match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` and are unique within their table. They are **local to the payload** and carry no meaning across payloads; cross-payload identity is `(artifact_sha256, address)` (§5.2). Hex is lowercase. `size`, `locator_start`, `locator_end` are INT64.

## 2. Source locators

A locator says *where inside* an artifact an attribution points. It is optional: absence never invalidates an attribution (whole-document, model-assisted, aggregated and external-system provenance legitimately have no coordinates, and a schema that demanded one would make producers invent them).

| `locator_type` | `locator_start` / `locator_end` | `locator_text` | meaning |
|---|---|---|---|
| `null` | null | null | the whole artifact |
| `bytes/1` | INT64, `0 ≤ start ≤ end ≤ size` | null | zero-based, half-open byte interval `[start, end)` of the artifact bytes |
| `lines/1` | INT64, `1 ≤ start ≤ end ≤ size` | null | one-based, **inclusive** line interval `[start, end]` over the artifact's lines, counted as: `line_count = number of LF bytes + (1 if size > 0 and the last byte is not LF else 0)`. LF (`0x0A`) is the only delimiter; a CR before it belongs to the line. So `""` → 0 lines, `"\n"` → 1 (one empty line), `"a"` → 1, `"a\n"` → 1, `"a\n\n"` → 2 (the second empty), `"a\r\nb"` → 2. An artifact of `size` bytes has at most `size` lines, which is the P1 bound |
| `x-<name>/<n>` | null | non-empty string | a producer-defined, versioned locator (`x-[a-z0-9-]+/[1-9][0-9]*`); opaque to Ext, **never verified** |

P1 checks the table above (shape, bounds against `size`). Whether the span is *correct* is a separate question with a separate posture:

```text
UNVERIFIED   the default: shape-valid, bytes not checked
VERIFIED     the artifact bytes were supplied, hashed to artifact_sha256, and the span lies within them
             (bytes/1: end ≤ len; lines/1: end ≤ line count)
```

`INVALID` is not a posture — a span that fails against supplied bytes is a verification failure (`LOCATOR_INVALID`, §4 P5). The posture is **reported in the verification result, never stored in the payload**: a stored "verified" would be a claim the verifier may be unable to re-check (the bytes may not be at hand), and IGX/1's rule that evidence is what the runtime derived, not what the file says, applies. `x-*` locators stay `UNVERIFIED` forever.

Derivation independence: an E5/E6 transformation that carries an attribution across from an origin object copies it unchanged, locator or not; it never drops an attribution because the locator is absent or `x-*`.

## 3. Derivation lineage

A derivation row states that `derived_object_id` (an object with `graph = null`, i.e. in the target graph) was produced from `origin_object_id` (an object whose `graph` names an `isongraph` artifact) by `producer_id` (any kind; transformations are the expected case).

- `kind ∈ { identity, collapse, rewrite }`:
  - `identity` — the derived object *is* the origin object carried over: same object kind, same address (types, ids, relation, ordinal). A derived object with an `identity` row has exactly that one derivation row.
  - `collapse` — the derived object stands for the set of its origins (one or more rows share `derived_object_id`): E6 `collapse_scc` makes one node from an SCC's nodes.
  - `rewrite` — the derived object was constructed from its origin(s) with a changed address: an edge re-targeted onto an SCC node, a node renamed by a projection. One or more origins.
  - All kinds: origin and derived objects have the **same object kind** (node→node, edge→edge, graph→graph). Material that vanishes (edges inside a collapsed SCC) has no derived object and no row; material created from nothing has no derivation row and is attributed instead (§1.1).
- **Many-to-one** (several rows with one `derived_object_id`) and **one-to-many** (one `origin_object_id` feeding several derived objects) are both permitted; `(derived_object_id, origin_object_id)` is unique.
- **Distinct graphs.** The origin graph's `artifact_sha256` must differ from `target_artifact_sha256`; an origin object with `graph = null` is `INVALID_DERIVATION` (self-derivation), as is a derived object with `graph ≠ null`. Hence within one payload the derivation relation is bipartite (target ← origins) and cannot cycle.
- **Across payloads** a chain is G″ ← G′ ← G, each step its own payload. Content addressing does not prevent two payloads from naming each other's targets as origins (a payload is not part of its target's bytes), so the lineage resolver (§5.2) treats a repeated **object** — the same `(artifact_sha256, address)` — on the active path as `DERIVATION_CYCLE` and refuses, and bounds depth and visits (§4.3). A path may legitimately pass through one graph twice via different objects; it may never return to the same object.
- Multiple origins are **support, not fusion**: three rows pointing at `n1` say `n1` stands for `o7`, `o8`, `o9`. How to combine their properties, authority, confidence or contradictions is merge semantics, deferred (§8).

## 4. Verification and admission

### 4.1 Verification order (deterministic; first failure wins; `IGPVError.step` names it)

`verify()` performs the IGX/1 verification of the binding **itself** (`17` §4, raising `IGXError` exactly as `igx.verify()` does) and takes only that result as evidence: no public IGPV/1 operation accepts a caller-supplied `igx.VerificationResult`, because a hand-built result carrying the right digest is not evidence that IGX/1 verification happened (the same boundary `17` §3 draws around `admit()`).

Execution order is fixed, and the **byte-budget preflight runs first**, before IGX/1 or Core touches any bytes:

```text
preflight   P1 byte budgets on lengths only (payload, target, each source, sum of sources)   → PROVENANCE_LIMIT_EXCEEDED
P0          igx.verify(binding, target)  then  igpv row, version range, payload digest
P1          parse the payload; row budgets; shape
P2          target binding
P3          references and derivations
P4          graph-object resolution
P5          source locator verification
```

The preflight is reported as step `P1` (it is P1's limits rule, hoisted), so an oversized target with an invalid IGX/1 binding fails with `PROVENANCE_LIMIT_EXCEEDED` at `P1`, never with the `IGXError` — the limit wins. Steps:

| step | checks | code on failure |
|---|---|---|
| **P0 binding** | *(after the preflight)* `igx.verify(binding, target, baselines=…, registry=…)` succeeds; its result is the evidence for P4's mode | *(`IGXError`, V0–V5)* |
| | `table.capabilities` has a row `extension = igpv` with non-null `payload_sha256` | `PROVENANCE_NOT_BOUND` |
| | that row's `version_range` admits `1.0.0` (`17` §2 range semantics; checked here for `OPTIONAL` rows too — IGX/1 V5 only ranges `REQUIRED` ones) | `PROVENANCE_VERSION_UNSUPPORTED` |
| | `payload_sha256 == sha256(payload bytes)` | `PAYLOAD_DIGEST_MISMATCH` |
| **P1 shape** | budgets (§4.3): the byte budgets are the **preflight** above (payload bytes ≤ `max_payload_bytes`; target bytes ≤ `max_graph_bytes`; each supplied source ≤ `max_graph_bytes`; sum of all supplied sources ≤ `max_sources_bytes`), checked on lengths before P0; after parsing the payload, every table's row count ≤ `max_rows_per_table` (which also bounds P3–P5 work, since resolution is one lookup per row) | `PROVENANCE_LIMIT_EXCEEDED` |
| | bytes equal the canonical re-emission (`canonical_form`, which includes row order §1); six blocks exactly once; fields present with the right types; `provenance_spec = IGPV/1`; `target_semantic_digest*` null; enums; key tokens and uniqueness (§1.3); `artifact_sha256` unique; per-kind null patterns in `table.objects`; identifier shape, INT64 ids and the twin rule (§1.2); `ordinal` spelling; locator shape and bounds against `size` (§2); duplicate rows (§1.1); unreachable artifact/producer/object rows (§1.1); `extractor ⇒ policy_sha256 null`; `isongraph ⇔ serialization_profile non-null` | `MALFORMED_PROVENANCE` |
| **P2 target** | `target_artifact_sha256 == sha256(target bytes)` **and** `== binding.artifact_sha256`; `target_serialization_profile == binding.serialization_profile` | `TARGET_BINDING_MISMATCH` |
| **P3 references** | every `object_id`, `artifact_id`, `producer_id` in attributions and derivations exists; `objects.graph` names an artifact with `kind = isongraph`; derivation rules of §3: derived in target, origin in an origin graph, origin graph digest ≠ target digest, same object kind, `identity` ⇒ single row and equal address, `(derived, origin)` unique | `UNRESOLVED_REFERENCE` (dangling) / `INVALID_DERIVATION` (§3 rule) |
| **P4 objects** | *(runs only when the IGX result is `semantic_verification = full`; in `limited` mode it is skipped and the result says `object_resolution = skipped`)* load the target bytes with the pinned Core loader for the profile (`ISONGraph` or `MultiGraph` by `meta.graph.format`, exactly as `17` §4 V4); every object with `graph = null` must exist: node by `has_node(type, id)` with the typed id; edge by `has_edge(relation, source, target[, key])` with `key = int(ordinal)` for a MultiGraph and `ordinal = "0"` required for a simple graph; undirected graphs: endpoints must be in canonical order (§1.2) and the edge is looked up as the logical edge. Then, for each origin graph whose bytes were supplied in `sources`: `sha256(bytes) == artifact_sha256` **and** `len(bytes) == size` (`SOURCE_ARTIFACT_MISMATCH`), load it the same way and resolve its objects; origin graphs not supplied are reported `unverified` | `UNRESOLVED_OBJECT` |
| **P5 locators** | for each attribution whose artifact bytes were supplied in `sources`: `sha256(bytes) == artifact_sha256` and `len(bytes) == size` (`SOURCE_ARTIFACT_MISMATCH`); `bytes/1`: `end ≤ len` — always true once the two checks above and P1's `end ≤ size` have passed, so for `bytes/1` the posture becomes `VERIFIED` without a reachable failure; `lines/1`: `end ≤ line_count` (§2) → `VERIFIED`, else `LOCATOR_INVALID` (reachable: a range within the byte size but past the real line count); not supplied or `x-*` → `UNVERIFIED` | `LOCATOR_INVALID` |

Every code is deterministic, carries the offending field (`table.row_key.column` for row-level faults), and never degrades to a warning. A payload that is unknown to a consumer is never "verified provenance": an `OPTIONAL` `igpv` row on a runtime without IGPV/1 is preserved in `unrecognized_optional` (IGX/1 V5) and nothing interprets it; a `REQUIRED` row on such a runtime is `UNSUPPORTED_CAPABILITY`; a binding with no `igpv` row has no provenance, and `verify()` says so (`PROVENANCE_NOT_BOUND`) rather than returning an empty success.

### 4.2 Admission

IGPV/1 adds **no admission policy of its own** in E2. A payload is admitted iff IGPV/1 verification P0–P5 succeeded **and** its IGX/1 binding is admitted (`17` §4.2 A0–A3); verification is the prerequisite (a payload that fails P0–P5 raises and is never admitted), admission is the binding's decision. `verify_and_admit()` returns the binding's `AdmissionResult` unchanged, so `receipt_posture` (`OK`, `CORE_LOSSY`, `CORE_BLOCKING_DIVERGENCE`, `INADMISSIBLE`) and the reasons are the binding's. Provenance binding is an identity-sensitive operation under `16` §4 — the identity it binds to is the **artifact** identity of the target and of each origin graph (SHA-256 of bytes), which every posture may carry; a `producer_bound` claim on the binding is admitted or denied exactly as IGX/1 decides, and IGPV/1 neither strengthens nor weakens it. When Semantic/2 freezes, `IGPV/2` may admit lineage across semantic identities; `IGPV/1` lineage is artifact-to-artifact.

### 4.3 Resource budgets

```python
@dataclass(frozen=True)
class Limits:
    max_payload_bytes: int = 64 * 1024 * 1024    # P1, before parsing the payload
    max_graph_bytes: int = 256 * 1024 * 1024     # P1, before loading: the target and each supplied origin graph
    max_sources_bytes: int = 1024 * 1024 * 1024  # P1, before anything: sum of all supplied source bytes
    max_rows_per_table: int = 1_048_576          # P1; bounds P3–P5 work (one lookup per row)
    max_lineage_depth: int = 64                  # §5.2 traversal
    max_lineage_visits: int = 1_048_576          # §5.2 objects visited per query
DEFAULT_LIMITS = Limits()
```

Exceeding a limit is `PROVENANCE_LIMIT_EXCEEDED` (verification) or `LINEAGE_BUDGET_EXCEEDED` (traversal); both name the limit in `field`. Every byte budget is checked on lengths in the §4.1 preflight, before any parser or Core loader runs (including the IGX/1 verification inside P0), so a small payload cannot make the verifier parse an unbounded graph.

## 5. Runtime API (`isongraph_ext.igpv`, Python 3.12)

Same pins as E1 (`ison-graph==1.4.1`, `ison-py==1.2.0`); the IGPV/1 runtime is the IGX/1 runtime plus one package.

### 5.1 Records and payload

```python
@dataclass(frozen=True)
class Artifact:   artifact_id: str; artifact_sha256: str; kind: Literal["document","isongraph"]; size: int
                  media_type: str | None = None; revision: str | None = None; uri: str | None = None
                  serialization_profile: Literal["ison-v1","isonl-v1"] | None = None
@dataclass(frozen=True)
class Producer:   producer_id: str; kind: Literal["extractor","transformation"]; implementation: str; version: str
                  spec: str | None = None; policy_sha256: str | None = None
@dataclass(frozen=True)
class NodeRef:    node_type: str; node_id: int | str
@dataclass(frozen=True)
class EdgeAddress: source: NodeRef; relation: str; target: NodeRef; ordinal: str = "0"
@dataclass(frozen=True)
class GraphObject: object_id: str; kind: Literal["graph","node","edge"]; graph: str | None = None   # artifact_id or None (target)
                  node: NodeRef | None = None; edge: EdgeAddress | None = None
@dataclass(frozen=True)
class Locator:    type: str; start: int | None = None; end: int | None = None; text: str | None = None
@dataclass(frozen=True)
class Attribution: attribution_id: str; object_id: str; artifact_id: str; producer_id: str; locator: Locator | None = None
@dataclass(frozen=True)
class Derivation: derivation_id: str; derived_object_id: str; origin_object_id: str; producer_id: str
                  kind: Literal["identity","collapse","rewrite"]

@dataclass(frozen=True)
class LineageStep: depth: int; graph_sha256: str; obj: NodeRef | EdgeAddress | None; kind: str | None   # derivation kind
                  producer: Producer | None; terminal: Literal["no_derivation_record","payload_unavailable"] | None
                  # terminal: "payload_unavailable" = no payload loaded for graph_sha256; "no_derivation_record" = the
                  # loaded payload holds no derivation for this object — which says nothing about whether it originated there

@dataclass(frozen=True)
class ProvenancePayload:
    target_artifact_sha256: str; target_serialization_profile: str
    artifacts: tuple[Artifact, ...]; producers: tuple[Producer, ...]; objects: tuple[GraphObject, ...]
    attributions: tuple[Attribution, ...]; derivations: tuple[Derivation, ...]
    def to_ison(self) -> str                                    # canonical writer output, no trailing newline
    @classmethod
    def from_ison(cls, text: str, *, limits: Limits = DEFAULT_LIMITS) -> "ProvenancePayload"
                                                                # raises IGPVError(MALFORMED_PROVENANCE | PROVENANCE_LIMIT_EXCEEDED, step="P1")
    @property
    def digest(self) -> str                                     # sha256(to_ison().encode("utf-8")) == payload_sha256 in the binding
    def check(self) -> None                                     # the P1 rules that need no bytes; raises IGPVError

class IGPVError(Exception): code: str; field: str; detail: str; step: str    # step ∈ P0..P5, L (lineage)
```

Records are immutable; `ProvenancePayload` construction does not validate (so E5/E6 can build incrementally), `check()`/`to_ison()`/`from_ison()` do. `from_ison()` rejects non-canonical text exactly as `17` §2.1.

### 5.2 Operations

```python
DEFAULT_REGISTRY: igx.CapabilityRegistry = {"igpv": "1.0.0"}   # defined in igx.registry, re-exported here; replaces
                                                               # EMPTY_REGISTRY as the production default (§9)

def bind(target: str | bytes, payload: ProvenancePayload, *, requirement: Literal["REQUIRED","OPTIONAL"] = "REQUIRED",
         serialization_profile: str, producer_port: str, identity_claim: str,
         capabilities: Sequence[igx.Capability] = (), consumer: igx.Consumer | None = None,
         baseline=igx.DEFAULT_BASELINE, registry=DEFAULT_REGISTRY, policy=igx.DEFAULT_POLICY,
         sources: Mapping[str, bytes] = {}, limits: Limits = DEFAULT_LIMITS) -> igx.ExtensionBinding
    # payload.check(); requires payload.target_artifact_sha256 == sha256(target) and profile equality (else IGPVError
    # TARGET_BINDING_MISMATCH, step P2); appends Capability("igpv", "^1", requirement, payload.digest) (an existing igpv
    # row is MALFORMED_PROVENANCE); calls igx.bind(...) (raises IGXError as E1 does); then verify() below. Never returns
    # a binding whose provenance it would not verify.

def verify(payload: str | bytes | ProvenancePayload, binding: igx.ExtensionBinding, target: str | bytes, *,
           sources: Mapping[str, bytes] = {}, limits: Limits = DEFAULT_LIMITS,
           baselines=igx.BASELINES, registry=DEFAULT_REGISTRY
          ) -> tuple[igx.VerificationResult, ProvenanceVerification]
    # Budgets, then igx.verify() (P0, raises IGXError), then P0–P5 (raises IGPVError on the first failing step).
    # The IGX result it returns is the one it produced; there is no parameter to supply one. `sources` maps
    # artifact_sha256 -> bytes for any artifacts the caller can supply (origin graphs, source documents);
    # absence is never a failure, only an UNVERIFIED posture.

def verify_and_admit(payload, binding, target, *, sources={}, limits=DEFAULT_LIMITS, baselines=igx.BASELINES,
                     registry=DEFAULT_REGISTRY, policy=igx.DEFAULT_POLICY
                    ) -> tuple[igx.VerificationResult, ProvenanceVerification, igx.AdmissionResult]
    # verify() above, then igx.admit(binding, that_result, policy=policy); the AdmissionResult is the binding's (§4.2).

@dataclass(frozen=True)
class ProvenanceVerification:
    payload_sha256: str; binding_digest: str; target_artifact_sha256: str
    object_resolution: Literal["full","skipped"]                       # P4 on the target: "skipped" iff IGX was "limited"
    origin_resolution: Mapping[str, Literal["verified","unverified"]]   # artifact_id of each origin graph -> P4 outcome
    locators: Mapping[str, Literal["VERIFIED","UNVERIFIED"]]            # attribution_id -> P5 posture (rows with a locator)
    counts: Mapping[str, int]                                          # table name -> rows
    steps_passed: tuple[str, ...]                                      # ("P0","P1","P2","P3","P4","P5"); P4 present in both modes

class Lineage:
    def __init__(self, payloads: Iterable[ProvenancePayload], *, limits: Limits = DEFAULT_LIMITS)
        # indexes payloads by target_artifact_sha256; two payloads for one target raise IGPVError(LINEAGE_AMBIGUOUS, step="L")
        # — provenance for one graph from two payloads is merge territory (§8), not a query the resolver may answer
    def origins_of(self, graph_sha256: str, obj: NodeRef | EdgeAddress | None) -> tuple[LineageStep, ...]
        # transitive closure over derivations: (graph_sha256, address) -> origin (graph_sha256, address, kind, producer),
        # depth-first in canonical record order; bounded by limits.max_lineage_depth / max_lineage_visits
        # (LINEAGE_BUDGET_EXCEEDED); the same (graph_sha256, address) twice on the active path is DERIVATION_CYCLE (§3);
        # a chain ends with terminal = "payload_unavailable" when no payload is loaded for the origin graph, or
        # "no_derivation_record" when the loaded payload holds none for the object — the resolver never guesses origin
    def attributions_of(self, graph_sha256: str, obj: NodeRef | EdgeAddress | None) -> tuple[Attribution, ...]
        # direct attributions of the object in the payload for graph_sha256; () if that payload holds none
```

`Lineage` is **read-only and bounded**; it never merges records, never ranks origins, never loads graphs, and never re-verifies: it answers over whatever parsed payloads it was given, so the caller verifies each payload first (§4) or knowingly queries unverified claims.

### 5.3 Failure contract

| operation | failure behaviour |
|---|---|
| `from_ison()`, `check()` | raise `IGPVError` with code `MALFORMED_PROVENANCE` or `PROVENANCE_LIMIT_EXCEEDED`, step `P1` |
| `verify()` | raises `IGXError` (P0, as `igx.verify()`) or `IGPVError` (P0–P5); returns only on full success |
| `verify_and_admit()` | raises `IGXError` as `igx.verify()`; raises `IGPVError` as `verify()`; returns the triple; a denial is in the `AdmissionResult`, never raised |
| `bind()` | raises `IGXError` or `IGPVError`; never returns a binding it would not verify and admit |
| `Lineage` | raises `IGPVError` (`LINEAGE_AMBIGUOUS`, `DERIVATION_CYCLE`, `LINEAGE_BUDGET_EXCEEDED`, step `L`) |
| CLI `python -m isongraph_ext.igpv verify <graph> <binding> <payload> [--source SHA256=PATH]... [--allow-retired]` | exactly `verify_and_admit()`: IGPV verify (which runs IGX verify inside P0), P0–P5 passed, **then** IGX admit; prints the three results as ISON (`meta.verification`, `meta.provenance`, `meta.admission`) exit **0**; `IGXError`/`IGPVError` printed as `meta.error`, exit **1** — no `meta.admission` is ever printed for a payload that failed verification; admission denied, exit **2**; usage error exit **64** |
| CLI `python -m isongraph_ext.igpv origins <graph-sha256> <payload>...` with `--node TYPE ID` or `--edge STYPE SID REL TTYPE TID [ORDINAL]` (neither = the graph object) | ids are ISON tokens (`1` is INT64, `"1"` is STRING, shell-quoted as needed); prints lineage steps as `table.lineage`; exit 0 / 1 on `IGPVError` / 64 usage |

Streams are UTF-8 with `\n` newlines as in E1.

## 6. Conformance vectors (`vectors/igpv1/`)

`manifest.ison` → `table.vectors`: `id target binding payload sources expect step detail`. `target` is a graph under `graphs/` (Core corpus copies as in `17` §5, plus synthetic derived graphs under `graphs/synthetic/`); `binding` under `bindings/`, `payload` under `payloads/` (byte-exact, `-text`); `sources` is `none` or a `+`-joined list of `sources/` files whose names are their sha256. `expect ∈ { verify_ok, reject:<CODE>, admit_ok, admit:<CODE>, lineage_ok, lineage:<CODE> }`, `+`-joined. `step` is the exact P/L step. `detail` carries `locator:<attribution_id>=<POSTURE>`, `origin:<artifact_id>=<status>`, `resolution:skipped`, `origins:<n>` assertions. Every vector is asserted against the runtime by `scripts/make_vectors.py` before it is written; `tests/test_vectors.py` is the reference runner and additionally checks every positive payload re-serialises byte-identically with equal digest.

| id | expect | step |
|---|---|---|
| ok/attribution-whole-artifact | verify_ok (no locator) + admit_ok | — |
| ok/attribution-bytes-locator-unverified | verify_ok, `locator:a0=UNVERIFIED` (sources none) | — |
| ok/attribution-bytes-locator-verified | sources supplied → `locator:a0=VERIFIED` | — |
| ok/attribution-lines-locator-verified | `lines/1` over a CRLF document (CR stays in the line) → `VERIFIED` | — |
| ok/attribution-x-locator-stays-unverified | `x-pdf-page/1` with sources supplied → `UNVERIFIED` | — |
| ok/multiple-sources-one-object | one node, three attributions (two artifacts, two producers) | — |
| ok/typed-ids-distinct-across-graphs | two targets, one holding `p 1`, one holding `p "1"`; each payload addresses its own typed id and resolves; swapping the payloads is `reject/unresolved-node` | — |
| ok/edge-int-and-string-endpoints | edge `p 1 knows p "s1"` (no twin) resolved with both endpoint types | — |
| ok/multigraph-ordinals | MultiGraph target, ordinals `"0"`, `"1"`, `"10"` resolved by key | — |
| ok/undirected-logical-edge | undirected target, canonical endpoint order → resolved | — |
| ok/graph-scope-attribution | the target graph object attributed to a document | — |
| ok/derivation-identity | projection copy: `identity`, origin graph supplied → `origin:g0=verified` | — |
| ok/derivation-collapse-many-to-one | three origin nodes → one derived node, `collapse` | — |
| ok/derivation-rewrite-edge | edge re-targeted onto a collapsed node | — |
| ok/derivation-origin-unverified | origin graph bytes not supplied → `origin:g0=unverified`, verify_ok | — |
| ok/limited-runtime-skips-resolution | retired test baseline (as `17` ok/retired-baseline-verifies): `resolution:skipped`, admit:`STALE_BINDING`, admit_ok with `--allow-retired` | — |
| ok/optional-igpv-row | binding row `igpv ^1 OPTIONAL` → verify_ok | — |
| ok/reserialize-stable | `from_ison(to_ison(p)).to_ison() == to_ison(p)`, digest equals file bytes' | — |
| ok/empty-provenance | all five tables empty; verify_ok (a true statement: nothing is attributed) | — |
| reject/not-bound | binding without an `igpv` row → `PROVENANCE_NOT_BOUND` | P0 |
| reject/payload-digest-null | `igpv` row with `payload_sha256 null` → `PROVENANCE_NOT_BOUND` | P0 |
| reject/version-range-excludes | `igpv =2.0.0 OPTIONAL` → `PROVENANCE_VERSION_UNSUPPORTED` | P0 |
| reject/payload-digest-mismatch | binding digest of another payload → `PAYLOAD_DIGEST_MISMATCH` | P0 |
| reject/binding-fails-igx | binding with a wrong corpus digest → `IGXError CORPUS_DIGEST_MISMATCH` raised from P0 (IGPV/1 never reports on a binding IGX/1 rejects) | P0 |
| reject/oversized-payload | `limits.max_payload_bytes` lowered by the runner → `PROVENANCE_LIMIT_EXCEEDED` before parse | P1 |
| reject/oversized-target | `limits.max_graph_bytes` lowered → `PROVENANCE_LIMIT_EXCEEDED` before IGX/1 loads the target | P1 |
| reject/oversized-target-and-bad-binding | same, with a binding IGX/1 would reject → still `PROVENANCE_LIMIT_EXCEEDED` (preflight wins) | P1 |
| reject/oversized-sources | `limits.max_sources_bytes` lowered → `PROVENANCE_LIMIT_EXCEEDED` before any source is hashed | P1 |
| reject/noncanonical-payload-text | trailing newline → `MALFORMED_PROVENANCE` field `canonical_form` | P1 |
| reject/rows-not-sorted | attributions in insertion order `a1, a0` → `MALFORMED_PROVENANCE` field `canonical_form` | P1 |
| reject/duplicate-artifact-digest | two artifact rows with one `artifact_sha256` → `MALFORMED_PROVENANCE` | P1 |
| reject/node-id-outside-int64 | `node_id 9223372036854775808` → `MALFORMED_PROVENANCE` | P1 |
| reject/twin-ids-in-one-graph | objects `p 1` and `p "1"` with the same `graph` → `MALFORMED_PROVENANCE` | P1 |
| reject/duplicate-block, reject/unexpected-block, reject/semantic-digest-set | `MALFORMED_PROVENANCE` | P1 |
| reject/object-null-pattern | node row with `relation` set → `MALFORMED_PROVENANCE` | P1 |
| reject/float-node-id | `node_id 1.0` → `MALFORMED_PROVENANCE` | P1 |
| reject/ordinal-not-decimal | `ordinal "01"` → `MALFORMED_PROVENANCE` | P1 |
| reject/identifier-unrepresentable | `node_type "a:b"` → `MALFORMED_PROVENANCE` | P1 |
| reject/locator-past-size | `bytes/1` with `end > size` → `MALFORMED_PROVENANCE` | P1 |
| reject/locator-shape | `lines/1` with `locator_text` set → `MALFORMED_PROVENANCE` | P1 |
| reject/dangling-artifact-row | artifact referenced by nothing → `MALFORMED_PROVENANCE` | P1 |
| ok/origin-artifact-reached-via-objects-graph | origin-graph artifact referenced only through `objects.graph` of a derivation's origin → verify_ok | — |
| reject/extractor-with-policy | `MALFORMED_PROVENANCE` | P1 |
| reject/target-sha-mismatch | payload names another graph → `TARGET_BINDING_MISMATCH` | P2 |
| reject/target-profile-mismatch | `isonl-v1` payload over an `ison-v1` binding → `TARGET_BINDING_MISMATCH` | P2 |
| reject/unresolved-producer | attribution names an unknown producer → `UNRESOLVED_REFERENCE` | P3 |
| reject/origin-not-isongraph | `objects.graph` names a `document` artifact → `UNRESOLVED_REFERENCE` | P3 |
| reject/self-derivation | origin object in the target graph → `INVALID_DERIVATION` | P3 |
| reject/origin-graph-is-target | origin artifact digest equals the target's → `INVALID_DERIVATION` | P3 |
| reject/derivation-kind-mismatch | node derived from an edge → `INVALID_DERIVATION` | P3 |
| reject/identity-with-two-origins | `INVALID_DERIVATION` | P3 |
| reject/identity-address-differs | `INVALID_DERIVATION` | P3 |
| reject/unresolved-node | typed id not in the target (`"1"` where only `1` exists) → `UNRESOLVED_OBJECT` | P4 |
| reject/unresolved-edge-ordinal | simple graph edge with `ordinal "1"` → `UNRESOLVED_OBJECT` | P4 |
| reject/undirected-noncanonical-endpoints | `UNRESOLVED_OBJECT` detail `endpoints not canonical` | P4 |
| reject/origin-object-missing | origin graph supplied, object absent → `UNRESOLVED_OBJECT` | P4 |
| reject/origin-bytes-wrong | supplied origin-graph bytes hash differently → `SOURCE_ARTIFACT_MISMATCH` | P4 |
| reject/document-bytes-wrong | supplied document bytes hash differently → `SOURCE_ARTIFACT_MISMATCH` | P5 |
| reject/document-size-wrong | supplied bytes hash correctly but `size` differs → `SOURCE_ARTIFACT_MISMATCH` | P5 |
| reject/origin-size-wrong | supplied origin-graph bytes hash correctly but `size` differs → `SOURCE_ARTIFACT_MISMATCH` | P4 |
| reject/locator-lines-past-end | `lines/1` `end` ≤ `size` but > `line_count` of the supplied bytes → `LOCATOR_INVALID` (the only reachable `LOCATOR_INVALID`: a `bytes/1` range cannot pass P1 and P5's size checks yet exceed the bytes) | P5 |
| ok/locator-lines-counting | `lines/1 [2,2]` over `"a\n\n"` (2 lines) → `VERIFIED`; the same over `"a\n"` (1 line) is `reject/locator-lines-past-end` | — |
| reject/two-faults-first-wins | wrong target sha **and** unresolved node → `TARGET_BINDING_MISMATCH` | P2 |
| lineage/chain-two-hops | G″ ← G′ ← G, `origins:3` | — |
| lineage/cycle-detected | two payloads deriving the same object from each other → `DERIVATION_CYCLE` | L |
| lineage/graph-revisited-different-object | path passes through one graph twice via different objects → lineage_ok (not a cycle) | — |
| lineage/ambiguous-target | two payloads for one target → `LINEAGE_AMBIGUOUS` | L |
| lineage/depth-budget | chain longer than a lowered `max_lineage_depth` → `LINEAGE_BUDGET_EXCEEDED` | L |
| lineage/payload-unavailable-terminal | origin graph with no payload loaded → chain ends `terminal = payload_unavailable`, lineage_ok | — |
| lineage/no-derivation-record-terminal | origin graph's payload loaded but holds no derivation for the object → `terminal = no_derivation_record`, lineage_ok | — |

Determinism: every positive vector is run twice in one process and across the two CI lanes; results must be identical, and `Lineage.origins_of` must return steps in canonical record order regardless of payload insertion order.

## 7. Repository

```text
isongraph-ext/src/isongraph_ext/igpv/
  __init__.py      re-exports; DEFAULT_REGISTRY
  errors.py        IGPVError
  records.py       Artifact, Producer, NodeRef, EdgeAddress, GraphObject, Locator, Attribution, Derivation, Limits
  payload.py       ProvenancePayload (to_ison / from_ison / digest / check), shape rules (P1)
  locators.py      locator table, line counting, posture derivation (P5)
  verify.py        P0–P5, ProvenanceVerification
  bind.py          bind(), verify_and_admit()
  lineage.py       Lineage, LineageStep
  __main__.py      CLI
isongraph-ext/src/isongraph_ext/igx/registry.py   DEFAULT_REGISTRY lives here (igx must not import igpv)
vectors/igpv1/{manifest.ison, README.md, graphs/, bindings/, payloads/, sources/}
scripts/make_vectors_igpv.py
isongraph-ext/tests/test_igpv_*.py, tests/test_vectors_igpv.py
```

Exact pins unchanged. `igx` gains `DEFAULT_REGISTRY` and switches its production default to it; nothing else in `igx` changes (§9).

## 8. Out of scope (deferred, each a later spec)

Provenance **merge** and conflict resolution (combining attributions or derivations for one object from several payloads or producers; precedence, authority, confidence, contradiction); any truth, confidence or quality field; provenance over semantic (Semantic/2) identities — `IGPV/2` after the freeze; provenance expressed as an ISONGraph (approach B — may become a derived *query projection* later, never canonical storage); revision/delta/projection/DAG semantics themselves; cryptographic signatures or origin authentication; network, git or filesystem resolution of `uri`/`revision`; TS runtime; any change to Core.

## 9. Changes this spec makes to earlier documents

- `17` §3 / §0: the production capability registry is no longer empty — `DEFAULT_REGISTRY = {"igpv": "1.0.0"}` becomes the default `registry` of `igx.bind/verify/verify_and_admit` and of the `igx` CLI. `EMPTY_REGISTRY` stays exported for tests and for the `17` §5 vectors whose manifest says `empty` (their outcomes are unchanged because they name the registry explicitly). This is the entry `17` §0 anticipated; the binding wire format, V-steps, A-steps and codes are untouched. E2 adds E1 regression tests for the change: the full `vectors/igx1` suite still passes, a `REQUIRED igpv ^1` row verifies under the default registry and still fails under `EMPTY_REGISTRY`, and the `igx` CLI's `verify` over a binding with an `igpv` row exits 0.
- `04`: the Provenance section is superseded by this document; Revision and Delta remain the E3 sketch.
- `01`: E2 scope line → "IGPV/1 per `18`; merge rules deferred"; E5/E6 lines gain "emits IGPV/1 lineage (`18` §3)".
- `16` §4 row text "provenance binding" is satisfied by §4.2 here: no new admission rule, artifact identity only in E2.

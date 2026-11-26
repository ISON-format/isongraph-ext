# IGRV/1 and IGD/1 — Revision identity and delta: design draft (E3)

Status: DRAFT rev 0 - proposal, not frozen, BLOCKED on G-ID (13-SEMANTIC-2.md section 7)

Written from the consumer side by the downstream consumer ISONGraph Visualize (https://github.com/ISON-format/isongraphviz; its public frozen specifications are `docs/specs/IGS-1.md` and `docs/specs/IGL-1.md` in that repository), as a **proposal for the Ext maintainers to take over, change or discard**. Nothing here is implemented, nothing here is frozen, and no vector exists. It changes nothing in IGX/1, IGPV/1, IGDM/1, IGP/1, IGAR/1, IGDC/1, Semantic/2 or Core.

**How to read this document.** Every statement that sounds normative (a MUST, a rule, a code, a format, a default, a limit) is a proposal and is labelled **PROPOSED**. A sentence without that label is a description of existing, public material (cited by document and section) or an explanation. Open decisions are collected in section 14. Where this draft says "Ext" it means the maintainers of `ISON-format/isongraph-ext`; where it says "consumer" it means any program that reads revisions and deltas, a visual timeline being the motivating case.

## 0. Why this exists

E3 (revision identity and delta) is the one remaining protocol the consumer needs and that has no design in the Ext repository. A visual timeline over a changing graph needs to know, precisely and verifiably:

1. which exact graph state each point on the timeline is (revision identity);
2. what changed between two states (delta), stated against addresses that cannot be confused (`igs-addr/1`, `26-IGDC1-DESIGN.md` section 1);
3. that applying the delta to the base really gives the claimed result (pure, verifiable apply), and why a delta is refused when it does not.

This draft states those needs as a design the Ext maintainers could freeze after the identity gate (G-ID) closes. It is deliberately shaped like `18-IGPV1-DESIGN.md` and `19-IGDM1-DESIGN.md` (companion files, canonical bytes, first-failure-wins verification steps, budgets, vector plan) so that it can be taken over with little rewriting.

### 0.1 Scope

**PROPOSED.** IGRV/1 and IGD/1 cover:

- revision identity of one graph state, and the base/parent relation between two states;
- delta operations for node, edge and property changes on the graph, and for changes to bound companion payloads (groups and other extensions), each addressed by a typed address;
- a canonical byte form and a canonical operation order;
- apply and rejection rules with named reason codes, and result identity;
- resource limits, companion-file and IGX/1 capability binding, a vector plan.

### 0.2 Non-goals

**PROPOSED.** Not in IGRV/1 or IGD/1: receipts for revisions or deltas (a later E7, section 9); merge or conflict resolution between revisions with several parents; any version-control semantics (branches, tags, history storage); signatures or authentication; renderer, layout or animation code; any change to the Core grammar; a TypeScript runtime.

## 1. Relation to Semantic/2

`13-SEMANTIC-2.md` section 0 states two digests that are never one: a **semantic digest** of graph meaning and an **artifact digest** of exact written bytes. Revision identity needs the first.

**PROPOSED.** A revision is a graph *state*, and its identity is the Semantic/2 semantic digest of that state (`13` section 3: algorithm `ISONGraph-Semantic/2`, value SHA-256 over the normal form). Revision identity is **never** derived from ISONCS or any other serialization bytes, from the writer, or from the file name. Two artifacts with different bytes and the same semantic digest are the same revision; two artifacts with the same bytes read by two ports that disagree about identity (section 14, question 4) are not guaranteed to be.

Facts about the present state that this proposal depends on, all from public documents:

| fact | where | consequence |
|---|---|---|
| Semantic/2 is `DRAFT FOR G-ID FREEZE`; E3 cannot open until all nine G-ID conditions pass | `13` section 7 | this draft cannot be frozen before the gate closes |
| condition 7 (golden corpus on Python and TypeScript) is stated as not started | `13` section 7 | no expected digest value can be written for any vector yet |
| the digest tag byte constants and the `u32` length choice are "illustrative, to be frozen" | `13` sections 3 and 7 | result identity cannot be implemented byte-exactly yet |
| `semantic_digest` and `semantic_digest_algorithm` in an IGX/1 binding are `null` until Semantic/2 freezes; a non-null value is `MALFORMED_BINDING` | `17` section 2 | the digest must live in the IGRV/1 payload, not in the binding, unless IGX/1 gets a new version |
| Rust, C# and C++ hold string-only ids; the id-typing decision is open | `13` section 7 | see open question 4 |
| a receipt posture of `CORE_LOSSY` means identity-sensitive operations (revision, delta, ...) refuse under policy or mark the result as port-bound | `13` section 6.1 | see section 3.3 |
| no Semantic/2 digest implementation exists in the repository | repository tree | E3 includes writing it, or depends on someone else writing it |

## 2. Addressing

**PROPOSED.** Every operation names its target with the typed addresses the rest of the ecosystem already uses, never with reference text (`:p:1`) and never with untyped ids:

```text
NodeRef/2     = ( node_type: STRING, node_id: INT64 | STRING )             (13 section 1.5; 18 section 1.2)
EdgeAddress/2 = ( source_ref, relation: STRING, target_ref, ordinal: STRING )   (13 section 2.2; 18 section 1.2)
tagged id     = "i:" + canonical decimal INT64   |   "s:" + string verbatim   (26 section 1.1, igs-addr/1)
```

On the wire an id is one STRING cell in the tagged form, so `i:7` and `s:7` are different addresses and a JavaScript-style integer above 2^53 cannot be mangled by a reader. The mapping to and from the cell-typed IGPV/1 and IGDM/1 form is `26` section 1; the semantic order of addresses is `26` section 1.3 (UTF-8 byte order, every INT64 before every STRING). For an undirected target an edge is addressed by its logical address, endpoints in canonical order (`13` section 2.3); a row that is not canonical is refused, never silently normalised (as `18` section 1.2 does).

The ID-TWIN-INVARIANT (`13` section 1.5) applies to the base, to the delta (it may not address both twins of a pair) and to the result.

## 3. Revision identity (IGRV/1)

### 3.1 The revision document

**PROPOSED.** One companion `<graph>.igrv.ison`, bytes exactly the canonical writer output (`17` section 2.1 and `19` section 1: blocks by `kind.name`, fields by name, rows by every column with nulls last; any other byte sequence is `MALFORMED_REVISION`, field `canonical_form`). Exactly these blocks, each once: `meta.igrv`, `meta.graph`, `table.parents`. Illustrative, not byte-canonical (see `ERRATA.md` E-3 for why examples in this repository are marked so):

```text
meta.igrv
revision_spec semantic_algorithm semantic_digest target_artifact_sha256 target_serialization_profile
IGRV/1 ISONGraph-Semantic/2 <64hex> <64hex> ison-v1

meta.graph
directed multigraph receipt_posture writer_implementation writer_version
true false OK isongraph-python 1.4.1

table.parents
parent_semantic_digest
<64hex>
```

| field | PROPOSED meaning |
|---|---|
| `revision_spec` | `IGRV/1` |
| `semantic_algorithm`, `semantic_digest` | the Semantic/2 digest of the state; the **revision identity** |
| `target_artifact_sha256`, `target_serialization_profile` | the exact artifact this document is bound to; informational for identity, mandatory for binding (section 11) |
| `directed`, `multigraph` | mandatory header of the state, never inferred (`13` section 2.1) |
| `receipt_posture`, `writer_*` | the `13` section 4 fields that make the digest interpretable (writer identity required there) |
| `table.parents` | zero rows (a root revision) or exactly one row (section 3.2) |

### 3.2 Parent and base rules

**PROPOSED.**

1. A revision has **zero or one** parent. Revisions with several parents (merges) are out of scope; `18` section 8 defers merge rules the same way.
2. The parent is named by its semantic digest only. IGRV/1 does not carry or fetch the parent's bytes.
3. A **delta** has a `base` and a `result`, each a semantic digest. The IGRV/1 `parents` row of the result revision is the delta's base, and a consumer MAY check this equality; an IGRV/1 document alone cannot prove the parent relation, only a verified delta can (section 6).
4. Revision identity is **state identity**, not history identity: reaching the same state by two paths, or returning to an earlier state (A, B, A), gives the same identity. Whether this is what a timeline needs is open question 5.

### 3.3 Posture

**PROPOSED.** Following `13` section 6.1: IGRV/1 records `receipt_posture`. A revision produced under `CORE_LOSSY` or `CORE_BLOCKING_DIVERGENCE` is either refused by policy or carried as port-bound; it MUST NOT be presented as a cross-port identity. Which of the two is the Ext maintainers' decision (open question 4).

## 4. Delta document (IGD/1)

### 4.1 Wire format

**PROPOSED.** One companion `<name>.igd.ison`, canonical writer bytes, blocks `meta.igd`, `table.ops`, `table.companions`, each once; tables may be empty.

```text
meta.igd
delta_spec base_semantic_digest result_semantic_digest result_target_artifact_sha256 semantic_algorithm
IGD/1 <64hex> <64hex> <64hex> ISONGraph-Semantic/2

table.ops
op target value_type value name
...
```

`delta_sha256 = sha256(delta bytes)` is external (it appears in no field), as `25` section 2 does for receipts, so that nothing is excluded from hashing.

### 4.2 Operations

**PROPOSED.** The operation vocabulary is closed. Every row of `table.ops` has the columns `op`, `target`, `name`, `value_type`, `value`; unused columns are null.

| op | target | other columns | meaning |
|---|---|---|---|
| `node.add` | node address `<node_type>\|<tagged id>` | none | the node exists in the result, with no properties; absent from the base |
| `node.remove` | node address | none | the node is absent from the result; present in the base |
| `edge.add` | edge address (4-tuple, tagged ids) | none | the edge exists in the result, with no properties; absent from the base |
| `edge.remove` | edge address | none | the edge is absent from the result; present in the base |
| `prop.add` | node or edge address | `name`, `value_type`, `value` | the property is absent from the target in the base and present in the result |
| `prop.replace` | node or edge address | `name`, `value_type`, `value` | the property is present in the base and has a different value in the result |
| `prop.remove` | node or edge address | `name` | the property is present in the base and absent from the result |

Separating `add` from `replace` makes every property operation state its precondition, so a wrong assumption is a stable rejection and not a silent overwrite. Whether `replace` and `remove` also carry the old value is open question 1.

**PROPOSED.** Values are Semantic/2 normal-form values (`13` section 1): `value_type` is one of `int64`, `float64`, `string`, `bool`; `value` is always a STRING cell holding the exact text (decimal for `int64`, `true`/`false` for `bool`, the string verbatim, and for `float64` the 16 lowercase hexadecimal digits of the IEEE-754 binary64 bits, so that no `repr()` or `toString()` spelling participates, `13` section 1.2). An integral float is not `float64` (it is `int64`); `null` is not a value (an absent property is expressed with `prop.remove`); a non-finite float, an integer outside INT64 and a lone surrogate are `VALUE_OUT_OF_DOMAIN`. Whether property values are typed this way or as native ISON cells is open question 3.

**PROPOSED.** Node and edge operations never carry properties. A node added with three properties is one `node.add` and three `prop.add` rows. The delta therefore has exactly one way to say each thing.

**PROPOSED, rename.** A rename (a changed id, type or relation) is `remove` plus `add` of the new address and carries no relation between the two. IGD/1 defines no rename operation.

### 4.3 Groups and other companion payloads

Groups exist only in IGDM/1 payloads (`19` section 0), and no companion payload is part of the Semantic/2 digest of the graph (`13` section 3 lists nodes, edges and properties only). A revision of "the graph and its groups" therefore has two identities, which this draft keeps apart.

**PROPOSED, option A (baseline).** `table.companions` records whole-payload replacement:

```text
table.companions
base_payload_sha256 capability result_payload_sha256
<64hex|null> igdm <64hex|null>
```

`capability` is an IGX/1 extension name; `base_payload_sha256` null means the capability is added by the delta, `result_payload_sha256` null means it is removed. The delta states that the bound payload for that capability changed from one exact byte string to another; it does not say how. The result payload is supplied by the caller and verified by its own capability verification (for IGDM/1, D0 to D4 of `19` section 3.1) against the result graph. IGD/1 adds no group semantics.

**Option B (not proposed here, listed in open question 2):** first-class group operations (`group.add`, `group.remove`, `group.set`, `member.add`, `member.remove`) mirroring `table.groups` and `table.members` of `19` section 1.1, with result identity over the resulting canonical IGDM/1 bytes. This would give a timeline fine-grained group changes at the price of IGD/1 depending on the IGDM/1 canonical writer and its rules (collapse exclusivity, hierarchy chains, acyclic parents).

## 5. Canonical order and application semantics

**PROPOSED, wire order.** The rows of `table.ops` are in the order the canonical writer gives (every column as text, nulls last, as in `25` section 2 and `26` section 2). A delta whose bytes are not the canonical re-emission is `MALFORMED_DELTA`, field `canonical_form`. The wire order is an artifact of the writer and has no meaning for application.

**PROPOSED, application.** The operations of a delta are a **set** applied **simultaneously** to the base state, not a sequence. Validity (section 6, G3) is defined against the base and the result, so no operation can depend on the order of another. Consequences, all PROPOSED:

- an address that appears as the target of two operations of conflicting kinds (add and remove of the same address, two operations on the same property, a property operation on a removed object) is `OPERATION_CONFLICT`;
- `node.remove` requires every edge incident to the node in the base to be removed by the same delta; there is no cascade (open question 9);
- `edge.add` requires both endpoints to exist in the result (present in the base and not removed, or added by the same delta);
- a property operation on an object added by the same delta is allowed (`prop.add`); a property operation on an object that is in neither base nor result is `UNRESOLVED_OBJECT`.

**PROPOSED, presentation order.** A consumer that animates a delta needs one order two implementations agree on. The presentation order is defined, derived and never stored: by operation kind in the order `edge.remove`, `prop.remove`, `node.remove`, `node.add`, `edge.add`, `prop.add`, `prop.replace`; then by the semantic order of the target address (`26` section 1.3, UTF-8 byte order, INT64 before STRING, edges by source, relation bytes, target, ordinal bytes); then by `name` UTF-8 bytes. It does not affect validity or result identity.

## 6. Verification, apply and rejection

### 6.1 Operations

**PROPOSED.**

```text
apply(base_state, delta)        -> result_state     pure; raises IGDError
verify_delta(base_artifact, delta_bytes, [binding], [result_artifact]) -> DeltaVerification
```

`apply` works on states (the Semantic/2 normal form of a loaded graph) and returns a state plus its semantic digest. It does **not** write bytes: the bytes of a materialised result depend on the writer, and the artifact digest of a materialised result is not part of revision identity (`13` section 4). A caller that materialises the result and wants it bound uses `igx.bind` as usual.

### 6.2 Verification order (deterministic; first failure wins; `IGDError.step` names it)

**PROPOSED.**

| step | checks | code on failure |
|---|---|---|
| **G0 budget** | delta bytes at most `max_delta_bytes`, base bytes at most `max_graph_bytes`, on lengths, before any parser or Core loader runs | `DELTA_LIMIT_EXCEEDED` |
| **G1 shape** | canonical bytes; blocks exactly once; fields; `delta_spec`; closed vocabulary; address and tagged-id grammar; `value_type` and value text grammar; unique rows; ops at most `max_ops`; ID-TWIN-INVARIANT inside the delta; `semantic_algorithm` known | `MALFORMED_DELTA`, `UNSUPPORTED_SEMANTIC_VERSION` |
| **G2 base** | load the base with the pinned Core, compute its semantic digest, compare with `base_semantic_digest` | `BASE_REVISION_MISMATCH` |
| **G3 operations** | against the base: every add target absent, every remove or replace target present, no conflicting operations, edge endpoints present in the result, removed nodes have no remaining edges | `COLLISION`, `INVALID_REMOVAL`, `UNRESOLVED_OBJECT`, `OPERATION_CONFLICT` |
| **G4 result state** | the result is a legal Semantic/2 state: values in domain, no id twin, no undirected mirror conflict, valid edge addresses, `directed` and `multigraph` unchanged | `INVALID_RESULT_STATE` |
| **G5 result identity** | the semantic digest of the result equals `result_semantic_digest` | `RESULT_REVISION_MISMATCH` |
| **G6 companions** | each `table.companions` row: when payload bytes are supplied, their digest equals the stated one and they pass their own capability verification against the result; when not supplied, the row is reported unchecked | `COMPANION_MISMATCH` |

Reasons (the `reason` field, a diagnostic; the code is the contract, as `13` section 5 says): `COLLISION` is `ADD_EXISTS` or `TWIN_EXISTS`; `INVALID_REMOVAL` is `ABSENT` or `NODE_HAS_EDGES`; `UNRESOLVED_OBJECT` is `NODE_ABSENT`, `EDGE_ABSENT`, `ENDPOINT_ABSENT` or `PROPERTY_ABSENT`; `INVALID_RESULT_STATE` carries a `13` section 5 reason (`VALUE_OUT_OF_DOMAIN`, `UNDIRECTED_EDGE_CONFLICT`, `INVALID_EDGE_ADDRESS`, ...). A property operation whose precondition fails is `COLLISION / ADD_EXISTS` (`prop.add` on a present property), or `INVALID_REMOVAL / ABSENT` or `UNRESOLVED_OBJECT / PROPERTY_ABSENT` (`prop.replace` or `prop.remove` on an absent one); the draft leaves the exact split to the first implementation and its vectors (open question 11).

The four rejection families the consumer needs, by name: **wrong base** (`BASE_REVISION_MISMATCH`), **collision** (`COLLISION`), **invalid removal** (`INVALID_REMOVAL`), **invalid result state** (`INVALID_RESULT_STATE`). `RESULT_REVISION_MISMATCH` is a separate fifth: the delta applies cleanly and produces a different state from the one it claims.

### 6.3 Empty and no-op deltas

**PROPOSED.** A delta with no operations and no companion rows is valid iff `base_semantic_digest == result_semantic_digest`. A delta whose operations change nothing in the state is not recognised as such (it is judged by G2 to G5 like any other); a producer should not emit it. Open question 10.

## 7. Result identity

**PROPOSED.** The result identity of a delta is `result_semantic_digest`, declared in `meta.igd` and recomputed at G5. A verified delta therefore proves the statement "applying these operations to a state whose semantic digest is the base gives a state whose semantic digest is the result", and nothing else: not that the operations are what the author intended (two different deltas can have the same base and result), not who produced them, and not that the base was a good state. A delta is identified as an artifact by `delta_sha256`.

## 8. Invertible deltas or checkpoints

This is the decision a visual timeline depends on most, and it is **not decided here** (open question 1). Both options are compatible with everything above.

| option | change to the format | effect on a timeline |
|---|---|---|
| **Invertible deltas** | `prop.replace` and `prop.remove` carry the old value; `node.remove` and `edge.remove` require explicit `prop.remove` rows for every property of the object (so the inverse can restore them); `inverse(delta)` is a pure function whose result is itself a verifiable delta with base and result swapped | stepping backwards applies the inverse, cost proportional to the steps; deltas are larger; the inverse adds its own rejection cases; a timeline needs only the deltas |
| **Forward-only deltas with checkpoints** | none to the delta; a checkpoint is a full revision (graph artifact and IGRV/1 document) every N steps; the checkpoint spacing is policy outside IGD/1 | seeking backwards loads the nearest earlier checkpoint and replays forward: bounded work, latency depends on spacing; storage grows by whole graphs; a timeline needs checkpoints plus deltas, and a verified path from checkpoint to target |

A mixed form (invertible deltas, plus checkpoints for long jumps) is possible and costs both. A replay budget (`max_replay_steps`, section 10) applies in any case.

## 9. Receipts and E7

**PROPOSED.** IGRV/1 and IGD/1 define verification outcomes (`DeltaVerification`, as `19` defines `DatamaticsVerification`) and no receipt. Revision and delta **receipts** belong to E7 and are not designed here. What E7 would need from this draft, and what this draft therefore keeps stable and external: `delta_sha256`, `base_semantic_digest`, `result_semantic_digest`, the document specification versions, and the verifier identity. IGAR/1 (`25`) is an admission receipt over IGX/1 and IGDM/1 inputs; it does not cover revisions or deltas, and this draft does not extend it.

## 10. Resource limits and budgets

**PROPOSED**, in the style of `18` section 4.3 and `19` section 3.3. Defaults are placeholders to be set from measurement; none has been measured.

```python
@dataclass(frozen=True)
class Limits:
    max_delta_bytes: int = 64 * 1024 * 1024        # G0, before parsing the delta
    max_graph_bytes: int = 256 * 1024 * 1024       # G0, before loading the base (and the result when supplied)
    max_ops: int = 1_048_576                        # G1; rows of table.ops
    max_companion_rows: int = 64                    # G1; rows of table.companions
    max_value_bytes: int = 1024 * 1024              # G1; one property value
    max_replay_steps: int = 4096                    # a consumer replaying a chain of deltas
DEFAULT_LIMITS = Limits()
```

Byte budgets are checked on lengths before any parser or Core loader runs, including the loader used for the base. The budgets bound bytes, not memory or time: apply costs about one Core load of the base plus a Semantic/2 digest of base and result, and `docs/resource-limits.md` states that a byte limit does not prevent an out-of-memory condition; process-level memory and time limits remain the caller's job. The digest cost for IGRV/1 and IGD/1 is not measured.

## 11. Companion files and IGX/1 capability binding

**PROPOSED.** `igrv` and `igd` are the capability names `17` section 0 already lists as future registry entries. Each is bound through IGX/1 as in `19` and `25`:

- `<graph>.igrv.ison` is an `igrv 1.0.0` capability of the graph's IGX/1 binding; `payload_sha256 = sha256(IGRV/1 bytes)`; its `target_artifact_sha256` must equal the binding's `artifact_sha256`.
- `<name>.igd.ison` is bound to the **result** graph as an `igd 1.0.0` capability of the result's IGX/1 binding, with `result_target_artifact_sha256` equal to the binding's `artifact_sha256`. The base graph is not part of the binding; the caller supplies it and G2 identifies it by semantic digest. Binding to the result, to the base or to neither is open question 8.
- Verification runs `igx.verify` first (a D0-style step), as every other capability does. An `OPTIONAL` row on a runtime without the capability is preserved and never interpreted; a `REQUIRED` row there is `UNSUPPORTED_CAPABILITY` (`17` section 4, V5).
- `igx.DEFAULT_REGISTRY` gains `igrv 1.0.0` and `igd 1.0.0` when the specification is admitted, by the same mechanism as `18` section 9 and `19` section 8. No IGX/1 wire change is needed: the semantic digest lives in the IGRV/1 payload while `semantic_digest*` in the binding stays null.

## 12. Vectors plan

**PROPOSED.** `vectors/igrv1/` and `vectors/igd1/`, each with `manifest.ison`, `README.md` and `SHA256SUMS` (as `vectors/igar1/` and `vectors/igdc1/` have), written by a generator in `scripts/` that does not import the implementation. No expected digest can be written until Semantic/2 freezes (section 1); the table lists the rows and their expected outcome. Counts are not pinned.

| group | rows (id) | expect | step |
|---|---|---|---|
| golden | `ok/add-node`, `ok/remove-isolated-node`, `ok/add-edge-simple`, `ok/add-edge-multigraph-ordinal`, `ok/undirected-edge-canonical`, `ok/prop-add-int64`, `ok/prop-add-string-digit-like`, `ok/prop-add-float64-bits`, `ok/prop-replace`, `ok/prop-remove`, `ok/signed-ids`, `ok/int64-extremes`, `ok/typed-ids-distinct`, `ok/node-with-edges-removed-together`, `ok/empty-delta-equal-states`, `ok/companion-replace` | verified, with stated result digest | G0 to G6 |
| order | `ok/wire-order-is-writer-order`, `ok/presentation-order-fixed`, `ok/order-utf8-not-utf16` | verified | G1 |
| round trip | `ok/apply-then-digest-matches`, `ok/inverse-restores-base` (only if invertible deltas are chosen) | verified | G5 |
| wrong base | `reject/base-digest-mismatch`, `reject/base-is-result` | `BASE_REVISION_MISMATCH` | G2 |
| collision | `reject/add-existing-node`, `reject/add-existing-edge`, `reject/add-twin-id`, `reject/prop-add-existing` | `COLLISION` | G3 |
| invalid removal | `reject/remove-absent-node`, `reject/remove-absent-edge`, `reject/remove-node-with-edges`, `reject/prop-remove-absent` | `INVALID_REMOVAL` / `UNRESOLVED_OBJECT` | G3 |
| conflict | `reject/add-and-remove-same-address`, `reject/two-ops-same-property`, `reject/prop-on-removed-node` | `OPERATION_CONFLICT` | G3 |
| result state | `reject/value-out-of-int64`, `reject/value-nonfinite-float`, `reject/value-lone-surrogate`, `reject/undirected-mirror-conflict`, `reject/header-changes-directed` | `INVALID_RESULT_STATE` | G4 |
| result identity | `reject/result-digest-mismatch` | `RESULT_REVISION_MISMATCH` | G5 |
| shape | `reject/noncanonical-text`, `reject/unknown-op`, `reject/untagged-id`, `reject/bare-reference-text`, `reject/ordinal-noncanonical`, `reject/duplicate-row`, `reject/twin-ids-in-delta`, `reject/value-type-unknown`, `reject/float64-not-16-hex`, `reject/integral-float-as-float64` | `MALFORMED_DELTA` | G1 |
| limits | `reject/oversized-delta`, `reject/oversized-base`, `reject/too-many-ops` | `DELTA_LIMIT_EXCEEDED` | G0, G1 |
| binding | `reject/not-bound`, `reject/payload-digest-mismatch`, `reject/result-target-mismatch` | codes as `19` D0 and D2 | D0 |
| consumer | JavaScript-parser hazards of `25` section 8 and `26` section 7 (integers above 2^53 in ids and `int64` values, digit-like strings, BOM, CR, repeated columns) | rejected or preserved exactly | G1 |

Two-fault rows (`reject/two-faults-first-wins`) fix the order of the steps. A Route B consumer (`25` section 8) qualifies its reader against these rows.

## 13. Security considerations

**PROPOSED** requirements first, then what is not defended.

1. **Hostile deltas.** A delta is untrusted bytes. Nothing is executed or interpolated. Every field is checked against a closed grammar at G1 before use; a delta whose result digest is lying is caught at G5; one that applies against the wrong state is caught at G2. A verified delta says it is internally consistent with its base and result, not that it is good or authorised (section 7).
2. **Huge deltas.** Byte budgets are checked on lengths before parsing; row budgets after parsing; the operation count bounds apply work, and apply is linear in operations plus one load and two digests of graph-sized state. Budgets do not bound memory; apply under process-level limits, in a process that can be killed (`docs/resource-limits.md`).
3. **Amplification.** A delta of at most `max_delta_bytes` can add at most `max_ops` objects and properties; the result is bounded by base plus ops. A chain of deltas is not bounded by the delta budget: the consumer's replay budget (`max_replay_steps`) and per-step verification apply.
4. **Address spoofing.** Typed tags make `i:7` and `s:7` different addresses; a string that already begins with a tag is wrapped (`s:i:7`), never reinterpreted (`26` section 1.1). The twin rule is enforced inside the delta and on the result, so a delta cannot create `i:1` next to `s:1`. Reference text is never an address. Ordinals and endpoint order must be canonical or the row is refused. **Not defended:** visually confusable ids (look-alike Unicode, NFC versus NFD stay different ids, `13` section 1.4); a consumer that displays ids must show the tag and may want to flag non-ASCII.
5. **Replay and forking.** Identity is state identity (section 3.2): the same delta can be replayed on any state with the base digest, and a producer can publish two different deltas between the same two states. A consumer building a timeline from a set of deltas must treat the set as untrusted and handle forks, cycles (A, B, A) and gaps itself; IGD/1 does not define a log.
6. **Authenticity.** Unsigned, like bindings and receipts (`17` section 1.1, `25` section 0). A digest match proves bytes, not who wrote them. Trust comes from the consumer's controlled channel, not from the document.
7. **Companion payloads.** A replaced companion payload (option A) is hostile input to its own capability verifier; IGD/1 only compares digests and calls that verifier, it does not relax it.
8. **Posture.** A revision produced on a lossy or divergent Core port is port-bound or refused (section 3.3), so a delta cannot launder a port-specific identity into a cross-port one.
9. **Error text.** Failure details carry addresses and digests, not file contents, and are prose outside the contract, as in `25` section 2.

## 14. Open questions

For the Ext maintainers. Each is a decision this draft does not make.

1. **Invertible deltas or checkpoints** (section 8). Which one, or both. Consequences for the format (old values, explicit property removal before node removal, an `inverse` function) and for a timeline are in the table in section 8.
2. **Are groups first-class operations** (section 4.3)? Option A replaces whole companion payloads and keeps IGD/1 independent of IGDM/1; option B gives fine-grained group changes and couples the two. A third possibility is to leave groups out of IGD/1 entirely and let each capability define its own change record.
3. **Do property operations carry typed values** as `value_type` plus a string cell (proposed here, JavaScript-safe, verbose) or as native ISON cells (compact, INT64 versus STRING decided by quoting, exposed to the integer and digit-like-string hazards listed in `25` section 8)? Also the spelling of `float64` (the bits in hexadecimal are proposed).
4. **Effect of the open Rust, C# and C++ id-typing decision** (`13` section 7). If those ports keep string-only ids, then `i:1` and `s:1` cannot both be represented there, the same file digests differently by reading port, and IGRV/1 revision identity would be port-bound for them. Options: require `INT64 | STRING` ids in every port that produces revisions; declare the ports unable to produce or apply deltas; or carry `receipt_posture` and refuse or mark port-bound (as `13` section 6.1 allows). Until decided, the draft assumes only a port with `INT64 | STRING` ids is a producer.
5. **State identity or history identity** (section 3.2). A timeline over A, B, A needs positions; a state digest alone gives two points the same identity. Whether a log or chain document is IGRV/1's business or a consumer's is open.
6. **Multi-parent revisions** (merge) are deferred. When, and with what conflict rules (`18` section 8 defers provenance merge for the same reason).
7. **Simultaneous set or ordered sequence** (section 5). A sequence with explicit positions is easier to read as history but adds an ordering a verifier must check and a way for two byte-different deltas to mean the same change.
8. **What the delta is bound to** (section 11): the result (proposed), the base, both, or nothing but semantic digests.
9. **Does `node.remove` cascade** to incident edges? The draft says no, so that every removal is stated; a cascade would shorten deltas and hide edge removals from a timeline.
10. **Empty deltas and no-op operations** (section 6.3): tolerate, or reject with a code.
11. **Exact split of reasons** for property precondition failures between `COLLISION`, `INVALID_REMOVAL` and `UNRESOLVED_OBJECT` (section 6.2).
12. **Multigraph ordinals.** In a multigraph, who allocates the ordinal of an added edge and what happens when it is not the smallest free one? An ordinal is an opaque string compared as bytes (`13` section 2.2); the draft takes whatever the delta states.
13. **Undirected edges.** Mirrored rows in Core and logical edges in Semantic/2 (`13` section 2.3): the draft addresses the logical edge only. Confirm.
14. **Who writes the Semantic/2 digest implementation** and the golden corpus that gates every vector here (`13` section 8).
15. **Temporal hints.** `19` section 1.1 defines `temporal_state` and `temporal_order` as presentation hints that are "not a revision reference". A consumer can derive `introduced`, `changed` and `removed` for objects from a verified delta (`node.add` and `edge.add`, property operations, removals). Whether Ext should offer that derivation, or leave it to consumers, is open; this draft does not propose it.

## 15. Repository (proposed layout)

```text
isongraph-ext/src/isongraph_ext/igrv/{__init__, errors, records, payload, verify, bind, __main__}.py
isongraph-ext/src/isongraph_ext/igd/{__init__, errors, records, payload, apply, verify, bind, __main__}.py
isongraph-ext/src/isongraph_ext/semantic/{__init__, normal_form, digest}.py        Semantic/2 digest, after G-ID
isongraph-ext/src/isongraph_ext/igx/registry.py                                    DEFAULT_REGISTRY gains igrv, igd
vectors/igrv1/, vectors/igd1/, scripts/make_vectors_igrv.py, scripts/make_vectors_igd.py
```

## 16. Out of scope

Revision logs and storage, merge and conflict resolution, signatures, receipts (E7), projection and DAG interaction with deltas, layout or animation, themes, any change to Core, a TypeScript runtime, and any change to a frozen specification. A frozen text is never edited; if this draft is adopted and a published table of an earlier specification must be corrected, that goes in `ERRATA.md`.

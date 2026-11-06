# IGDM/1 — Datamatics: design for E4

Status: **FROZEN 2026-11-06 (E4, rev 1)** · Implements planmap `01` E4 and `05-IGDM1-DATAMATICS.md` in `ISON-format/isongraph-ext`, binding through `17-IGX1-DESIGN.md` (FROZEN rev 3) as the capability `igdm`, addressing graph objects exactly as `18-IGPV1-DESIGN.md` (FROZEN rev 1) does. Nothing here is renderer code, layout computation, scene state, or a product vocabulary (`02` law 8, `11` ADR-E6). Changing §1–§5 after implementation ships is a new spec version (`IGDM/2`), never an edit.

## 0. What E4 delivers

A companion artifact `<graph>.igdm.ison` that states, for one exact ISONGraph artifact (the **target graph**), declarative and renderer-neutral **intent**:

1. **Node hints** — magnitude, semantic role, shape role, emphasis, badge, ring, label, visibility and level-of-detail, interaction capabilities, temporal state, accessibility text and role.
2. **Edge hints** — semantic role, pattern role, emphasis, direction-display intent, label, visibility and level-of-detail, interaction capabilities, temporal state, accessibility text.
3. **Groups** — hull / hierarchy / collapse / aggregate intent over explicit node memberships, nested through an acyclic parent tree (Core has no group concept; groups exist only here).
4. **Layout hints** — a layout family, flow direction, stability intent at graph scope; rank and anchor intent per node.
5. **Theme separation** — the payload carries **roles**, never colours, fonts, pixel sizes or coordinates; a theme is a downstream mapping from role to appearance and is out of scope.
6. **Deterministic verification** — canonical bytes, closed vocabularies with a preserved-and-reported `x-` extension namespace, reference and acyclicity rules, object resolution against the pinned Core, budgets, stable failure codes, IGX/1 binding compatibility; conformance vectors.

The E4 acceptance law:

> Every IGDM/1 hint names an exact graph object (or group of them) in an exact target artifact, says *what it means* and never *how it looks*, and can be verified structurally without a renderer; a consumer that ignores every hint still has the whole graph, and a consumer that knows no `x-` role still renders the graph with the closed roles it does know.

### 0.1 What a verified payload does not prove

That the hints are good, true, or consistent with the graph's meaning. A node marked `negative` is a producer's intent, not a fact about the node. Datamatics is presentation intent over Core semantics (`02` law 9: Ext never reinterprets the document); verification proves the intent is well-formed and points at real objects, nothing more.

## 1. Wire format and addressing

One companion document `<graph>.igdm.ison`; its bytes are **exactly** ison-py's canonical writer output (`17` §2.1 and `18` §1 as clarified: the writer orders blocks by `kind.name`, fields by name, rows by every column with nulls last). Any other byte sequence is `MALFORMED_DATAMATICS`, field `canonical_form`. Exactly these blocks, each **exactly once**: `meta.igdm`, `meta.layout`, `table.nodes`, `table.edges`, `table.groups`, `table.members`. Tables may be empty.

```text
meta.igdm
datamatics_spec target_artifact_sha256 target_serialization_profile
IGDM/1 <64hex> ison-v1

meta.layout
direction family stability
LR layered stable

table.nodes
a11y_role a11y_text badge drilldown emphasis expandable focusable label layout_anchor layout_rank lod_min magnitude node_id node_type ring role selectable shape_role temporal_order temporal_state visibility
warning null "3" null medium null null null null null 2 0.1 s1 order warning inactive null circle null null collapsed
null "Order 1 (active)" null null high "true" null "Order #1" "true" 0 0 0.8 1 order null active "true" document 3 changed visible

table.edges
a11y_text direction_display emphasis focusable label lod_min ordinal pattern_role relation role selectable source_id source_type target_id target_type temporal_order temporal_state visibility
null forward low null null 1 "0" dashed knows neutral null 1 order s1 order null null visible

table.groups
a11y_text collapsed group_id intent label lod_min parent_group_id role visibility
null "false" region hull "Region A" 0 null neutral visible
null "true" cluster collapse "Cluster" 1 region emphasis-low visible

table.members
group_id node_id node_type
cluster 1 order
region 1 order
region s1 order
```

(Quoting is the writer's: `"true"`/`"false"` are **string** tokens so they never parse as booleans, `"0"` ordinal and `"3"` badge are quoted because they look numeric.)

### 1.1 Blocks and fields

**`meta.igdm`** — one row. `datamatics_spec = IGDM/1`; `target_artifact_sha256` 64 lowercase hex (framing `17` §2.1: the exact target bytes); `target_serialization_profile ∈ { ison-v1, isonl-v1 }`, must equal the binding's. No IGX binding digest (circularity, as `18` §1.1).

**`meta.layout`** — one row, graph scope. `family ∈ { force, layered, radial, grid, geographic, manual } ∪ X`; `direction ∈ { TB, BT, LR, RL } | null` (non-null only meaningful with `layered`; other families **may** carry it — it is a hint, not a constraint — but `null` is required when `family` is null); `stability ∈ { stable, free } | null`. All three may be null (no layout intent).

**`table.nodes`** — at most one row per node address (`node_type`, `node_id` as `18` §1.2: typed INT64/STRING ids, Core identifiers, ID-TWIN-INVARIANT applies across the whole payload including members and edge endpoints). Hint columns, all nullable (`null` = no intent, never a default):

| column | domain | meaning |
|---|---|---|
| `magnitude` | ISON numeric literal (int or decimal float), `0 ≤ v ≤ 1`, not a boolean; `nan`, `inf` and exponent forms are not numeric literals in ISON (they parse as strings) and are therefore `MALFORMED_DATAMATICS` by the type rule | relative size/weight intent |
| `role` | `ROLE` | semantic state role |
| `shape_role` | `{ circle, square, diamond, hexagon, triangle, pill, document, person, process } ∪ X` | shape meaning, not geometry |
| `emphasis` | `{ none, low, medium, high }` | emphasis intent |
| `badge` | string, 1–16 Unicode scalar values, no control characters | short annotation (count, marker) |
| `ring` | `ROLE` | ring/halo state role |
| `label` | string, non-empty | display label intent (Core properties stay the data; this is what to show) |
| `visibility` | `{ visible, collapsed, hidden }` | visibility intent |
| `lod_min` | INT64 `0 ≤ v ≤ 1024` | minimum level of detail at which the object appears |
| `selectable`, `focusable`, `expandable`, `drilldown` | `"true"` / `"false"` string tokens | interaction capability markers |
| `temporal_state` | `{ introduced, changed, removed, steady }` | temporal hint |
| `temporal_order` | INT64 `≥ 0` | ordering key for temporal presentation (opaque ticks, not a revision reference — E3) |
| `layout_rank` | INT64 `≥ 0` | layered/ranked layout hint |
| `layout_anchor` | `"true"` / `"false"` | the node is an anchor (keep in place / treat as root) |
| `a11y_text` | string, non-empty | assistive text |
| `a11y_role` | `ROLE` | non-colour state role for assistive technology |

**`table.edges`** — at most one row per edge address (`source_type source_id relation target_type target_id ordinal`, exactly `18` §1.2 including canonical endpoint order for undirected targets). Columns: `role` (`ROLE`), `pattern_role` (`{ solid, dashed, dotted, double } ∪ X`), `emphasis`, `direction_display` (`{ forward, backward, both, none }`), `label`, `visibility`, `lod_min`, `selectable`, `focusable`, `temporal_state`, `temporal_order`, `a11y_text` — same domains as nodes.

**`table.groups`** — `group_id` key (`18` §1.3 token, unique). `intent ∈ { hull, hierarchy, collapse, aggregate }`; `parent_group_id` null or an existing `group_id` (never itself; the parent relation is acyclic); `label`, `role`, `collapsed` (`"true"`/`"false"`, meaningful for `collapse` and `hierarchy`), `visibility`, `lod_min`, `a11y_text` — same domains. A group with no members is permitted (an empty hull is a legitimate intent) but a group must be reachable: either it has members or it is the parent of a group that does (D1).

**`table.members`** — `(group_id, node_type, node_id)` unique; `group_id` must exist (D3); the node must resolve in the target (D4). A node may belong to any number of `hull` groups; among groups with intent `collapse` or `aggregate` a node belongs to **at most one** (a node cannot be collapsed into two places) — `MALFORMED_DATAMATICS` otherwise. `hierarchy` groups may nest; a node's hierarchy groups must form a chain (each is an ancestor or descendant of the others), else `MALFORMED_DATAMATICS`. Both rules report the conflict at the **later** membership in key order (`<group_id>/<node_type>:<node_id>`, by UTF-8 bytes); implementations precompute group ancestry once so validation is linear in memberships plus group depth, never quadratic.

### 1.2 Vocabularies

```text
ROLE = { neutral, active, inactive, selected, warning, negative, positive, info, emphasis-high, emphasis-low } ∪ X
X    = tokens matching x-[a-z0-9-]+          (product/extension namespace; 18 §2's locator rule reused)
```

`selected` is **author-supplied presentation intent** ("show this as selected"), not live UI selection state: actual selection, focus and hover belong to the ISONGraph Visualize interaction runtime and are never written back into a Datamatics payload. A closed vocabulary value outside its set is `MALFORMED_DATAMATICS`. An `x-` value is **preserved and reported** (`unrecognized_roles` in the result, as IGX/1 reports `unrecognized_optional`), never an error and never silently reinterpreted: a consumer that does not know `x-betterify-risk` treats the hint as `null` *for that column only*. Products (Betterify, SkillDen, …) map their semantics into `x-` roles downstream (`05`); Ext never defines them (`11` ADR-E6).

### 1.3 Theme separation (normative)

No column of any table may carry a colour, a font, a pixel/em size, a coordinate, an image reference or a CSS/SVG fragment; there is no "style" column and no free-form attribute map. Everything appearance-related is a role from §1.2 that a downstream theme resolves. This is what makes a Datamatics payload portable across renderers and what *enables* accessible rendering: every visual state has a non-colour role (`a11y_role`, `temporal_state`, `emphasis`) that assistive technology can announce. It does not *guarantee* an accessible interface — the accessibility columns are optional, and a payload with none of them is valid. ISONGraph Visualize (and any other consumer) MUST supply suitable fallback labels, keyboard interaction and non-colour presentation when application hints are absent; IGDM/1 is the channel for intent, not a substitute for the renderer's own accessibility obligations.

## 2. Compactness

Nulls cost one token; the writer sorts fields alphabetically and keeps headers once per block, so a payload with sparse intent is small. Rows exist only for objects that carry at least one non-null hint (D1: a node/edge row whose hint columns are all null is `MALFORMED_DATAMATICS` — noise is not intent). A target with 10⁴ nodes and three hints each is a few hundred KiB; `10` §benchmarks measures token overhead against the bare graph.

## 3. Verification and admission

### 3.1 Verification order (deterministic; first failure wins; `IGDMError.step` names it)

`verify()` runs IGX/1 verification itself (no caller-supplied result), after the same byte-budget preflight as `18` §4.1 (target ≤ `max_graph_bytes`, payload ≤ `max_payload_bytes`; there are no sources in IGDM/1).

| step | checks | code on failure |
|---|---|---|
| **D0 binding** | `igx.verify(binding, target)` succeeds *(raises `IGXError`)*; `table.capabilities` has an `igdm` row with non-null `payload_sha256` (`DATAMATICS_NOT_BOUND`); its range admits `1.0.0` (`DATAMATICS_VERSION_UNSUPPORTED`); `payload_sha256 == sha256(payload bytes)` (`PAYLOAD_DIGEST_MISMATCH`) | as listed |
| **D1 shape** | row counts ≤ `max_rows_per_table` (`DATAMATICS_LIMIT_EXCEEDED`); canonical bytes; six blocks exactly once; fields; `datamatics_spec`; enums, ranges, string rules, `"true"/"false"` tokens; address rules and twins (§1.1); unique node/edge addresses, unique group ids, unique members; all-null hint rows; collapse/aggregate exclusivity; hierarchy chain rule; empty-and-childless groups; `direction` requires non-null `family` | `MALFORMED_DATAMATICS` |
| **D2 target** | `target_artifact_sha256 == sha256(target) == binding.artifact_sha256`; profile equals the binding's | `TARGET_BINDING_MISMATCH` |
| **D3 references** | every `parent_group_id` and every member `group_id` exists; the parent relation has no cycle (a group is never its own ancestor); nesting depth ≤ `max_group_depth` (`DATAMATICS_LIMIT_EXCEEDED`) | `UNRESOLVED_REFERENCE` / `GROUP_CYCLE` |
| **D4 objects** | *(only when the IGX result is `full`; `limited` → `object_resolution = skipped`)* load the target with the pinned Core (`18` §4.1 P4 rules, same code path); every node row, every edge row and every member must exist | `UNRESOLVED_OBJECT` |

Codes: `DATAMATICS_NOT_BOUND`, `DATAMATICS_VERSION_UNSUPPORTED`, `PAYLOAD_DIGEST_MISMATCH`, `DATAMATICS_LIMIT_EXCEEDED`, `MALFORMED_DATAMATICS`, `TARGET_BINDING_MISMATCH`, `UNRESOLVED_REFERENCE`, `GROUP_CYCLE`, `UNRESOLVED_OBJECT`. `IGDMError(code, field, detail, step)`; row fields are `table.<name>.<key>.<column>` where a node row's key is `<node_type>:<node_id>`, an edge row's key is `<source_type>:<source_id>-<relation>-<target_type>:<target_id>#<ordinal>`, a member's key is `<group_id>/<node_type>:<node_id>`.

Unknown-safe behaviour is IGX/1's: an `OPTIONAL igdm` row on a runtime without IGDM/1 is preserved and never interpreted; a `REQUIRED` row there is `UNSUPPORTED_CAPABILITY`.

### 3.2 Admission

IGDM/1 adds **no admission policy**: a payload is admitted iff D0–D4 succeeded and the IGX/1 binding is admitted (`17` §4.2). Datamatics claims no identity of its own; `receipt_posture` is the binding's.

### 3.3 Budgets

```python
@dataclass(frozen=True)
class Limits:
    max_payload_bytes: int = 64 * 1024 * 1024
    max_graph_bytes: int = 256 * 1024 * 1024
    max_rows_per_table: int = 1_048_576
    max_group_depth: int = 64
DEFAULT_LIMITS = Limits()
```

## 4. Runtime API (`isongraph_ext.igdm`, Python 3.12)

Same exact pins. Addressing types are imported from `igpv` (`NodeRef`, `EdgeAddress`); object resolution reuses `igpv.resolve`.

```python
@dataclass(frozen=True)
class NodeHints:   node: NodeRef; magnitude: float | None = None; role: str | None = None; shape_role: str | None = None
                   emphasis: str | None = None; badge: str | None = None; ring: str | None = None; label: str | None = None
                   visibility: str | None = None; lod_min: int | None = None; selectable: bool | None = None
                   focusable: bool | None = None; expandable: bool | None = None; drilldown: bool | None = None
                   temporal_state: str | None = None; temporal_order: int | None = None; layout_rank: int | None = None
                   layout_anchor: bool | None = None; a11y_text: str | None = None; a11y_role: str | None = None
@dataclass(frozen=True)
class EdgeHints:   edge: EdgeAddress; role, pattern_role, emphasis, direction_display, label, visibility: str | None = None
                   lod_min: int | None = None; selectable: bool | None = None; focusable: bool | None = None
                   temporal_state: str | None = None; temporal_order: int | None = None; a11y_text: str | None = None
@dataclass(frozen=True)
class Group:       group_id: str; intent: str; parent_group_id: str | None = None; label: str | None = None; role: str | None = None
                   collapsed: bool | None = None; visibility: str | None = None; lod_min: int | None = None; a11y_text: str | None = None
@dataclass(frozen=True)
class Member:      group_id: str; node: NodeRef
@dataclass(frozen=True)
class LayoutHints: family: str | None = None; direction: str | None = None; stability: str | None = None

@dataclass(frozen=True)
class DatamaticsPayload:
    target_artifact_sha256: str; target_serialization_profile: str
    layout: LayoutHints = LayoutHints(); nodes: tuple[NodeHints, ...] = (); edges: tuple[EdgeHints, ...] = ()
    groups: tuple[Group, ...] = (); members: tuple[Member, ...] = ()
    def to_ison(self) -> str; def from_ison(text, *, limits=DEFAULT_LIMITS); digest; def check(self) -> None   # D1 rules that need no bytes

class IGDMError(Exception): code, field, detail, step        # D0..D4

def verify(payload, binding, target, *, limits=DEFAULT_LIMITS, baselines=BASELINES, registry=DEFAULT_REGISTRY) -> tuple[igx.VerificationResult, DatamaticsVerification]
def verify_and_admit(payload, binding, target, *, limits, baselines, registry, policy) -> tuple[igx.VerificationResult, DatamaticsVerification, igx.AdmissionResult]
def bind(target, payload, *, requirement="REQUIRED", serialization_profile, producer_port, identity_claim, capabilities=(), consumer=None, baseline, registry, policy, limits) -> igx.ExtensionBinding

@dataclass(frozen=True)
class DatamaticsVerification:
    payload_sha256: str; binding_digest: str; target_artifact_sha256: str
    object_resolution: Literal["full", "skipped"]
    unrecognized_roles: tuple[str, ...]        # distinct x- values seen, sorted, with their column: "nodes.role:x-betterify-risk"
    counts: Mapping[str, int]; steps_passed: tuple[str, ...]   # ("D0","D1","D2","D3","D4")

DEFAULT_REGISTRY = {"igpv": "1.0.0", "igdm": "1.0.0"}     # igx.registry; igdm re-exports it
```

Booleans are Python `bool | None` in records and `"true"`/`"false"` string tokens on the wire (§1); `from_ison` maps the tokens, and any other value (including a bare ISON boolean) is `MALFORMED_DATAMATICS`.

CLI: `python -m isongraph_ext.igdm verify <graph> <binding> <payload> [--allow-retired]` → one ISON document with `meta.verification`, `meta.datamatics`, `meta.admission`; exit 0 / 1 (`meta.error`, `IGXError` or `IGDMError`) / 2 denied / 64 usage. Streams UTF-8, LF.

### 4.1 Composition with IGPV/1

A binding may carry both `igpv` and `igdm` rows; they are independent payloads over the same target and verify independently. A Datamatics row never references provenance records (no cross-payload identifiers in E4); E5/E6 may emit both for a derived graph.

## 5. Conformance vectors (`vectors/igdm1/`)

`manifest.ison` → `table.vectors`: `id target binding payload expect step detail`, conventions as `vectors/igpv1` (generator-made graphs under `graphs/synthetic/`, binding derived from the shipped payload bytes unless the row tests the binding, `expect ∈ { verify_ok, reject:<CODE>, admit_ok, admit:<CODE> }`, `step` the D step or `A1`, `detail` holding `roles:<csv>`, `resolution:skipped`, `limits:<name>=<int>`). `IGXError` raised inside D0 is recorded as `D0`.

| id | expect | step |
|---|---|---|
| ok/node-hints-full-row, ok/edge-hints, ok/multigraph-edge-ordinal, ok/undirected-edge-canonical | verify_ok + admit_ok | — |
| ok/groups-nested-hull-and-collapse, ok/empty-hull-group, ok/hierarchy-chain | verify_ok | — |
| ok/x-roles-preserved | verify_ok, `roles:nodes.role:x-betterify-risk,edges.pattern_role:x-wavy` | — |
| ok/layout-only, ok/empty-datamatics, ok/optional-igdm-row, ok/limited-runtime-skips-resolution, ok/reserialize-stable, ok/igpv-and-igdm-same-binding | verify_ok (+ admit:STALE_BINDING for limited) | — |
| reject/not-bound, reject/version-range-excludes, reject/payload-digest-mismatch, reject/binding-fails-igx | listed codes | D0 |
| reject/oversized-payload, reject/oversized-target | `DATAMATICS_LIMIT_EXCEEDED` | D1 |
| reject/noncanonical-text, reject/rows-not-sorted, reject/unexpected-block, reject/role-outside-vocabulary, reject/magnitude-out-of-range, reject/magnitude-nan, reject/lod-negative, reject/boolean-not-token, reject/badge-too-long, reject/all-null-hint-row, reject/duplicate-node-row, reject/twin-ids, reject/collapse-exclusivity, reject/hierarchy-not-chain, reject/group-self-parent, reject/group-unreachable, reject/direction-without-family, reject/node-id-outside-int64 | `MALFORMED_DATAMATICS` | D1 |
| reject/target-sha-mismatch, reject/target-profile-mismatch | `TARGET_BINDING_MISMATCH` | D2 |
| reject/unknown-parent-group, reject/member-unknown-group | `UNRESOLVED_REFERENCE` | D3 |
| reject/group-cycle | `GROUP_CYCLE` | D3 |
| reject/group-depth-budget | `DATAMATICS_LIMIT_EXCEEDED` (`limits:max_group_depth=2`) | D3 |
| reject/unresolved-node, reject/unresolved-edge, reject/unresolved-member, reject/undirected-noncanonical-endpoints | `UNRESOLVED_OBJECT` | D4 |
| reject/two-faults-first-wins | wrong target sha and unresolved node → `TARGET_BINDING_MISMATCH` | D2 |

## 6. Repository

```text
isongraph-ext/src/isongraph_ext/igdm/{__init__, errors, records, payload, verify, bind, __main__}.py
isongraph-ext/src/isongraph_ext/igx/registry.py        DEFAULT_REGISTRY gains igdm
vectors/igdm1/, scripts/make_vectors_igdm.py, isongraph-ext/tests/test_igdm_*.py, tests/test_vectors_igdm.py
```

## 7. Out of scope

Layout computation, rendering, scene/camera state, animation, themes (role → appearance), product vocabularies, hint merging across payloads, hints on provenance records, references to revisions (E3), TS runtime, any change to Core.

## 8. Changes this spec makes to earlier documents

- `17` §0/§3: `DEFAULT_REGISTRY` gains `igdm 1.0.0` (same mechanism as `18` §9); E1 vectors unchanged.
- `05`: superseded by this document for E4.
- `01`: E4 row references this spec; E5/E6 lines note that derived graphs may carry IGDM/1 payloads.

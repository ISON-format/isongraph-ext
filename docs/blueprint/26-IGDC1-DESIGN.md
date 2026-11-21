# IGDC/1 — Datamatics Consumption: typed-address mapping and canonical hint contract

Status: **DRAFT rev 2 FOR OWNER FREEZE REVIEW (2026-11-20)** — corrects rev 1 after the owner's rev 1 review (architecture and ISON wire choices approved; freeze held). · Serves requirements EXT-2 and EXT-3 of `24-EXT-REQUIREMENTS-FOR-VIZ.md`. Consumes IGDM/1 (`19`, FROZEN rev 1) and IGPV/1 addressing (`18`, FROZEN rev 1) through IGX/1 (`17`, FROZEN rev 3). Changes **nothing** in IGX/1, IGPV/1, IGDM/1, IGP/1, Semantic/2 (`13`, a draft owned by Core), IGS/1 or IGL/1. **No runtime code exists for this spec in the repository**; every example and every vector count below was produced and run against the pinned runtime (ison-py 1.2.0, ison-graph 1.4.1) by throwaway scripts outside the repository, not typed by hand (`ERRATA.md` E-3 is the lesson). Changing §1–§6 after implementation ships is a new spec version (`IGDC/2`), never an edit. Pairs with `25-IGAR1-DESIGN.md` rev 2.

## Rev 2 change log (what changed since rev 1, and why)

| # | Owner finding | Change | Where |
|---|---|---|---|
| F3 | Reject repeated column declarations and unconsumed rows; C0 must not be the only defence | New shared strict reader (`strict_ison`): byte budget, canonical form, exact block set, **no repeated column, no summary row, no typed/computed column declaration, no reference cell, scalar cells only**. Probed: ison-py keeps a repeated header, lets the **last** value win, pads a short row, and re-emits summary lines, `name:int` declarations and `:ref` cells unchanged, so a re-emission check alone passes them | §4 C0/C1, §5 |
| budget | Documented byte budget before parsing untrusted ISON | Reader budget = IGDM/1 `Limits.max_payload_bytes` (default 64 MiB), applied **before** decoding; row budget = `max_rows_per_table`; derived output must fit the same budget (P1). No new capacity claim | §4, §3 |
| vectors | IGDC address-vector coverage incomplete; runner executes only `tag`/`parse` | Address set rebuilt as five executable tables (`vectors`, `edges`, `order`, `edge_order`, `twins`), **142 rows, every one run**, row counts pinned in the runner; consumption set is dispatched by explicit `op`, **86 rows**, counts pinned | §5 |
| probe | Empty-string id: run the probe, record the outcome, no `pytest.skip` as evidence | Probe run. Core refuses empty / whitespace / `:` / `\|` string ids; IGDM/1 D1 alone accepts them; D4 refuses them; limited runs are stopped by P0. Pinned as **25 assertions, zero skips**. Generic tagged syntax (`s:`) stays valid; source acceptance is a separate fact (§1.7) | §1.7 |
| rulings | Owner decisions on rev 1 open points | Multigraph and `isonl-v1` carried (approved); `_x` siblings (approved); writer row order separate from semantic order (approved); `target_directed` / `target_multigraph` retained and must originate from the verified target (§2.1, §3); empty-string ids per §1.7 | §2, §7 |
| F4 | Browser-consumer qualification must be explicit | New §7: two routes; no TypeScript verifier is claimed; a SHA-256 match does not establish ISONCS canonicality | §7 |

Unchanged from rev 1: the ISON wire format, the tagged `igs-addr/1` mapping, `_x` sibling columns, C0–C4 step order, codes, boundary rules.

## 0. What IGDC/1 is

A **consumer contract**: a canonical ISON companion `<graph>.igdc.ison` that states, for one verified IGDM/1 payload over one exact target graph, the hints a consumer reads, with every graph address in the typed `igs-addr/1` form. It is derived by a pure function from verified inputs (§3) and is never an input to verification of anything.

It exists because two things that Visualize needs are not guaranteed by IGDM/1's wire form alone:

1. **Typed identity that survives any carrier.** IGDM/1 keeps integer and string ids apart only through the *cell type* of the ISON document (`7` versus `"7"`). That is sound inside ison-py and unverified in every other port; IGDC/1 makes the distinction part of the *value* (`i:7`, `s:7`), so it cannot be erased by a reader that coerces cells.
2. **A graceful-degradation shape for `x-` roles.** IGDM/1 §1.2 says a consumer that does not know an `x-` role treats the hint as `null` for that column only. IGDC/1 builds that behaviour into the columns (§2.2) so a consumer that reads only the closed columns degrades correctly without parsing `x-` tokens at all.

IGDC/1 adds **no Datamatics semantics**. Every column is an IGDM/1 column; every value is an IGDM/1 value, re-spelled only where §1 and §2.2 say. It is not a replacement for IGDM/1, not an IGS/1 scene, and carries no verdict: schema validity, verifier results and admission policy belong to IGAR/1 (`25`) and never appear in a scene (§6).

Ext is the format owner here (ISON is Ext's exchange format). IGS/1 and IGL/1 keep their own frozen canonical JSON contracts; nothing in this document changes them.

## 1. Typed-address mapping (`igs-addr/1`) — EXT-2

IGS/1 §1.2 defines the target scheme. This section defines how every address that IGDM/1 and IGPV/1 already carry maps into it. The mapping is **a total function on D1-valid addresses** and a **partial function with stable codes on anything else**; it never guesses.

### 1.1 Node ids

| source (`NodeRef.node_id` as IGPV/1 §1.2, IGDM/1 D1) | tagged id | rule |
|---|---|---|
| integer `n`, `−2^63 ≤ n ≤ 2^63−1` | `i:` + decimal of `n` | `0` or `-?[1-9][0-9]*`, ASCII digits; exactly the canonical decimal; `-0`, `+5`, leading zeros cannot arise from an integer |
| string `s` | `s:` + `s` verbatim | no trimming, no normalisation, no case folding; NFC and NFD stay different ids; the empty string maps to `s:` (§1.7) |
| boolean, float, null, integer outside INT64 | **rejected**, `INVALID_ADDRESS` | not ids (IGPV/1 §1.2) |
| string that is not UTF-8-encodable (lone surrogate) | **rejected**, `INVALID_ADDRESS` | no bytes, no digest (IGDM/1 D1) |

The mapping reads the **type of the value**, never its spelling. A string whose text is all digits stays `s:`; a string that already begins `i:` or `s:` is wrapped again (`"i:7"` → `s:i:7`). Decimal-looking text is never promoted to an integer id, and `i:7` and `s:7` are different identities.

Inverse (`parse_id`): the first two characters must be `i:` or `s:` (lower case, exactly); `i:` is followed by a canonical INT64 decimal (anything else — `-0`, `+5`, `007`, `1.0`, a space, a non-ASCII digit, an out-of-range value, an empty remainder — is `INVALID_ADDRESS`); `s:` is followed by the string verbatim, empty allowed, a lone surrogate not. Any other prefix, or none, is `INVALID_ADDRESS`. A bare `7` is **not** a tagged id.

ISON's native reference form (`:type:id`) is **not used** and never consulted: it can depend on a target column's declared type and would erase the distinction this section exists to keep.

### 1.2 Types, relations, ordinals

- `node_type` and `relation` are Core identifiers, unchanged: non-empty, no whitespace, none of `:` `|` `"` `\`. A violation is `INVALID_ADDRESS`.
- `ordinal` is the canonical decimal string `0|[1-9][0-9]*` (ASCII digits), unchanged (`"0"`, `"1"`, `"10"`; `"01"`, `"00"`, `"-1"`, `""` are `INVALID_ADDRESS`). In a graph with `target_multigraph = "false"` every ordinal is `"0"`; otherwise `INVALID_ADDRESS`.
- An edge address is `(source type, source tagged id, relation, target type, target tagged id, ordinal)`. The six columns are the whole edge identity.

### 1.3 Semantic order and undirected endpoints

Semantic order (IGS/1 §5.5; `13` §2.3; implemented as `igpv.resolve.node_ref_key`): by `node_type` UTF-8 bytes; then every INT64 before every STRING; INT64 by signed numeric value; STRING by UTF-8 bytes. Edges: source, `relation` bytes, target, ordinal **bytes** (`"1" < "10" < "2"`).

For `target_directed = "false"` an edge row states its endpoints in canonical order (`source ≤ target` in semantic order; a self-loop is one edge). A non-canonical row is `INVALID_ADDRESS` (C2). For a directed graph the endpoints are as written.

**Row order is not semantic order.** IGDC/1 bytes are the canonical writer's output, which sorts rows by every column as text (§2). For tagged ids that disagrees with semantic order (`i:10` sorts before `i:2`; `i:-1` after `i:0`). A consumer that needs semantic order MUST sort with the §1.3 comparator (`semantic_key`, `edge_semantic_key`); it MUST NOT assume the file is in it. UTF-16 code-unit order (the JavaScript default) is **not** UTF-8 byte order for characters outside the BMP (U+FF5E sorts after U+1F600 in UTF-16, before it in UTF-8). The `order` vectors (§5) catch both traps.

### 1.4 Twins

The twin rule is inherited from IGDM/1 D1 (`ID-TWIN-INVARIANT`), not new: within one `node_type`, `i:<d>` and `s:<d>` where `<d>` is the canonical decimal of the integer may not both appear **anywhere in the document** (node rows, edge endpoints, members). Violation: `TWIN_IDS`. (`s:007` and `i:7` are not twins; `s:-0` and `i:0` are not twins; `s:7` and `i:7` are.) Core enforces the same rule itself: adding string `"7"` beside integer `7` in one node type is `DuplicateNodeError`.

### 1.5 Where the mapping applies

The same function maps IGPV/1 `NodeRef`/`EdgeAddress` values (the cell-typed `node_id`/`source_id`/`target_id` columns of `table.objects`). IGDC/1 itself carries only IGDM/1 content; applying the mapping to IGPV/1 is available to consumers and is covered by the address vectors (§5).

### 1.6 What this mapping cannot do

It cannot recover a type that the carrier already lost. If a payload reaches Ext with its ids already coerced (for example an untyped export), the information is gone and Ext can only reject or be told. IGDM/1 and IGPV/1 payloads are verified at D1 with cell types intact, so for verified payloads the mapping is lossless. **IGDC/1 claims losslessness only for inputs that passed IGDM/1 D1** and says so in its production gate (§4). Core ports other than Python are out of scope: the Rust/C#/C++ ports hold string ids (`13` §7); Ext does not mark them equivalent here.

### 1.7 Valid tagged syntax versus what a verified target can contain (probe result)

The generic mapping accepts every string, the empty string included: `tag_id("")` is `s:` and `parse_id("s:")` is `""`. That is **syntax**. Whether a *verified target* can carry such an id is a separate fact, recorded by running the probe against the pinned runtime (`tests/test_igdc_probe.py`, 25 assertions, **no skips**):

| fact (ison-graph 1.4.1 · ison-py 1.2.0 · IGDM/1) | consequence for IGDC/1 |
|---|---|
| Core refuses a node id that is empty, contains whitespace, `:` or `\|` (`InvalidIdentifierError`) | `s:` (empty), `s:a:b`, `s:i:7` (the string `"i:7"`) cannot be a node of any Core graph |
| Core accepts digit-like and awkward strings: `007`, `-0`, `+5`, `1e3`, `q"q`, `é`, NFD `é`, `😀`, `～`, `-`, `~`, the 19-digit decimal string 2^63 (one above INT64 max), and they round-trip | these are the ids the **consumption** vectors use (§5) |
| IGDM/1 D1 alone, with no target, accepts the empty string id | D1-valid is not Core-valid |
| D4 (object resolution against the target) refuses such a node: `UNRESOLVED_OBJECT` | `consume` over a full verification can never produce `s:` |
| A **limited** verification (retired baseline, Core runtime absent) skips D4, so IGDM/1 alone lets the empty id through | IGDC/1's P0 refuses it: `RESOLUTION_REQUIRED` |

So: **address-mapping vectors** (`vectors/igs-addr`, a pure function) may use `s:` and `s:i:7`; **consumption vectors** (`vectors/igdc1`, end to end through a verified target) use only Core-representable ids. The hint-document checks C0–C3 are syntactic and accept a document containing `s:`; such a document can never pass C4 or a receipt, which is the contract (a well-formed hint set is not a verified one, §4).

## 2. Wire format

One companion document `<graph>.igdc.ison`, bytes **exactly** ison-py's canonical writer output (`17` §2.1 applies verbatim): UTF-8, LF, no trailing newline, blocks ordered by `kind.name`, fields by name, rows by every column with nulls last. Any other byte sequence is not an IGDC/1 document (`MALFORMED_CONSUMPTION`, field `canonical_form`). Exactly these blocks, each **exactly once**: `meta.igdc`, `meta.layout`, `table.nodes`, `table.edges`, `table.groups`, `table.members` (tables may be empty). Boolean columns are the **string tokens** `"true"`/`"false"` as in IGDM/1 (a bare ISON boolean is `MALFORMED_CONSUMPTION`). Each block declares **exactly** the columns of §2.1, each **once** (§4 C1).

### 2.1 Blocks

**`meta.igdc`** — one row:

| field | domain |
|---|---|
| `consumption_spec` | `IGDC/1` |
| `address_scheme` | `igs-addr/1` |
| `igdm_payload_sha256` | 64 lowercase hex; `sha256` of the exact IGDM/1 payload bytes this document was derived from |
| `target_artifact_sha256` | 64 lowercase hex; equals the payload's |
| `target_serialization_profile` | `ison-v1` or `isonl-v1`, as in the payload (IGDC carries it; IGS/1's `ison-v1`-only rule is applied by the IGS adapter, which MUST reject an unsupported profile rather than downgrade it) |
| `target_directed`, `target_multigraph` | `"true"`/`"false"` tokens. **They originate from the verified target**: derivation (§3) reads them from the target graph as loaded by the pinned Core. They are retained so a consumer can check undirected endpoint order and simple-graph ordinals without loading the target. Read from a hint document alone (C0–C3) they are *assertions*, not facts; C4 or a trusted IGAR/1 receipt is what makes them facts |

**`meta.layout`** — one row: `family`, `family_x`, `direction`, `stability` (§2.2 for `family_x`).

**`table.nodes`** — one row per IGDM/1 node row. Key: `(node_type, node_id)` with `node_id` tagged (§1.1). Hint columns: exactly IGDM/1 §1.1's (`magnitude role shape_role emphasis badge ring label visibility lod_min selectable focusable expandable drilldown temporal_state temporal_order layout_rank layout_anchor a11y_text a11y_role`), with the §2.2 `_x` siblings.

**`table.edges`** — one row per IGDM/1 edge row. Key: the six address columns (§1.2). Hint columns exactly IGDM/1 §1.1's edge columns, with `_x` siblings.

**`table.groups`** — one row per group: `group_id`, `intent`, `parent_group_id`, `label`, `role`, `role_x`, `collapsed`, `visibility`, `lod_min`, `a11y_text`.

**`table.members`** — explicit membership records `(group_id, node_type, node_id)`, `node_id` tagged. Membership is **never** packed into a list-valued cell: ISON cells are scalars, and a bracketed value would read as a string (`19` §2). One row, one membership.

Nulls mean "no intent", never a default, as in IGDM/1. Numeric columns that can exceed 2^53 (`temporal_order`, `layout_rank`) are exact INT64 on the wire; a JavaScript `Number` cannot hold them (§7).

### 2.2 `x-` roles: sibling columns

The IGDM/1 columns where an `x-` token is legal are `role`, `ring`, `a11y_role`, `shape_role` (nodes), `role`, `pattern_role` (edges), `role` (groups) and `family` (layout). Each gets a sibling `<column>_x`. Derivation (§3) puts a closed-vocabulary value in the closed column and an `x-` token in the sibling, **never both**: for one subject exactly one of `<column>` and `<column>_x` is non-null, or both are null.

- A consumer that knows no `x-` role reads the closed columns only; every hint carried by an unknown `x-` role is already `null` there — IGDM/1's "null for that column only" with no token parsing.
- A consumer that knows `x-betterify-risk` reads `role_x`. IGDC never interprets or defines an `x-` role (`11` ADR-E6); products map them downstream.
- `_x` values match `x-[a-z0-9-]+`. An `x-` token in a closed column, a non-token in an `_x` column, or both columns set is `MALFORMED_CONSUMPTION` (C1).

### 2.3 Example (byte-exact: `vectors/igdc1/hints/ok--x-roles-preserved.igdc.ison`, digest `457d9ebbe84eae31dead4c080200c5a02850ea7bc3eb2b789a9914f51da83c2b`)

```text
meta.igdc
address_scheme consumption_spec igdm_payload_sha256 target_artifact_sha256 target_directed target_multigraph target_serialization_profile
igs-addr/1 IGDC/1 f55491679b655d9cd943ca804a142287c724035d30b9840a3d4daeb584e585d4 2b0bd5b0e74e8e92a3e5f47f5b3b92c17ce0f9b0641714c0dc11b8e81d6e89c2 "true" "false" ison-v1

meta.layout
direction family family_x stability
LR layered null stable

table.edges
a11y_text direction_display emphasis focusable label lod_min ordinal pattern_role pattern_role_x relation role role_x selectable source_id source_type target_id target_type temporal_order temporal_state visibility
null null null null null null "0" null x-wavy knows null null null i:1 order s:s1 order null null null

table.groups
a11y_text collapsed group_id intent label lod_min parent_group_id role role_x visibility
null "false" region hull "Region A" 0 null neutral null visible
null "true" cluster collapse Cluster 1 region emphasis-low null visible

table.members
group_id node_id node_type
cluster i:1 order
region i:1 order
region s:s1 order

table.nodes
a11y_role a11y_role_x a11y_text badge drilldown emphasis expandable focusable label layout_anchor layout_rank lod_min magnitude node_id node_type ring ring_x role role_x selectable shape_role shape_role_x temporal_order temporal_state visibility
null null null null null null null null null null null null null i:1 order null null null x-betterify-risk null null null null null null
null null null null null null null null null null null null null s:s1 order null null warning null null null null null null null
```

(The source payload's `1` and `s1` were an integer and a string id; the writer emits `i:1` and `s:s1` as plain strings, and `i:7`, `s:7` round-trip as strings through ison-py 1.2.0 — verified for the whole id grammar of §1.1 including `"007"`, `"-0"`, `"1e3"` and INT64 extremes. The writer, not this text, decides quoting.)

## 3. Derivation (pure; EXT-3)

`derive(P, d, m) → H` where `P` is an IGDM/1 payload that passed D0–D4 with **object resolution `full`**, and `d`, `m` are the target graph's directedness and multigraph-ness **as read by the pinned Core from the verified target**. Nothing else is read. Rules:

1. `meta.igdc` as §2.1; `igdm_payload_sha256 = sha256(exact payload bytes)`; `target_*` copied from `P` except `d`, `m`.
2. Every IGDM/1 node, edge, group and member row yields **exactly one** IGDC/1 row (row counts equal), in no particular order (the writer orders them). No row is added, dropped, merged or reordered by meaning.
3. Address columns: `node_id`/`source_id`/`target_id` become tagged ids (§1.1); all other address columns are copied.
4. Hint columns: copied unchanged (magnitude keeps its int-or-float literal; booleans stay tokens) except the §2.2 split.
5. `meta.layout`: copied, with `family` split as §2.2.
6. `derive` is deterministic and **byte-reproducible**: the same verified inputs and the same pinned writer give the same bytes. It reads no clock, no environment and no other file.
7. The derived document must fit the hint byte budget (P1, §4). It is refused, never truncated.

## 4. Verification of a hint document (C0–C4; first failure wins; `IGDCError.step` names it)

Consumer-side structural checks, C0–C3, need no target and no Python runtime beyond a conforming ISON canonical reader; C4 is the Python reference's recomputation.

| step | checks | code |
|---|---|---|
| **C0 bytes** | **byte budget** `≤ Limits.max_payload_bytes` (default 64 MiB) **before any decoding or parsing**; valid UTF-8; no byte-order mark; no CR; re-emission through the pinned writer equals the input; and (a second, independent check over the typed model) the model re-emits the same bytes | `DATAMATICS_LIMIT_EXCEEDED` (field `max_payload_bytes`) / `MALFORMED_CONSUMPTION` (`canonical_form`, `document`) |
| **C1 shape** | exactly the six blocks, each once, no others; **each block declares exactly the §2.1 columns, each once** (a repeated declaration is refused even when the canonical writer would emit it); **no summary row (`---`), no typed or computed column declaration (`name:int`, `name:computed`), no reference cell (`:type:id`)**; cells are scalars (string, integer, number, boolean, null); meta blocks have exactly one row; row budget `max_rows_per_table`; `consumption_spec`, `address_scheme` literals; hex fields; tokens; closed vocabularies (IGDM/1 §1.1–§1.2); §2.2 sibling rules; INT64 ranges of `lod_min`, `temporal_order`, `layout_rank`; magnitude `0 ≤ v ≤ 1` | `MALFORMED_CONSUMPTION` / `DATAMATICS_LIMIT_EXCEEDED` (field `max_rows_per_table`) |
| **C2 addresses** | every tagged id parses (§1.1); identifier rules; ordinal rules incl. the simple-graph rule; unique node rows, edge rows, group ids, members; twin rule (§1.4); undirected canonical endpoints (§1.3) | `INVALID_ADDRESS` / `TWIN_IDS` |
| **C3 references** | every `parent_group_id` and member `group_id` exists; the parent relation is acyclic; depth ≤ `max_group_depth` (IGDM/1's own D3, reused, not re-implemented) | `UNRESOLVED_REFERENCE` / `GROUP_CYCLE` / `DATAMATICS_LIMIT_EXCEEDED` |
| **C4 derivation** | *(Python reference only; needs the IGDM/1 payload, binding and target)* `derive` over the verified inputs yields exactly these bytes — including `target_directed` and `target_multigraph` | `DERIVATION_MISMATCH` |

Why C1 states the structural rules separately: against ison-py 1.2.0 a repeated column header parses without error, is kept in the block's field list while the row silently keeps the **last** value, and the canonical writer re-emits it (`a a b` with equal cells is canonical output); `---` summary lines, `name:int` / `name:computed` declarations and `:ref` cells likewise parse and re-emit unchanged. Only a **short row** (fewer cells than columns, which the parser pads with `null`) is caught by C0 re-emission alone, and the vectors prove that too. Set-of-names comparison is not a defence against any of these.

C0–C3 do **not** re-check IGDM/1's relation rules (collapse/aggregate exclusivity, hierarchy chain, reachable groups) and do not require a row to carry a hint. A document that passes C0–C3 is a well-formed hint set, not a verified one; **C4, or an IGAR/1 receipt delivered through a trusted channel (`25`), is what ties it to a verified IGDM/1 payload.**

Production preconditions of `consume()`:

- **P0** — the inputs passed `igdm.verify` with `object_resolution = "full"`. A `limited` result (retired baseline whose Core runtime is not installed) is `RESOLUTION_REQUIRED`: IGDC does not claim address facts it could not re-derive.
- **P1** — the derived document fits the hint byte budget `Limits.max_payload_bytes` (the same budget class as the payload; a payload at its limit may expand through tagged ids and `_x` siblings and is then refused with `DATAMATICS_LIMIT_EXCEEDED`, field `max_payload_bytes`, step `P1`).

IGX/1 and IGDM/1 errors from verification propagate **unchanged**; IGDC does not wrap them. `consume()` does **not** call `admit()`: whether a binding is admitted is IGAR/1's concern, recorded beside, never inside, the hint set.

Codes: `MALFORMED_CONSUMPTION`, `INVALID_ADDRESS`, `TWIN_IDS`, `UNRESOLVED_REFERENCE`, `GROUP_CYCLE`, `DATAMATICS_LIMIT_EXCEEDED`, `DERIVATION_MISMATCH`, `RESOLUTION_REQUIRED`. `IGDCError(code, field, detail, step)`; row fields use IGDM/1's key shapes with tagged ids (`table.nodes.<type>:<tagged id>.<column>`).

## 5. Vectors — `vectors/igs-addr/` and `vectors/igdc1/` (complete inventory)

Independence rule: **expected files are not produced by the production code.** `scripts/make_vectors_igdc.py` imports only `ison_parser` for the address set (hand-written literals) and, for the consumption set, builds *inputs* through the existing public igx/igdm API and takes the verdict of input-level rejections from the **existing** verification path as an oracle; the expected `*.igdc.ison` files come from a separate reference deriver that reads the **parsed IGDM/1 wire document** (the production `derive` reads payload records: two independent paths to the same bytes). The production `igdc` package is then tested against the files. Every file is pinned in each set's `manifest.ison` and `SHA256SUMS` (closes EXT-9's remaining gap). **Every row of both manifests is normative and executed; a port claims conformance by passing all rows, and the row counts are part of the claim.** Runners fail on an unknown `kind`/`op`; per-table and per-`(op, expect)` counts are pinned so a row cannot be silently dropped; every `reject` row must raise exactly its `(code, step)`.

### 5.1 `vectors/igs-addr/` — 142 rows in five tables

Typed literals (`int:7`, `str:7`, `bool:true`, `float:1.5`, `null:`, `surrogate:d800`, `tagged:i:7`, `tagged-lone:d800`) state a value's type; no reader infers it from digits.

| table (rows) | ids | expectation |
|---|---|---|
| `vectors` kind `tag` (28) | ok: int-7, string-7, int-zero, int-negative-one, int64-min, int64-max, string-007, string-minus0, string-1e3, string-leading-plus, string-looks-tagged-i, string-looks-tagged-s, string-beyond-int64, string-arabic-indic-digit, string-nfc, string-nfd, string-astral, string-fullwidth-tilde, string-with-quote, string-empty-is-valid-syntax · reject: int64-overflow, int64-underflow, bool-true-id, bool-false-id, float-id, float-integral-id, null-id, lone-surrogate-id | `tag_id` gives the stated tag, and `parse_id(tag)` returns the same value **of the same type** / raises `INVALID_ADDRESS` (C2) |
| `vectors` kind `parse` (23) | ok: parse-i-7, -s-7, -s-007, -s-looks-tagged, -s-empty, -i-min, -i-max · reject: parse-bare-7, -i-leading-zero, -i-minus-zero, -i-plus, -i-empty, -i-decimal-point, -i-space, -i-trailing-space, -i-arabic-indic-digit, -i-overflow, -i-underflow, -unknown-tag, -uppercase-tag, -empty, -tag-without-colon, -s-lone-surrogate | `parse_id` → typed literal / `INVALID_ADDRESS` |
| `vectors` kinds `node_type`, `relation` (20) | ok: plain, unicode, punctuation (each) · reject: empty, space, colon, pipe, quote, backslash, tab (each) | Core identifier rule: ok / `INVALID_ADDRESS` |
| `edges` (19) | ok: directed-as-written, directed-string-to-int, undirected-canonical-int-before-string, -ints-numeric, -negative-first, -type-bytes, undirected-self-loop, multigraph-ordinal-0, -1, -10 · reject: undirected-string-before-int, undirected-ints-out-of-order, undirected-type-bytes-out-of-order, simple-graph-ordinal-1, ordinal-leading-zero, -double-zero, -negative, -empty, -not-ascii-digit | `edge_address` yields the stated endpoint tags and ordinal / `INVALID_ADDRESS` |
| `order` (33 rows, 7 vectors) | order-mixed, order-ints-numeric-not-text, order-every-int-before-every-string, order-int64-extremes, order-utf8-not-utf16, order-type-bytes-first, order-string-bytes-not-case-folded | the stated `position` **is** the `semantic_key` order; trap `text` (plain-text sort differs) or `utf16` (UTF-16 code-unit sort differs) is asserted |
| `edge_order` (11 rows, 3 vectors) | edge-order-ordinal-bytes (`0 < 1 < 10 < 2`), edge-order-relation-bytes, edge-order-source-then-relation | `edge_semantic_key` order |
| `twins` (8) | reject: twin-i7-s7, twin-s7-i7-reversed, twin-i0-s0, twin-negative · ok: twin-not-s007-vs-i7, twin-not-s-minus0-vs-i0, twin-not-across-types, twin-not-two-ints | `TwinGuard`: `TWIN_IDS` (C2) / ok |

### 5.2 `vectors/igdc1/` — 86 rows; `op` selects what runs

Manifest columns: `id op target binding payload hints expect code step detail`. `op ∈ {consume, verify, derivation}`: `consume` runs `consume(payload, binding, target)` (ok: bytes **equal the expected hint file exactly**, and the file passes C0–C3 and C4; reject: the stated error, propagated unchanged from igx/igdm where the code is theirs); `verify` runs C0–C3 on a hint document; `derivation` runs C4 (`verify_derivation`). `detail` carries `limits:<name>=<int>` and `baselines:all` exactly as `vectors/igdm1`.

| op · expect · code · step | rows | ids (prefix `ok/` or `reject/` omitted) |
|---|---|---|
| consume · ok (19) | 19 | node-hints-full-row, edge-hints, groups-members-resolved, hierarchy-chain, x-roles-preserved, x-roles-all-columns (all six `_x` columns, one `x-` token and one closed value each), layout-only, layout-intent, empty-datamatics, empty-hull-group, multigraph-ordinals (`target_multigraph = "true"`, ordinals `0`,`10`: carried, not rejected), undirected-canonical-endpoints (`target_directed = "false"`), isonl-profile-carried, id-types-distinct (`i:7`, `s:s`, `s:7`, `i:7` across four node types), string-ids-digit-like-and-unicode (13 ids: `007 -0 +5 1e3 7`, the 19-digit decimal string 2^63 (one above INT64 max), `q"q`, `é`, NFD `é`, `😀`, `～`, `-`, `~`), int64-extremes, int-id-ordering-trap (the file's row order is asserted **not** to be semantic order), accessibility-fields (quotes, `\|`, `:`, Unicode in labels), int64-hint-values (`temporal_order = 2^53+1`, `layout_rank = INT64 max`) |
| consume · reject (7) | 7 | target-sha-mismatch `TARGET_BINDING_MISMATCH` D2 · binding-artifact-mismatch `SOURCE_BINDING_MISMATCH` V4 · payload-digest-mismatch `PAYLOAD_DIGEST_MISMATCH` D0 · payload-oversize `DATAMATICS_LIMIT_EXCEEDED` D1 · payload-twin-ids `MALFORMED_DATAMATICS` D1 · unresolved-node `UNRESOLVED_OBJECT` D4 · resolution-limited `RESOLUTION_REQUIRED` **P0** (the codes in the first six are what the existing igx/igdm path raises, taken from it as the oracle) |
| verify · ok (1) | 1 | igdc-wellformed-not-verified (passes C0–C3 although its label is not in the payload) |
| verify · reject · `MALFORMED_CONSUMPTION` · C0 (4) | 4 | igdc-noncanonical, igdc-cr, igdc-bom, igdc-not-utf8 |
| verify · reject · `DATAMATICS_LIMIT_EXCEEDED` · C0 / C1 (2) | 2 | igdc-oversize (C0, byte budget before parsing) · igdc-row-budget (C1) |
| verify · reject · `MALFORMED_CONSUMPTION` · C1 (28) | 28 | unexpected-block, missing-block, duplicate-block, meta-extra-row, summary-row, typed-column, computed-column, reference-cell, **duplicate-column-igdc / -layout / -nodes / -edges / -groups / -members**, unexpected-column, missing-column, bare-boolean, directed-bare-boolean, closed-outside-vocab, x-in-closed-column, x-token-malformed, closed-and-x-both, wrong-spec, wrong-address-scheme, bad-hex, bad-profile, lod-out-of-range, magnitude-out-of-range (each prefixed `igdc-`) |
| verify · reject · `INVALID_ADDRESS` · C2 (14) | 14 | untagged-id, id-leading-zero, id-minus-zero, id-out-of-int64, unknown-tag, id-empty-int, bad-node-type, undirected-noncanonical, simple-ordinal-1, ordinal-leading-zero, duplicate-node-row, duplicate-edge-row, duplicate-member, duplicate-group |
| verify · reject · `TWIN_IDS` · C2 (1) | 1 | igdc-twin-ids |
| verify · reject · C3 (4) | 4 | `UNRESOLVED_REFERENCE`: igdc-unknown-parent, igdc-member-unknown-group · `GROUP_CYCLE`: igdc-group-cycle · `DATAMATICS_LIMIT_EXCEEDED`: igdc-group-depth |
| derivation · reject · `DERIVATION_MISMATCH` · C4 (6) | 6 | igdc-derivation-mismatch, igdc-payload-digest-mismatch, **igdc-directed-fact-wrong**, **igdc-multigraph-fact-wrong**, igdc-row-dropped, igdc-row-added |

Totals: consume 26, verify 54, derivation 6 = **86**; ok 20, reject 66. Address 142 + consumption 86 = **228 rows, all executed**. A TypeScript or other port implements C0–C3 against the same files (§7); C4 is Python-only until a verified port exists.

## 6. Boundary rules (normative)

1. An IGDC/1 document contains **hints and addresses only**. It has no verdict, admission, receipt or verifier field and never will (those are IGAR/1's). A consumer MUST NOT place any such status inside a hash-bearing IGS/1 scene.
2. Appearance never appears: no colour, font, size, coordinate, image or CSS/SVG fragment (IGDM/1 §1.3 carries over).
3. IGDC/1 never feeds back into IGDM/1, IGPV/1, IGX/1 or Core. It is a read-only view.
4. IGDC/1 hint presence is not truth: a verified hint set proves the hints are well-formed and point at real objects (`19` §0.1), nothing more.
5. IGDC/1 carries what Ext verified; it does **not** widen what the Visualize IGS/1 adapter accepts. The adapter rejects multigraph targets and `isonl-v1` rather than silently downgrading them.

## 7. Consumer qualification (what "a consumer reads IGDC/1 correctly" means)

IGDC/1 is Python-verified. No TypeScript (or any other) ISONCS verifier is claimed to exist; none may be assumed. A consumer chooses one of two routes and states which:

- **Route A — preferred first integration (no ISON parsing in the browser).** Ext emits and checks IGDC/1 (and IGAR/1) during a controlled build in Python (C0–C4). The consumer verifies the pinned artifact digests and consumes a **typed representation generated from the verified bytes** at build time. That representation is qualified by comparing it, row for row and type for type, with the `vectors/igdc1` hint files (the expected hint file is the oracle for every `consume · ok` row). The browser never decides canonicality.
- **Route B — a consumer that parses the ISON itself.** Its reader must be qualified against **every** `verify` row, every `consume · ok` row (its parse of the expected hint file compared with the stated values) and every address row, including the hazards ISON readers are known for: integers above 2^53 (`int64-hint-values`, `int64-extremes`), digit-like strings (`string-ids-digit-like-and-unicode`, `id-types-distinct`), quoted tokens versus bare booleans, a leading byte-order mark, CR, repeated column declarations, summary rows, typed declarations and reference cells (the C0/C1 rows), and UTF-16 versus UTF-8 sort order (`order-utf8-not-utf16`). It must perform its own canonical-form check; a **SHA-256 match alone does not establish ISONCS canonicality** (it establishes that the bytes are the ones somebody hashed). A Route B reader that cannot re-emit canonically MUST NOT claim C0.

"IGDC/1 consumption complete" for a consumer means: its route is named, its qualification run is recorded (vector set digest, row counts, result), and — for Route B — each of C0–C3 it claims is covered by rows it passes. A passing Python suite alone does not establish it.

## 8. Owner rulings applied and remaining points

Applied from the rev 1 review: multigraph and `isonl-v1` carried (§2.1, §6.5); `_x` sibling columns (§2.2); writer order separate from semantic order with the comparator exposed (§1.3); `target_directed` / `target_multigraph` retained and sourced from the verified target (§2.1, §3); generic `s:` syntax with source acceptance established by the probe (§1.7); documented byte budget before parsing (§4).

Owner ruling 2026-11-20: reuse of IGDM/1's private helpers inside this package is approved **as internal use with compatibility restrictions** — they are not a promised API, `tests/test_igdc_compat.py` pins the exact names, signatures and behaviour IGDC/1 relies on so an IGDM edit fails loudly, and no frozen IGDM/1 behaviour changes. **Scope of the strict reader:** `strict_ison` serves only the new contract schemas (IGDC/1, IGAR/1, verifier profile, policy file). Repeated columns, summary rows, typed declarations and reference cells may be legitimate in other ISON uses; refusing them is a property of these schemas, not a redefinition of canonical ISON, and none of `igx`, `igpv`, `igdm`, `igp` imports it (pinned by the same test file). Remaining for the owner at freeze — none that blocks the contract text. The decision above, for the record: C3 reuses IGDM/1's `check_references` and C1 reuses IGDM/1's field rules by **importing its private helpers** (`igdm.payload._common_hints`, `_vocab`, `_untok`, `check_references`) instead of copying them, so the vocabularies cannot drift; nothing in `igdm` changes. If a public seam is preferred, that is an IGDM/1 edit and therefore a separate owner decision.

## 9. Repository (planned; implementation waits for freeze)

```text
isongraph-ext/src/isongraph_ext/strict_ison.py                     shared strict reader (also used by IGAR/1)
isongraph-ext/src/isongraph_ext/igdc/{__init__, errors, address, hints, derive, verify, __main__}.py
vectors/igs-addr/, vectors/igdc1/, scripts/make_vectors_igdc.py
isongraph-ext/tests/test_strict_ison.py, test_igdc_probe.py, test_igdc_address.py, test_igdc_hints.py, test_igdc_derive.py, test_vectors_igdc.py
docs/blueprint/plans/2026-11-17-ext2-ext3-igdc1.md
```

`igx` never imports `igdc`; `igdc` imports `igdm`, `igpv` (addressing, resolution), `igx` (binding, digest) and `strict_ison`. The frozen `DEFAULT_REGISTRY` is unchanged: IGDC/1 is **not a capability** and never appears in a binding's `table.capabilities` (it is derived, not bound).

# IGAR/1 — Admission Receipt: canonical receipt, verifier profile and trusted admission boundary

Status: **DRAFT rev 2 FOR OWNER FREEZE REVIEW (2026-11-20)** — corrects rev 1 after the owner's rev 1 review (architecture and ISON wire choices approved; freeze held). · Serves requirement EXT-1 of `24-EXT-REQUIREMENTS-FOR-VIZ.md` (owner GO 2026-11-17: the receipt route, not a TypeScript verifier, for the first integration). Wraps the **existing** Python verification path — `igx.verify` (`17` §4, V0–V5), `igdm.verify` (`19` §3.1, D0–D4) and `igx.admit` (`17` §4.2, A1–A3) — without changing any of them. Pairs with `26-IGDC1-DESIGN.md` rev 2. Changes nothing in IGX/1, IGPV/1, IGDM/1, IGP/1, Semantic/2, IGS/1 or IGL/1. **No runtime code exists for this spec in the repository**; every example and vector count below was produced and run against the pinned runtime (ison-py 1.2.0, ison-graph 1.4.1) by scripts kept outside the repository. Changing §1–§6 after implementation ships is a new spec version (`IGAR/2`), never an edit.

## Rev 2 change log (what changed since rev 1, and why)

| # | Owner finding | Change | Where |
|---|---|---|---|
| **F1** | A policy match is not trusted admission: `check(receipt, trust=policy)` could succeed without any byte, binding, hint document or provenance | The one operation was split into five that each claim only what they check: `inspect_receipt` (R0–R2, no inputs), `check_subject` (R3, **every** subject input required), `qualify_policy` (R4, *claims nothing about trust*), `DeliveryPins` (R5, controlled-channel digest pin) and `authorize_hints` — the **only** operation that authorizes use of hints — which establishes pinned **and** bound (target, binding, payload **and the hint document held**) **and** policy-fit **and** passed, together, with all inputs required keywords. An omitted input is a `TypeError`, never a skipped check; nothing unpinned is ever parsed; a rejection receipt can never be authorized. `RECEIPT_NOT_TRUSTED` is renamed `RECEIPT_POLICY_UNSATISFIED` | §3, §4 |
| **F2** | Receipt reproducibility omits verifier configuration | New **verifier profile** (`IGAR-PROFILE/1`): a canonical ISON document carrying every normative input of a run — limits, capability registry, admission policy and every baseline field verification reads — named in each receipt by `profile_sha256`. `issue()` takes a profile and nothing else (no loose limits/baselines/registry/policy arguments). Recompute (now **R6**) runs under the profile the receipt names; an absent or different profile, another verifier version or another runtime is `RECOMPUTE_UNAVAILABLE` — *not* a verdict on the receipt; only `RECEIPT_RECOMPUTE_MISMATCH` after every precondition holds says the receipt is not what the verifier computes. `TrustPolicy` gains a required `profiles` dimension | §2.1, §2.4, §3 |
| **F3** | Reject repeated column declarations and unconsumed rows | Shared strict reader (`strict_ison`, also used by IGDC/1) for receipts, profiles and policy files: byte budget before parsing, canonical form, exact block set, **no repeated column, no summary row, no typed/computed declaration, no reference cell**, scalar cells only. Adversarial fixtures for every column of every block | §3 R0/R1, §7 |
| **F4** | Browser-consumer qualification must be explicit | New §8: two routes, preferred first integration = Python build + typed representation; a SHA-256 match does not establish ISONCS canonicality; rev 1's claim that R0–R4 "need no Python" is withdrawn as a *fact* and kept as a *goal* | §8 |
| budget | Documented byte budget before parsing | Receipt, profile and policy readers use IGDM/1 `Limits.max_payload_bytes` (default 64 MiB) before decoding; row budget `max_rows_per_table`; `RECEIPT_LIMIT_EXCEEDED` | §3 |
| plan | IGAR vector dispatch ambiguous | Vectors dispatch on explicit `op` (`issue inspect subject policy authorize recompute profile policyfile`); **122 rows**, counts pinned | §7 |
| rulings | Owner decisions on rev 1 choices | `table.checks` omitted; `detail` excluded from receipt bytes; trust-policy file is canonical ISON with its complete format in §4.3 and the implementation documentation; `igdc_spec` always recorded; Python reference is the only issuer; rejection receipts never positive | §2, §4, §9 |

Unchanged from rev 1: the ISON wire format and digest rule, the first-failure record and the §2.2 status table, the three-status layering, the build-time vendoring channel, the boundary rules.

## 0. What IGAR/1 is — and is not

A **receipt**: a canonical ISON record that states, for exact input bytes, what a named verifier computed — the inputs' identities, the verifier, the verification profile and the pinned Core baseline it ran under, the structured result of schema validation, verification and admission policy, and (optionally) the digest of the IGDC/1 hint set derived from them.

It is **evidence of what a verifier computed**. It is not a proof that a trusted verifier computed it.

> **A digest does not prove that a trusted verifier issued a receipt.** IGAR/1 is unsigned. Anyone who can write bytes can write a receipt that says `verified`. A consumer may rely on a receipt only when it arrives through a **trusted delivery boundary** (§4); the receipt's own content cannot establish that. Without such a boundary a self-declared `verified` is **not** verified evidence.

IGAR/1 deliberately has no signature, timestamp, nonce or clock field. Determinism is the point: identical inputs, identical verifier and identical profile give identical bytes, so a Python party can *re-derive* a receipt (§3, R6) and everyone else can *pin* its digest (§4). Signing, if ever wanted, is a later separately versioned extension and sits outside this one (`17` §1.1 takes the same position for bindings).

### 0.1 Vocabulary (kept apart on purpose)

| term | established by | says | does **not** say |
|---|---|---|---|
| **well-formed** | `inspect_receipt` (R0–R2) | the receipt is a canonical, consistent *claim* | that it is true, bound or delivered by anyone |
| **bound** | `check_subject` (R3) | the claim is about exactly the target, binding, payload and hint document the caller holds | who made it |
| **policy-fit** | `qualify_policy` (R4) | the claimed verifier, profile, baseline and posture are acceptable to a policy | anything about provenance or bytes; a forged receipt can be policy-fit |
| **pinned** | `DeliveryPins` (R5) | these exact receipt bytes arrived through the consumer's controlled, digest-pinned channel | that the claim is true (only that the controlled build said it) |
| **reproduced** | `recompute` (R6, Python only) | a Python verifier under the named profile computes exactly these bytes | trust in the party that ran it |
| **authorized** | `authorize_hints` | pinned **and** bound **and** policy-fit **and** passed, together, for the hints held | anything beyond this receipt, these bytes, this policy |

A **rejection receipt** is *delivered evidence of rejection*: it can be well-formed, bound and pinned, and it can **never** be authorized (R4 fails on `verification` under every policy, and a receipt that names no hint document cannot authorize one). Authenticity of a rejection is not approval.

## 1. Three statuses, kept apart

| group | question | fields in `meta.result` |
|---|---|---|
| **schema validation** | is each input well-formed? | `binding_schema`, `payload_schema` |
| **verifier result** | did the verifier's checks over exact bytes, baseline and target succeed? | `verification` |
| **admission policy** | given verification, may this runtime use the binding now? | `admission` (and `meta.admission`) |

plus `consumption` (does an IGDC/1 hint set derived in the same run accompany the receipt?). These are separate fields with separate vocabularies; none can be inferred from another except by the fixed table in §2.2. **None of them belongs in a hash-bearing IGS/1 scene** (§6).

## 2. Wire format

One document `<graph>.igar.ison`, bytes **exactly** ison-py's canonical writer output (`17` §2.1 applies verbatim): UTF-8, LF, no trailing newline, blocks by `kind.name`, fields by name, rows by every column with nulls last. Any other byte sequence is not an IGAR/1 receipt (`MALFORMED_RECEIPT`, `canonical_form`). **`receipt_sha256 = sha256(file bytes)` is external**: it appears in no field of the receipt, so nothing is excluded from hashing and there is one digest with one meaning. Exactly these blocks, each **exactly once**: `meta.admission`, `meta.consumption`, `meta.failure`, `meta.igar`, `meta.result`, `meta.subject`, `meta.verifier`, `table.reasons`, `table.unrecognized`; each block declares exactly the columns of §2.1, each once. Any other block, duplicate, missing block, repeated or extra column, summary row, typed column or reference cell is `MALFORMED_RECEIPT` (R1). (A field named like a digest of the receipt itself is an extra field: rejected.) The human-readable `detail` of a failure is **not** recorded: it is prose outside the contract.

### 2.1 Blocks

**`meta.igar`** — one row: `receipt_spec = IGAR/1`.

**`meta.subject`** — one row; the **exact identities** the receipt is about. Each is `sha256` of the **raw bytes as supplied** (no normalisation), computed even when the input is malformed, so a rejection is still bound to what was rejected:

| field | meaning |
|---|---|
| `target_artifact_sha256` | the target graph bytes |
| `binding_sha256` | the IGX/1 binding bytes (`= binding_digest`, `17` §2.1) |
| `igdm_payload_sha256` | the IGDM/1 payload bytes |
| `igdc_sha256` | the IGDC/1 hint-set bytes derived in the same run (`26`), or `null` |

**`meta.verifier`** — one row; the verifier identity, the profile and the baseline it ran under:

| field | meaning |
|---|---|
| `verifier` | `isongraph-ext` |
| `verifier_version` | the Ext package version |
| `igx_spec`, `igdm_spec`, `igdc_spec` | `IGX/1`, `IGDM/1`, `IGDC/1` (the specifications implemented; `igdc_spec` is **always** recorded, also when no hint set was requested) |
| `profile_sha256` | 64 lowercase hex, **never null**: `sha256` of the verifier profile document (§2.4) the run used |
| `core_commit` | the baseline `core_commit` the **binding pins** (`17` §2), or `null` if the binding could not be parsed |
| `runtime_ison_graph`, `runtime_ison_py` | the installed distribution versions that did the work (the exact pins, `17` §3) |
| `semantic_verification` | `full` / `limited` (`17` §4 V0) when verification passed, else `null` |
| `object_resolution` | `full` / `skipped` (`19` §3.1 D4) when verification passed, else `null` |

**`meta.result`** — one row; the layered statuses:

| field | domain |
|---|---|
| `binding_schema` | `valid` · `invalid` · `not_evaluated` |
| `payload_schema` | `valid` · `invalid` · `not_evaluated` |
| `verification` | `verified` · `rejected` · `not_evaluated` |
| `admission` | `admitted` · `denied` · `not_evaluated` |
| `consumption` | `derived` · `failed` · `absent` |

**`meta.failure`** — one row, all fields `null` when nothing failed: `check` (`V0`…`V5`, `D0`…`D4`: the step of the **first** failure, first failure wins), `code` and `field` (the `IGXError`/`IGDMError` `code` and `field`). There is no `table.checks` pass/not-run ledger: it would claim `pass` for steps that never ran.

**`meta.admission`** — one row: `code` (`STALE_BINDING` / `IDENTITY_CLAIM_INADMISSIBLE`, or `null` if admitted or not evaluated), `step` (`A1`/`A2`/`null`), `receipt_posture` (`OK`/`CORE_LOSSY`/`CORE_BLOCKING_DIVERGENCE`/`INADMISSIBLE`, or `null` if not evaluated). Admission is IGX/1's decision, reported unchanged (`19` §3.2).

**`meta.consumption`** — one row: `code`, `step`, `field`; all `null` unless `consumption = failed` (then the IGDC/1 error that ended derivation, `26` §4).

**`table.reasons`** — the admission `reasons` tokens (`17` §4.2), one per row; empty when none.

**`table.unrecognized`** — one row per `unrecognized_roles` entry (`19` §4, e.g. `nodes.role:x-betterify-risk`); empty when none. Preserved and reported, never interpreted.

### 2.2 The status table (normative, recomputable)

`meta.failure.check` determines the schema and verification statuses:

| `failure.check` | `binding_schema` | `payload_schema` | `verification` |
|---|---|---|---|
| *(none)* | valid | valid | verified |
| `V1` | invalid | not_evaluated | not_evaluated |
| `D1` (shape, and the budget preflight `19` §3.1 reports as `D1`) | valid | invalid | not_evaluated |
| `V0`, `V2`, `V3`, `V4`, `V5`, `D0` | valid | not_evaluated | rejected |
| `D2`, `D3`, `D4` | valid | valid | rejected |

`binding_schema` is `valid` whenever the binding parsed (the parse is IGX/1 V1 and always precedes everything else), so `V1` is the only way it becomes `invalid`. `admission` is `not_evaluated` unless `verification = verified`; then it is `admitted` iff `meta.admission.code` is `null`, else `denied`. `consumption` is `derived` iff `igdc_sha256` is non-null; `failed` iff `meta.consumption.code` is non-null (and `igdc_sha256` is null); otherwise `absent` — no hint set accompanies this receipt, whether none was requested or verification did not reach `verified`. A receipt cannot tell those two apart and does not try to.

### 2.3 Examples (byte-exact: vector files; `verifier_version` is injected as `vectors`)

`vectors/igar1/receipts/ok--verified-unrecognized-roles.igar.ison` — verified and admitted, two `x-` roles reported (digest `0af0ef99f32cd1a75ca4ac459bf74cee141077512e63971d5dcef0330fe23c5b`):

```text
meta.admission
code receipt_posture step
null OK null

meta.consumption
code field step
null null null

meta.failure
check code field
null null null

meta.igar
receipt_spec
IGAR/1

meta.result
admission binding_schema consumption payload_schema verification
admitted valid absent valid verified

meta.subject
binding_sha256 igdc_sha256 igdm_payload_sha256 target_artifact_sha256
e143c30845e51876972acd966270b26dbdee2ddafde4f08a9f1a18a5fed0d5de null f55491679b655d9cd943ca804a142287c724035d30b9840a3d4daeb584e585d4 2b0bd5b0e74e8e92a3e5f47f5b3b92c17ce0f9b0641714c0dc11b8e81d6e89c2

meta.verifier
core_commit igdc_spec igdm_spec igx_spec object_resolution profile_sha256 runtime_ison_graph runtime_ison_py semantic_verification verifier verifier_version
ce9d3b78afd79cbdffdd67546bcb5278dc38be70 IGDC/1 IGDM/1 IGX/1 full 437145940b1b0836d357c28ed107e4bfcee91d06f7a74480b638e681a4495b93 1.4.1 1.2.0 full isongraph-ext vectors

table.reasons
reason

table.unrecognized
entry
edges.pattern_role:x-wavy
nodes.role:x-betterify-risk
```

`ok--rejected-target-mismatch.igar.ison` (the payload names a target other than the supplied bytes): rejected at D2, admission not evaluated (digest `2b47c014d1f7aacb533b40b5255c94f1769b4b76e8a90eaf2451f3d3f455902a`). Its `meta.failure` row is `D2 TARGET_BINDING_MISMATCH meta.igdm.target_artifact_sha256`, `meta.result` is `not_evaluated valid absent valid rejected`, and `meta.verifier` carries `null` for `object_resolution` and `semantic_verification`; every other block is as above. (The writer, not this text, decides quoting: an all-digit value is emitted quoted. Never hand-write a receipt.)

### 2.4 The verifier profile (`IGAR-PROFILE/1`, normative) — finding F2

The same target, binding and payload bytes can verify, or be denied, differently under different limits, capability registries, admission policies or baseline sets. A receipt that does not say which ran cannot honestly promise reproducibility. The **verifier profile** is a canonical ISON document that carries **every normative input explicitly** (no digest-only indirection), and every receipt names it: `meta.verifier.profile_sha256 = sha256(profile bytes)`.

| block | content |
|---|---|
| `meta.profile` | `profile_spec = IGAR-PROFILE/1` |
| `meta.limits` | `max_payload_bytes`, `max_graph_bytes`, `max_rows_per_table`, `max_group_depth` (the IGDM/1 `Limits`) |
| `meta.admission_policy` | `allow_retired_baselines` (`"true"`/`"false"` token) |
| `table.accept_lossy_domains` | `domain` (reserved by IGX/1; recorded because it is part of the policy object) |
| `table.registry` | `extension`, `version` (the capability registry, e.g. `igdm 1.0.0`, `igpv 1.0.0`) |
| `table.baselines` | one row per baseline: `core_commit core_format core_version core_semantic_spec corpus_version corpus_commit corpus_digest core_runtime_dist core_runtime_dist_version canonical_writer_dist canonical_writer_dist_version retired adopted` |
| `table.baseline_receipts` | one row per `(baseline, port)`, every port present: the conformance receipt fields (`sha256 port_version posture receipt_core_commit core_format core_version corpus_commit corpus_digest corpus_version semantic_spec`) |
| `table.baseline_domains` | `baseline port tag` |
| `table.baseline_runtime` | `baseline module sha256` (the Core runtime module hashes V0 compares with the installed Core) |

The default profile of Ext 0.4.1 (`vectors/igar1/profiles/default.igar-profile.ison`, 4,110 bytes) has digest `437145940b1b0836d357c28ed107e4bfcee91d06f7a74480b638e681a4495b93`; its limits row is `268435456 64 67108864 1048576`, its registry `igdm 1.0.0` / `igpv 1.0.0`, its policy `allow_retired_baselines = "false"`, and its one baseline is `ce9d3b78afd79cbdffdd67546bcb5278dc38be70`. A reference builder and the production writer produce these bytes independently and agree.

Rules:

1. **One statement of the effective configuration.** `issue()` takes a profile (default: the installed package's `Profile.default()`, *recorded*, never implied) and no other configuration argument. A receipt can therefore never describe a run that used different settings than it names.
2. **Recompute never defaults.** R6 needs the profile document the receipt names (§3). Absent profile, a profile whose digest differs, another `verifier_version`, or other `ison-graph`/`ison-py` versions than the receipt records → `RECOMPUTE_UNAVAILABLE` (field names which). That says nothing against the receipt: a legitimate historical receipt is never labelled invalid because today's defaults differ. Only after every precondition holds does a byte difference raise `RECEIPT_RECOMPUTE_MISMATCH`. The profile carries the baselines, so a historical receipt re-runs without the original package.
3. **Consumers pin profiles.** `TrustPolicy.profiles` names the accepted `profile_sha256` values; an empty set accepts none. A receipt issued under a permissive profile (for example `allow_retired_baselines = "true"`, which turns a stale binding into `admitted`) is only as good as the consumer's acceptance of that profile digest.
4. **A profile hash is an identity, not evidence of provenance.** `profile_sha256` must equal the sha256 of the *canonical bytes of the profile actually supplied* (R6 checks it, and reading the profile re-checks canonical form); R4 qualifies it against the consumer's accepted profiles; R6 additionally needs the matching verifier version and runtime, else `RECOMPUTE_UNAVAILABLE`, never a false mismatch.
5. **A profile is data, not trust.** Reading one (`MALFORMED_PROFILE`, `RECEIPT_LIMIT_EXCEEDED`) goes through the same strict reader and byte budget as a receipt (§3).

## 3. Operations and checks (first failure wins; `IGARError.step` names it)

| step | operation | checks | needs | code |
|---|---|---|---|---|
| **R0 bytes** | `inspect_receipt` | **byte budget** `≤ Limits.max_payload_bytes` before any decoding; valid UTF-8; no byte-order mark; no CR; re-emission through the pinned writer equals the input (and the typed model re-emits the same bytes) | the receipt | `RECEIPT_LIMIT_EXCEEDED` / `MALFORMED_RECEIPT` (`canonical_form`, `document`) |
| **R1 shape** | `inspect_receipt` | the nine blocks exactly once and no others; **each declares exactly §2.1's columns, each once**; **no summary row, no typed/computed column, no reference cell**; scalar cells; meta blocks one row; row budget; `receipt_spec`, `verifier`, `*_spec` literals; 64-hex digests incl. `profile_sha256` (never null); closed vocabularies; `core_commit` 40 hex or `null`; no field is a digest of the receipt | the receipt | `MALFORMED_RECEIPT` / `RECEIPT_LIMIT_EXCEEDED` |
| **R2 consistency** | `inspect_receipt` | the §2.2 table holds (statuses match `failure.check`; `admission` and `consumption` rules; `semantic_verification`/`object_resolution` non-null iff `verification = verified`; `meta.admission` fields null unless admission evaluated; `failure.code`/`field` non-null iff `check` non-null; `reasons` empty unless admission evaluated) | the receipt | `INCONSISTENT_RECEIPT` |
| **R3 subject** | `check_subject` | `sha256(target)`, `sha256(binding)`, `sha256(payload)` equal `meta.subject`; the hint document is checked **in both directions**: a receipt that names one the caller did not supply, or a caller-supplied one the receipt does not name, is a mismatch. **Every subject input is a required keyword**; none defaults; `None` is accepted only for the hint document and only meaning "I hold none" | the exact bytes | `RECEIPT_SUBJECT_MISMATCH` |
| **R4 policy** | `qualify_policy` | the receipt **claims** an acceptable verifier, profile, baseline, runtime, admission and resolution (§4.3). Order: `verification` (a rejection receipt always fails here), `verifier`, `profile`, `core_commit`, `runtime`, `admission`, `resolution`. **This is not a trust decision** | the receipt, a policy | `RECEIPT_POLICY_UNSATISFIED` |
| **R5 delivery** | `DeliveryPins`, inside `authorize_hints` | `sha256(receipt bytes)` is in the consumer's pinned delivery set | the receipt bytes, the pins | `RECEIPT_NOT_PINNED` |
| **R6 recompute** | `recompute` (*Python reference only*) | under the named profile, the installed verifier reproduces exactly these bytes (§2.4 rule 2) | the receipt, binding, payload, target, **the profile document** | `RECOMPUTE_UNAVAILABLE` / `MALFORMED_PROFILE` / `RECEIPT_RECOMPUTE_MISMATCH` |

`authorize_hints` composes them in this order, first failure wins, **and nothing unpinned is ever parsed**: size budget → R5 → R0–R2 → R3 → R4. R6 is separate: reproduction needs Python and the profile and is how a Python party independently confirms a receipt; it is not part of authorization.

Codes: `MALFORMED_RECEIPT`, `INCONSISTENT_RECEIPT`, `RECEIPT_LIMIT_EXCEEDED`, `RECEIPT_SUBJECT_MISMATCH`, `RECEIPT_POLICY_UNSATISFIED`, `RECEIPT_NOT_PINNED`, `RECOMPUTE_UNAVAILABLE`, `RECEIPT_RECOMPUTE_MISMATCH`, `MALFORMED_PROFILE`, `MALFORMED_POLICY`, `MALFORMED_PINS`. `IGARError(code, field, detail, step)`. Issuing a receipt never raises for a rejected input — rejection **is** the content — and raises only for programmer errors (a non-bytes input).

The strict reader is specific to the new contract schemas (receipt, profile, policy file, and IGDC/1): the restrictions below are these schemas', not canonical ISON's, and no frozen package imports it. Against ison-py 1.2.0 a repeated column header parses silently (kept in the field list while the row keeps the **last** value) and the canonical writer re-emits it; `---` summary lines, `name:int`/`name:computed` declarations and `:ref` cells likewise re-emit unchanged. A short row is padded with `null` and is caught by re-emission alone. R0's re-emission check is therefore **not** the only defence: R1 states the structural rules and has an adversarial fixture for every column of every block.

## 4. The trusted admission boundary (normative) — finding F1

### 4.1 What a consumer MUST do

1. **Authorize through `authorize_hints` only.** Nothing short of all of {pinned, bound to the actual target, binding, payload **and hint document**, policy-fit, passed} is authorization. A policy match, a consistent receipt, a pinned rejection, or a bound receipt alone is not.
2. **Accept receipts only from a trusted delivery channel** (§4.5). A receipt obtained from an arbitrary client, an uploaded bundle or any channel the consumer does not control is **untrusted input**: its `verified` or `admitted` is not established, and `authorize_hints` refuses it (`RECEIPT_NOT_PINNED`) without parsing it.
3. **Check the subject against the bytes it will actually render** (R3), not against bytes named in some manifest. A receipt for different bytes proves nothing about these, and a missing input is an error, not a pass.
4. **Pin a profile and a policy** (`TrustPolicy.profiles`, `.verifiers`, `.core_commits`): the receipt names the verifier and profile that claim to have run; only the consumer decides whether they are acceptable.
5. **Not treat a missing receipt as a pass.** No authorized receipt means *unverified*; whether unverified hints are rendered at all is consumer policy outside IGAR/1, but they MUST NOT be labelled verified.
6. **Keep the three statuses out of the scene.** Verification, admission and receipt data never enter a hash-bearing IGS/1 scene or its digest.

### 4.2 The operations (Python reference, `isongraph_ext.igar`)

```python
inspect_receipt(data: bytes | str, *, limits=DEFAULT_LIMITS) -> Receipt                                          # R0-R2; asserts nothing about trust
check_subject(receipt: Receipt, *, target: bytes, binding: bytes, payload: bytes, igdc: bytes | None) -> None   # R3; every input required
qualify_policy(receipt: Receipt, policy: TrustPolicy) -> None                                                   # R4; NOT a trust decision
DeliveryPins(receipts: frozenset[str])  .of(*digests)  .from_sha256sums(text, *, names)                         # R5 data
authorize_hints(receipt: bytes, *, pins: DeliveryPins, target: bytes, binding: bytes, payload: bytes,
                igdc: bytes, policy: TrustPolicy, limits=DEFAULT_LIMITS) -> TrustedAdmission                    # the ONLY authorization
recompute(receipt, binding, payload, target, *, profile: bytes | None, verifier_version: str | None = None) -> None   # R6
issue(binding, payload, target, *, igdc: bool = False, profile: Profile | None = None, verifier_version: str | None = None) -> Receipt
```

`TrustedAdmission` is an **in-process value issued only by `authorize_hints`**; calling its constructor yourself raises `TypeError` (pinned by `test_trusted_admission_cannot_be_constructed_directly`). This is a programming guarantee for controlled build-time use, not authentication and not isolation against malicious code in the same process. It carries the receipt, target, binding, payload, hint and profile digests plus verifier, version and baseline; it has no serialization and is not a file format. (Same-process code can forge any Python object: the guard is against accident.) There is no partial success: every input of `authorize_hints` is a required keyword, `None` for any of them is a `TypeError`, and `igdc` must be the hint document actually held — a receipt that names none cannot authorize one.

### 4.3 `TrustPolicy`

```python
@dataclass(frozen=True)
class TrustPolicy:
    verifiers: frozenset[tuple[str, str]]       # accepted (verifier, verifier_version); empty accepts none
    core_commits: frozenset[str]                # accepted baseline core_commit values; empty accepts none
    profiles: frozenset[str]                    # accepted verifier-profile digests (§2.4); empty accepts none
    runtime: frozenset[tuple[str, str]] = frozenset()   # accepted (runtime_ison_graph, runtime_ison_py); empty = do not constrain
    require_admission: bool = True              # admission must be "admitted"
    require_full_resolution: bool = True        # semantic_verification and object_resolution must be "full"
```

The policy has **no default that accepts anything**: constructing one requires naming verifiers, baselines and profiles. R4's order and field names are in §3.

**Policy file** (`--trust-policy`; complete format, also in `docs/igar-policy-format.md` of the implementation): a canonical ISON document read with the same strict reader and budget as a receipt (`MALFORMED_POLICY`, step R4). Blocks, each once: `meta.policy` (`policy_spec = IGAR-POLICY/1`, `require_admission`, `require_full_resolution`: `"true"`/`"false"` tokens), `table.verifiers` (`verifier verifier_version`), `table.core_commits` (`core_commit`, 40 hex), `table.profiles` (`profile_sha256`, 64 hex), `table.runtime` (`runtime_ison_graph runtime_ison_py`). An empty table is legal and accepts nothing; a duplicate row, a repeated column, a bad hex digit, a bare boolean, an unexpected block or a summary row is refused. Example (the vector `policies/accept.policy.ison`):

```text
meta.policy
policy_spec require_admission require_full_resolution
IGAR-POLICY/1 "true" "true"

table.core_commits
core_commit
ce9d3b78afd79cbdffdd67546bcb5278dc38be70

table.profiles
profile_sha256
437145940b1b0836d357c28ed107e4bfcee91d06f7a74480b638e681a4495b93

table.runtime
runtime_ison_graph runtime_ison_py

table.verifiers
verifier verifier_version
isongraph-ext vectors
```

### 4.4 `DeliveryPins` (R5)

The consumer's own statement of which receipt files its controlled channel delivers: lowercase `sha256` digests, for example read from the consumer's vendoring pin file (`from_sha256sums(text, *, names)` reads `sha256sum` lines and pins **only** the named files; every name must be present exactly once). IGAR/1 cannot know **how the pin file itself is protected** — that is the consumer's boundary (§4.5). A pin set an attacker can edit pins nothing.

### 4.5 The first-integration channel

For the Visualize V1b integration the trusted channel is **build-time vendoring pinned by the consumer's own digest**: Ext (an Ext release tagged and pinned by digest) is run by the build or release process the consumer controls; the resulting `*.igar.ison` and `*.igdc.ison` are stored with the artifacts they describe; the consumer's own pin file (Visualize's `VENDOR.sha256`) pins the **receipt digest**. Trust then derives from the pin and the controlled build, **not from the receipt's contents**. Receipts that arrive at run time from a user, a network peer or an upload are outside this channel and are untrusted (§4.1 rule 2). A deployment that wants run-time receipts needs its own authenticated channel (for example a service the consumer operates and authenticates); defining that is outside IGAR/1. Signatures would be a later extension and do not change this boundary.

### 4.6 Threats this design addresses, and those it does not

| threat | handled by |
|---|---|
| forged receipt claiming `verified`, written to satisfy the policy for the real bytes | **not** by the receipt or the policy: by R5 (it is not in the pinned set, so it is refused before it is parsed) — vector `reject/authorize-unpinned-but-policy-fit` |
| receipt replayed against different bytes | R3, all four inputs, both directions for the hint document |
| receipt and payload swapped as a pair | the consumer's pin on the digests (§4.4); R3 alone cannot detect a consistent forged pair |
| caller omits an input so a check is skipped | every input of `check_subject` and `authorize_hints` is a required keyword; `None` is a `TypeError` |
| receipt from an outdated or unwanted verifier | R4 (`verifiers`, `core_commits`, `runtime`) |
| receipt issued under a permissive or different configuration | `profile_sha256` + `TrustPolicy.profiles` (R4) |
| a legitimate historical receipt "failing" because today's defaults differ | R6 never defaults the profile; absence/difference is `RECOMPUTE_UNAVAILABLE`, not invalid |
| receipt for a limited (unverifiable) run | `require_full_resolution` |
| pinned rejection receipt used as approval | R4 `verification`; and it names no hint document (R3) |
| oversize or malformed input exhausting the reader | byte budget before parsing; nothing unpinned is parsed |
| verdict laundering into a scene | §4.1 rule 6 and `26` §6 |
| freshness / revocation | **out of scope**: no timestamps by design; a consumer revokes by changing its pin or policy |
| the pin file itself being edited | **out of scope**: the consumer's repository controls |

## 5. Runtime API and CLI (`isongraph_ext.igar`, Python 3.12; planned)

The operations are §4.2. `issue` takes **bytes** (what the verifier hashes), runs `ExtensionBinding.from_ison`, `igdm.verify` and `igx.admit` under the profile, and when `igdc=True` `igdc.consume`; maps the outcome by §2.2 and never lets a verification exception escape. `verifier_version` defaults to `isongraph_ext.__version__`; tests and vectors inject a fixed value so receipt vectors do not change on every release (the vector manifest records the injected value). **Python reference only** issues IGAR/1 receipts; a receipt from any other producer is unqualified (`17` §1.1).

CLI (`python -m isongraph_ext.igar`): `issue <graph> <binding> <payload> [--profile f] [--igdc <out>]` → receipt on stdout (default profile if `--profile` is absent; the profile digest is in the receipt) · `inspect <receipt>` · `subject <receipt> --target f --binding f --payload f [--igdc f]` (all required) · `policy <receipt> --trust-policy f` · `authorize <receipt> --pins f --target f --binding f --payload f --igdc f --trust-policy f` (all required; prints the admitted digests, exit 0) · `recompute <receipt> <graph> <binding> <payload> --profile f` (the profile is required). Exit 0 / 1 (`meta.error`) / 2 (`RECEIPT_POLICY_UNSATISFIED`, `RECEIPT_NOT_PINNED`, `RECEIPT_SUBJECT_MISMATCH`: refused) / 64 usage; streams UTF-8, LF, as `19` §4. Inputs are read within byte budgets (budget + 1 bytes at most).

## 6. Boundary rules (normative)

1. A receipt records **what a verifier computed over exact bytes under a named profile**; it never asserts that hints are good or true (`19` §0.1) and never changes IGX/1 admission semantics.
2. IGAR/1 and its statuses are **outside IGS/1**: no field of a receipt is a scene field, and no scene field is derived from a receipt's status.
3. The three status groups stay distinct in storage, in code and in any consumer UI: schema validity, verifier result, admission policy.
4. IGAR/1 introduces no Datamatics, provenance or identity semantics; address typing is `26` §1.
5. Receipts never feed back into IGX/1, IGPV/1, IGDM/1 or Core.
6. `authorize_hints` is the only authorization; a `TrustedAdmission` is never persisted or transmitted by this package.

## 7. Vectors — `vectors/igar1/` (complete inventory)

Independence rule (as `26` §5): expected receipts and profiles are **not** produced by the production code. `scripts/make_vectors_igar.py` builds inputs through the existing public API and writes each expected `*.igar.ison` and `*.igar-profile.ison` with separate reference builders inside the script that import only `ison_parser` plus the existing `igx`/`igdm` verification entry points as *oracles of the verdict* (the verdict comes from `verify`/`admit`; the document shape comes from the reference builder). One row pins the digest of an `igdc1` hint file written independently by the IGDC generator. Inputs are byte copies of frozen `vectors/igdm1` files. Every file is pinned in `manifest.ison` and `SHA256SUMS` (133 files). **Every row is normative and executed; the runner fails on an unknown `op`, each `reject` row must raise exactly its `(code, step)`, and per-`(op, expect)` counts are pinned.**

`manifest.ison` → `table.vectors`: `id op binding payload target igdc receipt profile policy expect code step detail`. `op` selects the operation: `issue` (inputs + profile → the expected receipt **byte for byte**, which must also pass R0–R2, R3 and R6), `inspect` (R0–R2), `subject` (R3), `policy` (R4), `authorize` (R5 + R0–R4 together), `recompute` (R6), `profile` (`Profile.from_ison`), `policyfile` (`TrustPolicy.from_ison`). `detail` carries `verifier_version=<v>`, `igdc`, `limits:<name>=<int>`, `pins:receipt|other|empty`.

| op · expect · code · step | rows | ids (prefix `ok/` or `reject/` omitted) |
|---|---|---|
| issue · ok | 14 | verified-admitted, verified-unrecognized-roles, verified-admission-denied-stale (retired baseline whose Core runtime is installed), verified-limited-resolution (`limited`/`skipped`), verified-consumer-lossy (`CORE_LOSSY`), rejected-target-mismatch (D2), rejected-binding-malformed (V1, `core_commit` null), rejected-payload-shape (D1), rejected-payload-oversize (D1 under a 16-byte profile), rejected-unresolved-object (D4), rejected-baseline-unknown (V2), with-igdc, igdc-resolution-required (`consumption = failed`, `RESOLUTION_REQUIRED`, P0), **profile-non-default** (same inputs as verified-admitted, another profile, a different receipt) |
| inspect · ok | 5 | inspect-verified-admitted, -rejected-target-mismatch, -verified-admission-denied-stale, -with-igdc, -igdc-resolution-required |
| inspect · reject · `MALFORMED_RECEIPT` · R0 | 4 | receipt-noncanonical, -cr, -bom, -not-utf8 |
| inspect · reject · `RECEIPT_LIMIT_EXCEEDED` · R0 / R1 | 2 | receipt-oversize (budget before parsing, R0) · receipt-row-budget (R1) |
| inspect · reject · `MALFORMED_RECEIPT` · R1 | 24 | receipt-unexpected-block, -missing-block, -duplicate-block, -extra-field, -embedded-digest-field, -bad-hex, -profile-null, -profile-bad-hex, -unknown-spec, -status-outside-vocabulary, **-summary-row, -typed-column, -computed-column, -reference-cell, -meta-extra-row, -duplicate-column-{meta-admission, meta-consumption, meta-failure, meta-igar, meta-result, meta-subject, meta-verifier, table-reasons, table-unrecognized}** (one per block) |
| inspect · reject · `INCONSISTENT_RECEIPT` · R2 | 8 | receipt-verified-but-failure-set, -rejected-but-failure-null, -status-contradicts-check, -admitted-without-verification, -admission-fields-without-admission, -consumption-contradicts-digest, -limited-without-flags, -core-commit-null-without-v1 |
| subject · ok | 2 | subject-exact, subject-exact-with-igdc |
| subject · reject · `RECEIPT_SUBJECT_MISMATCH` · R3 | 6 | subject-target-differs, -binding-differs, -payload-differs, -igdc-differs, -igdc-unexpected (a hint document supplied, none named), -igdc-missing (one named, none held) |
| policy · ok | 1 | policy-match (and a policy match says nothing about provenance) |
| policy · reject · `RECEIPT_POLICY_UNSATISFIED` · R4 | 8 | policy-receipt-rejected (**a rejection receipt under a permissive policy**), -verifier-not-allowed, -profile-not-accepted, -core-commit-not-allowed, -runtime-not-allowed, -admission-required, -full-resolution-required, -empty-policy |
| authorize · ok | 1 | authorize-pinned-bound-fit |
| authorize · reject · `RECEIPT_NOT_PINNED` · R5 | 3 | **authorize-unpinned-but-policy-fit** (finding F1's scenario), -unpinned-empty-pins, -unpinned-garbage-never-parsed (R5 fires, not R0) |
| authorize · reject · R0 / R3 / R4 | 7 | `RECEIPT_LIMIT_EXCEEDED`: authorize-oversize · `RECEIPT_SUBJECT_MISMATCH`: authorize-subject-target-differs, -subject-igdc-differs, -receipt-names-no-igdc, -pinned-rejection-receipt · `RECEIPT_POLICY_UNSATISFIED`: authorize-policy-verifier, -policy-profile |
| recompute · ok | 3 | recompute-default-profile, recompute-non-default-profile (a historical receipt under the profile it names), recompute-with-igdc |
| recompute · reject · `RECOMPUTE_UNAVAILABLE` · R6 | 4 | recompute-profile-absent, -profile-differs, **-historical-under-current-defaults**, -verifier-version |
| recompute · reject · `RECEIPT_RECOMPUTE_MISMATCH` / `MALFORMED_PROFILE` · R6 | 3 | recompute-flipped-verdict, -wrong-baseline-field · recompute-malformed-profile |
| profile · ok | 3 | profile-default, -all-baselines, -retired-installed |
| profile · reject · `MALFORMED_PROFILE` · R6 | 13 | profile-wrong-spec, -negative-limit, -bare-boolean-policy, -duplicate-baseline, -receipt-for-unknown-baseline, -unknown-port, -missing-port-receipt, -bad-receipt-sha, -duplicate-runtime-module, -unexpected-block, -duplicate-column-limits, -summary-row, -not-utf8 |
| profile · reject · `RECEIPT_LIMIT_EXCEEDED` · R6 | 1 | profile-oversize |
| policyfile · ok | 2 | policyfile-valid, policyfile-empty-tables-accept-nothing |
| policyfile · reject · `MALFORMED_POLICY` · R4 | 8 | policyfile-wrong-spec, -bare-boolean, -unexpected-block, -duplicate-column, -bad-commit-hex, -bad-profile-hex, -summary-row, -duplicate-row |

Totals: issue 14, inspect 43, subject 8, policy 9, authorize 11, recompute 10, profile 17, policyfile 10 = **122 rows** (ok 31, reject 91).

## 8. Consumer qualification and the cross-contract acceptance gate — finding F4

IGAR/1 does not make a browser a verifier. Rev 1 said R0–R4 "need neither Python nor the Core runtime"; that is withdrawn as a *fact* and kept as a *goal*: R0 needs a conforming canonical ISON reader and writer, and nothing in this repository establishes that the current browser has one. A consumer states one route:

- **Route A — preferred first integration.** Ext runs in Python during the consumer's controlled build: `issue`, `consume` (IGDC/1), and `authorize_hints` against the consumer's pins and policy. The browser never parses ISON and never decides canonicality. It consumes a **typed representation generated at build time from the verified artifacts**, plus the pinned digests. That representation is qualified by comparing it with the expected `vectors/igdc1` hint files (`26` §7). Trust in what the browser shows is trust in the build and in the pin file (§4.5), and the integration says so.
- **Route B — a consumer that parses the artifacts itself.** Its ISON reader must be qualified against the C0–C3 and R0–R5 rows (`26` §5, §7 of this document), including the known JavaScript parser hazards: integers above 2^53, digit-like strings, bare versus quoted booleans, byte-order marks, CR, repeated column declarations, summary rows, typed declarations, reference cells, and UTF-16 versus UTF-8 ordering. It must perform its own canonical-form check: **a SHA-256 match alone does not establish ISONCS canonicality** — it establishes that the bytes are the ones somebody hashed. R6 stays Python-only.

**Acceptance gate for V1b ("browser admission complete").** All of: (1) the route is named; (2) for Route A, the build runs `authorize_hints` with the consumer's own pins and policy, with `igdc` the hint document actually shipped, and fails the build on any refusal; (3) for Route B, a qualification run over the vector sets is recorded with set digests, row counts and results; (4) no scene field carries a status (§6.2); (5) the IGS adapter rejects unsupported profiles and graph shapes rather than downgrading them. Python suite success is evidence for the Python reference only; it does not complete this gate.

## 9. Owner rulings applied and remaining blockers

Applied from the rev 1 review: `table.checks` omitted and statuses derived from the first failure (§2.1–§2.2); `detail` excluded from receipt bytes (§2); trust-policy file is canonical ISON with its complete format in §4.3 and the implementation documentation; `igdc_spec` always recorded (§2.1); Python reference only for IGAR/1 issuance (§5); a rejection receipt can be authentic evidence of rejection but never authorizes positive admission, and the terminology reflects it (§0.1); initial trusted receipts are limited to controlled build-time delivery (§4.5); F1–F4 as the change log.

**Remaining blockers before freeze** — none in the contract text that I know of. Items for the owner to confirm:

1. **Terminology.** `RECEIPT_NOT_TRUSTED` is renamed `RECEIPT_POLICY_UNSATISFIED` and R5/R6 are renumbered (delivery is R5, recompute is R6). Both renames are deliberate: R4 must not say "trusted".
2. **A profile carries the baselines in full** (about 4.1 KB for one baseline; every field V0–V5 and A1–A3 read). The alternative — a digest that "resolves" to a package version — would again make the receipt depend on installed defaults, which is finding F2's complaint. Confirm the explicit form.
3. **`TrustedAdmission` is an in-process guard, not a capability.** If a stronger isolation is wanted (a separate verifier process whose output the consumer reads), that is a deployment design outside IGAR/1.
4. **Visualize's Route (A or B) is the integration session's choice**; this spec only fixes what each route must establish (§8).

## 10. Repository (planned; implementation waits for freeze)

```text
isongraph-ext/src/isongraph_ext/igar/{__init__, errors, profile, receipt, issue, check, trust, __main__}.py
vectors/igar1/, scripts/make_vectors_igar.py
isongraph-ext/tests/test_igar_receipt.py, test_igar_strict.py, test_igar_profile.py, test_igar_issue.py, test_igar_check.py, test_igar_trust.py, test_vectors_igar.py
docs/igar-policy-format.md, docs/blueprint/plans/2026-11-17-ext1-igar1.md
```

`igx`, `igpv`, `igdm`, `igdc` never import `igar`; `igar` imports `igx`, `igdm`, `igdc` and `strict_ison`. `DEFAULT_REGISTRY` is unchanged: IGAR/1 is not a capability.

# IGX/1 — Extension Binding: Design Spec (E1)

Status: **FROZEN 2026-11-05 (rev 3)** · Implements `16-CORE-BASELINE-AND-COMPATIBILITY-CONTRACT.md` §3–§7 in the new repo `ISON-format/isongraph-ext`. Supersedes the field sketch in `03`. Nothing here touches provenance, revision, Datamatics, projection or DAG. Rev 2 applied the five spec-review corrections (artifact-level semantic eligibility; stored `source_canonical` verified; binding bytes must be canonical; verify raises / admit returns; registry injection + pinned Core runtime + receipt cross-fields). Rev 3 applies the plan-review corrections that touch the contract: historical verification against a retired baseline whose runtime is no longer installed is **limited**, never silently full (§4 V0/V4, §4.2); `admit()` binds its evidence to the binding by digest (§3); conventional SemVer caret semantics (§2); CLI usage errors exit 64 (§3). The wire format (§2) is unchanged by rev 3. Changing §1–§6 after implementation ships is a new binding spec version (`IGX/2`), never an edit.

## 0. What E1 delivers

An **independently verifiable, deterministic extension binding with honest identity claims**: given a Core graph artifact and the frozen Core baseline, produce a companion binding whose every claim a second party can re-check offline, and refuse to produce or admit a binding whose claim the receipts and the artifact do not support.

IGX/1 is the **binding protocol**, recognised by `meta.igx.binding_spec = "IGX/1"`. It is not a capability and does not register itself. The production capability registry is **empty** in E1; real capabilities (`igpv`, `igrv`, `igd`, `igdm`, `igp`, `igdag`, `igrcp`) enter it when their own specs are admitted. *Post-freeze note (2026-11-06, `18` §9): E2 admits `igpv 1.0.0` — `DEFAULT_REGISTRY = {"igpv": "1.0.0"}` replaces `EMPTY_REGISTRY` as the production default of `bind`/`verify`/`verify_and_admit` and the CLI; `EMPTY_REGISTRY` stays exported and the §5 vectors are unchanged. No other part of this spec moves.* Tests inject a registry containing `x-igx-test 1.0.0` (§3) so known-capability behaviour is exercised without touching production state.

## 1. Three identities, never merged

| Identity | Establishes | How E1 verifies it |
|---|---|---|
| **artifact** | the exact source bytes match `artifact_sha256` | re-hash the supplied bytes (V4) |
| **producer_bound** | the pinned producer's interpretation of *this artifact* is supported by its conformance evidence **and** the artifact lies inside the Semantic/2-draft domain | producer posture `FULL`, receipt verified by digest (V3), **and** `source_semantic_eligibility = eligible` (V4, §4.1) |
| **cross_port** | producer and consumer are proven compatible for the artifact's semantic domain | **reserved** — requires Semantic/2 frozen (`13` §3) and both postures admissible; always inadmissible in E1 |

`identity_claim ∈ { none, artifact, producer_bound, cross_port }`.

A `FULL` posture describes the port's behaviour against the corpus, not the semantic validity of every document it can load. The corpus itself records the gap: `values/int-beyond-int64` is `out_of_domain INTEGER_OUT_OF_INT64` yet Python loads it (`pass`). So:

```text
producer posture FULL  +  artifact loads  ≠  artifact is Semantic/2-identifiable
```

`producer_bound` therefore has two preconditions, producer trust (receipt) **and** source eligibility (artifact), and E1 admits it only when both are established. When eligibility cannot be established the honest claim is `artifact`, and `bind()` refuses the stronger one rather than downgrading silently.

`LOSSY_KNOWN` producers do **not** receive `producer_bound` in E1. Accepting a possible loss is a policy decision, not evidence that meaning survived; that admission waits for artifact-level domain classification (E7). The policy field is reserved (§3) and the negative vectors stay (§5).

### 1.1 What a verified binding does not prove

A canonical-writer match and an unsigned SHA-256 chain prove **reproducibility and consistency**: that these bytes are what the binding names, that the pinned implementation re-emits them unchanged, and that the receipts referenced are the ones the baseline holds. They prove nothing about **who** produced the artifact. `producer_port` is a caller-supplied statement that the verifier checks for *internal consistency* (the Python writer does not contradict a Python claim); it is not cryptographic producer authentication. Signatures, if ever wanted, are a later spec's business and sit outside IGX/1.

## 2. Binding wire format

One companion document `<graph>.igx.ison`. Its bytes are **exactly** ison-py's canonical writer output for the document (UTF-8, no trailing newline, §2.1); any other byte sequence is not an IGX/1 binding. The writer, not this spec, decides block order (by `kind.name`), field order (ordinal) and quoting (typed-looking strings such as `"true"` are quoted; `IGX/1`, `1.4.1`, `^1` are bare) — the example below is shown as the writer emits it. Exactly these blocks, each **exactly once** (`meta.consumer` at most once); any other block or a duplicate is `MALFORMED_BINDING` — never silently dropped.

```text
meta.core_baseline
core_commit core_conformance_receipt core_format core_semantic_spec core_vector_corpus_commit core_vector_corpus_digest core_vector_corpus_version core_version producer_core_posture producer_port producer_port_version
<40hex> <64hex> isongraph ISONGraph-Semantic/2-draft <40hex> <64hex> 1 1.4.1 FULL python 1.4.1

meta.igx
binding_spec identity_claim
IGX/1 producer_bound

meta.source
artifact_sha256 core_writer_implementation core_writer_version semantic_digest semantic_digest_algorithm serialization_profile source_canonical source_semantic_eligibility source_semantic_reason
<64hex> isongraph-python 1.4.1 null null ison-v1 "true" eligible null

table.capabilities
extension payload_sha256 requirement version_range
x-igx-test null OPTIONAL ^1
```

Optional (sorts between `meta.core_baseline` and `meta.igx`):

```text
meta.consumer
consumer_conformance_receipt consumer_core_posture consumer_port consumer_port_version
<64hex> KNOWN_DEFECT ts 1.4.1
```

Field rules:
- `serialization_profile ∈ { ison-v1, isonl-v1 }` — which loader/writer the artifact bytes belong to.
- `source_canonical` is a **string token** `∈ { "true", "unverified" }` on the wire (quoted so it never parses as a boolean). It is set by the runtime, never by the caller, and re-derived at V4; `"false"` is a *derived* value that can never appear in a valid binding (a Python-writer claim the Python writer contradicts is rejected at bind time). Cross-field rule (V1): `producer_port = python ⇒ "true"`; any other producer `⇒ "unverified"`.
- `source_semantic_eligibility ∈ { eligible, ineligible, unclassified }` and `source_semantic_reason` (null, or one of the corpus reason codes §4.1) — set by the runtime, re-derived at V4. Cross-field rule (V1): `eligible ⇒ reason null`; `ineligible ⇒ reason non-null`; `unclassified ⇒ reason null`.
- `core_writer_implementation ∈ { isongraph-python, isongraph-ts, isongraph-js, isongraph-rs, isongraph-cs, isongraph-cpp }` and must agree with `producer_port`; `core_writer_version` must equal `producer_port_version`.
- `semantic_digest` / `semantic_digest_algorithm` are `null` until Semantic/2 freezes; a non-null value is `MALFORMED_BINDING` in E1.
- `table.capabilities` may be empty (header only). `extension` is unique per table; `version_range` is one of `=X.Y.Z`, `^X[.Y[.Z]]`, `~X.Y[.Z]`, `>=X.Y.Z` with conventional SemVer meaning — `=` exact; `>=` at or above; `~X.Y[.Z]` ≥ the padded value and `< X.(Y+1).0`; `^` ≥ the padded value and below the next change of the left-most non-zero component (`^1.2.3 < 2.0.0`, `^0.1 < 0.2.0`, `^0.0.3 < 0.0.4`, `^0 < 1.0.0`); `requirement ∈ { REQUIRED, OPTIONAL }`; `payload_sha256` is `null` or 64 hex (the payload artifact's bytes — payload formats are the later specs' business).

### 2.1 Digest framing (frozen)

- `artifact_sha256 = sha256(bytes)` where `bytes` are **exactly the bytes supplied to the runtime** — a `str` is UTF-8 encoded as given, a `bytes` value is hashed as-is. No normalisation, no newline policy: the runtime hashes what it was handed and records separately (`source_canonical`) whether that is the canonical form.
- **A binding is canonical by construction.** `to_ison()` returns `dumps_canonical(document)` (no newline appended). `from_ison(text)` parses, re-emits through the same writer and **rejects** (`MALFORMED_BINDING`, field `canonical_form`) when the re-emitted text differs from the input by even one byte. Consequently `binding_digest = sha256(binding file bytes) = sha256(to_ison().encode("utf-8"))`: one digest, one meaning. There is no separate "canonical content identity"; two different byte sequences can never carry the same `binding_digest`. The binding holds no field with its own digest, so nothing is excluded from hashing.
- `core_conformance_receipt = sha256(receipt_bytes)` where `receipt_bytes` are exactly what Core's `scripts/corpus_receipt.py` prints: `dumps_canonical(receipt) + "\n"`. These are the bytes stored under `baselines/` (§6) and in the blueprint's `receipts/`.
- `payload_sha256 = sha256(payload bytes as stored)`; framing of payloads is each capability spec's responsibility.
- Hex is lowercase. Git ids are full 40-hex object ids.

## 3. Runtime API (`isongraph_ext.igx`, Python 3.12)

Dependencies are **exact pins**, not floors: `ison-graph==1.4.1`, `ison-py==1.2.0`. The reference runtime is the implementation the baseline was measured with, or it is not the reference runtime (§4 V0, §6).

```python
@dataclass(frozen=True)
class Receipt:                 # one parsed Core Conformance Receipt + the sha256 of its exact bytes
    sha256: str; port: str; port_version: str; posture: str
    core_commit, core_format, core_version, corpus_commit, corpus_digest: str; corpus_version: int; semantic_spec: str

@dataclass(frozen=True)
class Baseline:                # one per embedded core_commit
    core_format, core_version, core_commit, core_semantic_spec: str
    corpus_version: int; corpus_commit, corpus_digest: str
    receipts: Mapping[str, Receipt]           # port -> Receipt
    domains: Mapping[str, frozenset[str]]     # port -> lossy/defect domain tags (§4 A3)
    core_runtime: Mapping[str, str]           # "ison_graph/<file>.py" -> sha256 of that module's source at core_commit
    core_runtime_dist: tuple[str, str]        # ("ison-graph", "1.4.1")
    retired: bool                             # True = verifiable, not admissible for new operations

BASELINES: Mapping[str, Baseline]             # keyed by core_commit; loaded from package data
DEFAULT_BASELINE: Baseline                    # newest non-retired = ce9d3b78…

CapabilityRegistry = Mapping[str, str]        # extension -> registered version "X.Y.Z"
EMPTY_REGISTRY: CapabilityRegistry = {}       # production default in E1; tests pass {"x-igx-test": "1.0.0"}

@dataclass(frozen=True)
class Capability: extension: str; version_range: str; requirement: Literal["REQUIRED","OPTIONAL"]; payload_sha256: str | None

@dataclass(frozen=True)
class Consumer: port: str; port_version: str; posture: str; receipt_sha256: str

@dataclass(frozen=True)
class ExtensionBinding:        # the four/five blocks as typed fields
    def to_ison(self) -> str                                   # canonical writer output, no trailing newline
    @classmethod
    def from_ison(cls, text: str) -> "ExtensionBinding"        # raises IGXError(MALFORMED_BINDING); rejects non-canonical text
    @property
    def digest(self) -> str                                    # sha256(to_ison().encode("utf-8"))

class IGXError(Exception): code: str; field: str; detail: str; step: str   # step = V0..V5 (verification) or A1..A2 (bind refusal)

def bind(source: str | bytes, *, serialization_profile: str, producer_port: str, identity_claim: str,
         capabilities: Sequence[Capability] = (), consumer: Consumer | None = None,
         baseline: Baseline = DEFAULT_BASELINE, registry: CapabilityRegistry = EMPTY_REGISTRY,
         policy: AdmissionPolicy = DEFAULT_POLICY) -> ExtensionBinding
    # Derives source_canonical and source_semantic_eligibility, builds the binding from the baseline + receipt,
    # then runs verify() and admit(). A binding that fails verification raises IGXError (step V*); one whose claim
    # is inadmissible raises IGXError with the AdmissionResult's code/step (A*). bind() never returns a binding
    # it would not itself admit, and never downgrades a claim on the caller's behalf.

def verify(binding: ExtensionBinding, source: str | bytes, *, baselines: Mapping[str, Baseline] = BASELINES,
           registry: CapabilityRegistry = EMPTY_REGISTRY) -> VerificationResult
    # "Is this binding historically valid against the baseline it pins?" Retired baselines verify.
    # RAISES IGXError on the first failing step (V0..V5). Returns only on full success.

def admit(binding: ExtensionBinding, result: VerificationResult, *, policy: AdmissionPolicy = DEFAULT_POLICY) -> AdmissionResult
    # "May this runtime use it now, and is its identity claim admissible?"
    # NEVER raises for a policy denial: returns AdmissionResult(admitted=False, code=..., step=...).

def verify_and_admit(binding: ExtensionBinding, source: str | bytes, *, baselines=BASELINES, registry=EMPTY_REGISTRY,
                     policy: AdmissionPolicy = DEFAULT_POLICY) -> tuple[VerificationResult, AdmissionResult]
    # The entry point for callers that need a trustworthy decision: the result handed to admit() is the one
    # verify() just produced for this binding and these bytes. A VerificationResult constructed by hand is not evidence.

@dataclass(frozen=True)
class VerificationResult:
    binding_digest: str                                               # admit() refuses a result whose digest is not the binding's
    semantic_verification: Literal["full","limited"]                 # "limited": V4 re-derivations were not possible (§4 V0)
    source_canonical: Literal["true","false","unverified"] | None    # derived in "full"; None in "limited"
    source_semantic_eligibility: Literal["eligible","ineligible","unclassified"] | None
    source_semantic_reason: str | None
    unrecognized_optional: tuple[Capability, ...]                    # preserved and reported, never dropped
    steps_passed: tuple[str, ...]                                    # ("V0","V1","V2","V3","V4","V5"); "V4" is present in both modes

@dataclass(frozen=True)
class AdmissionResult:
    admitted: bool
    code: Literal["STALE_BINDING","IDENTITY_CLAIM_INADMISSIBLE"] | None   # None iff admitted
    step: Literal["A1","A2"] | None                                        # None iff admitted
    receipt_posture: Literal["OK","CORE_LOSSY","CORE_BLOCKING_DIVERGENCE","INADMISSIBLE"]
    reasons: tuple[str, ...]        # stable sub-reason tokens, e.g. SEMANTIC2_NOT_FROZEN, SOURCE_NOT_ELIGIBLE,
                                    # LOSSY_PRODUCER_BOUND_RESERVED, CORE_BLOCKING_DIVERGENCE, PRODUCER_POSTURE_<P>

@dataclass(frozen=True)
class AdmissionPolicy:
    accept_lossy_domains: frozenset[str] = frozenset()   # RESERVED in E1: any non-empty value is ignored for admission
                                                         # and reported in reasons as POLICY_FIELD_RESERVED
    allow_retired_baselines: bool = False
```

Failure contract, one rule per operation:

| operation | failure behaviour |
|---|---|
| `from_ison()` | raises `IGXError(MALFORMED_BINDING, step="V1")` |
| `verify()` | raises `IGXError` for invalid runtime, binding or evidence (V0–V5) |
| `admit()` | returns `AdmissionResult(admitted=False, code, step, reasons)` — a policy decision, not malformed data. The one exception: `result.binding_digest != binding.digest` raises `IGXError(VERIFICATION_RESULT_MISMATCH, step="A0")` — evidence for another binding is not a policy question |
| `verify_and_admit()` | raises as `verify()`; returns `(VerificationResult, AdmissionResult)` |
| `bind()` | raises `IGXError` carrying the verification or admission code/step; never returns an inadmissible binding |
| CLI `python -m isongraph_ext.igx verify <graph> <binding>` | prints the `VerificationResult` as ISON, exit **0**; on `IGXError` prints it as ISON, exit **1** |
| CLI `python -m isongraph_ext.igx admit <graph> <binding> [--allow-retired]` | verify first (exit 1 on `IGXError`), then prints the `AdmissionResult` as ISON; exit **0** if admitted, **2** if denied |
| CLI usage error (bad arguments, missing file) | exit **64** (`EX_USAGE`), message on stderr, nothing on stdout — never 2, so a denial is always distinguishable from a mis-typed command |

The CLI exposes no `--registry` and no `--accept-lossy` in E1: production registry is empty and the lossy policy is reserved.

## 4. Verification order (deterministic; first failure wins; `IGXError.step` names it)

| step | checks | code on failure |
|---|---|---|
| **V0 runtime** | compare the installed `ison_graph` distribution, module hashes **and the `ison-py` distribution version** (the canonical writer every canonicality verdict runs through; recorded in `MANIFEST.ison` as `canonical_writer_dist[_version]`) (after `\r\n → \n` normalisation — line endings are not implementation; the recorded values are the git blob hashes at `core_commit`, which the published `ison_graph-1.4.1` wheel reproduces byte-for-byte) with the **binding's** baseline. Match → `semantic_verification = full`. Mismatch and the baseline is **retired** → `semantic_verification = limited`: evidence (V1–V3, V4's byte check, V5) is still verified, the V4 re-derivations are skipped, and the result says so — a historical binding never becomes unverifiable, and never gets a false "fully re-verified". Mismatch and the baseline is **current** → the install is not the reference runtime | `CORE_RUNTIME_MISMATCH` |
| **V1 shape** | input bytes equal the canonical re-emission (§2.1); required blocks exactly once, `meta.consumer` ≤ 1, no other blocks; every field present with the right type; `binding_spec == "IGX/1"`; enums valid; `semantic_digest*` null; capability rows unique and well-formed; `core_writer_implementation` matches `producer_port` and `core_writer_version == producer_port_version`; `source_canonical` token allowed for the producer (§2); eligibility/reason cross-field rule (§2) | `MALFORMED_BINDING` |
| **V2 baseline pins** | `core_commit` is a known baseline (supported or retired); `core_format`, `core_version`, `core_semantic_spec` equal that baseline's | `CORE_BASELINE_UNSUPPORTED` |
| | `core_vector_corpus_version`, `_commit`, `_digest` equal that baseline's | `CORPUS_DIGEST_MISMATCH` |
| **V3 receipts** | `producer_port` ∈ six ports; baseline has that port's receipt; `core_conformance_receipt == receipt.sha256`; `producer_port_version == receipt.port_version`; `producer_core_posture == receipt.posture`; **and every cross-field inside the receipt agrees with the selected baseline**: `receipt.core_commit`, `core_format`, `core_version`, `corpus_version`, `corpus_commit`, `corpus_digest`, `semantic_spec`. Same checks for `meta.consumer` if present | `RECEIPT_REFERENCE_INVALID` |
| **V4 source** | `artifact_sha256 == sha256(supplied bytes)` | `SOURCE_BINDING_MISMATCH` |
| | *(the two derivation checks below run only in `full` mode; in `limited` mode they are skipped and the result's derived fields are `None`)* | |
| | derive canonicality: `producer_port == python` → reload via the profile's loader (`ISONGraph.from_ison`/`from_isonl`; `MultiGraph.from_ison`/`from_isonl` when the parsed document carries `meta.graph.format = ison-graph-multigraph-v1`, since the Python port writes those too), re-emit with the matching `to_ison`/`to_isonl`, and the supplied bytes must equal `emitted` or `emitted + "\n"` (Core's `save()` writes no newline, Core's corpus files end in exactly one — both are the writer's form; `artifact_sha256` still pins exactly one of them) → derived `"true"` / `"false"` (a loader exception is `"false"`); other producers → derived `"unverified"`. **Require `derived == stored source_canonical`.** A Python claim with derived `"false"` fails here (the Python writer contradicts the claim); a stored token that disagrees with the derivation fails here too (V1's token rule already removes the python/`"unverified"` and non-python/`"true"` combinations, so derived `"false"` is the reachable case) | `SOURCE_WRITER_MISMATCH` |
| | derive eligibility (§4.1) → `(eligibility, reason)`. **Require both equal the stored fields.** | `SOURCE_ELIGIBILITY_MISMATCH` |
| **V5 capabilities** | every `REQUIRED` extension is in the injected registry and its range admits the registered version; `OPTIONAL` unknowns are collected into `unrecognized_optional` | `UNSUPPORTED_CAPABILITY` |

### 4.1 Source semantic eligibility (E1 classifier, frozen with this spec)

The classifier decides whether the artifact lies inside the Semantic/2-draft domain the corpus's `semantic` column names. It is deliberately minimal: it recognises exactly the `out_of_domain` classes the corpus shows a `FULL` Python port **loading successfully**, because those are the only cases where "loads" and "identifiable" diverge. Everything the Python loader rejects never reaches a claim at all.

Run only when the pinned Python Core is present (always, in E1's reference runtime) and the artifact loads under the stated profile:

| order | condition (on the loaded graph) | result |
|---|---|---|
| 1 | the parsed document carries `meta.graph.format = ison-graph-multigraph-v1` (Core's `MULTIGRAPH_FORMAT`) | `ineligible`, `MULTIGRAPH_DOCUMENT` |
| 2 | any node id, or any integer property value, lies outside `[-2^63, 2^63-1]` | `ineligible`, `INTEGER_OUT_OF_INT64` |
| 3 | otherwise | `eligible`, `null` |

If the artifact does not load under the pinned Python Core (possible only for a non-Python producer, since a Python claim already failed V4 canonicality), the result is `unclassified`, `null`. The classifier's value domain is complete for ISON: ISON values are scalars only (integer, float, boolean, string, null, reference) — a bracketed or braced token is a string — so node ids plus node and edge property values are the whole domain; there is nothing nested to recurse into. The classifier never consults the lossy-domain tags (`binary64-inexact-int`, `integral-float-collapse`): those describe *consumer* fidelity, and the corpus marks their vectors `identifiable`. A future Semantic/2 freeze replaces this table in `IGX/2`; E1 bindings keep verifying against this one.

### 4.2 Admission (run only after a successful verification)

| step | checks | code |
|---|---|---|
| **A1 currency** | baseline not retired, or `policy.allow_retired_baselines` | `STALE_BINDING` |
| **A2 claim** | `none` → admitted. `artifact` → admitted (V4's byte check passed in either mode). `producer_bound` → admitted iff `semantic_verification == full` **and** producer posture `FULL` **and** `source_semantic_eligibility == eligible`; a `limited` result is denied with reason `SEMANTIC_REVERIFICATION_UNAVAILABLE` (the stored eligibility was not re-derived, so it is a claim, not evidence); otherwise denied with reasons: `SOURCE_NOT_ELIGIBLE:<reason>` when eligibility is `ineligible`, `SOURCE_UNCLASSIFIED` when `unclassified`, `LOSSY_PRODUCER_BOUND_RESERVED` for `LOSSY_KNOWN`, `CORE_BLOCKING_DIVERGENCE` for `KNOWN_DEFECT`, `PRODUCER_POSTURE_<P>` for `PARTIAL`/`INCONCLUSIVE`/`NONCONFORMANT`. `cross_port` → denied, reason `SEMANTIC2_NOT_FROZEN` (plus `CONSUMER_REQUIRED` if `meta.consumer` is absent) | `IDENTITY_CLAIM_INADMISSIBLE` |
| **A3 consumer** | reporting only, never a denial: if `meta.consumer` is present and the result is admitted, set `receipt_posture = CORE_BLOCKING_DIVERGENCE` when the consumer's posture is `KNOWN_DEFECT` or worse, `CORE_LOSSY` when it is `LOSSY_KNOWN`, so no caller mistakes an admitted producer-bound result for cross-port equivalence | — |

`receipt_posture` is `OK` for an admitted result with no consumer caveat, `INADMISSIBLE` for every denial.

The domain tags are stored per port in the embedded baseline (`baselines/<commit>/domains.ison`), derived from the corpus manifest + README at baseline-embedding time, not from prose at runtime: `binary64-inexact-int` (`ids/int64-extremes`, `values/int64-extreme-values`, `values/int-beyond-int64-inexact`), `integral-float-collapse` (`values/int-vs-integral-float`), defect `multigraph-document-accepted` (`structure/multigraph-document`). In E1 they feed A3 reporting only.

## 5. Conformance vectors (`vectors/igx1/`)

`manifest.ison` in the Core corpus style: `id graph binding registry expect step detail`. `registry ∈ { empty, test }` (`test` = `{"x-igx-test": "1.0.0"}`). `expect ∈ { verify_ok, reject:<CODE>, admit_ok, admit:<CODE>, admit_posture:<POSTURE> }`, several joined by `+`. `step` is the exact V/A step that must fire, so a TS runner later must agree on *where* it failed, not just *that* it failed. The Python runner (`tests/test_vectors.py`) is the reference.

| id | expect | step |
|---|---|---|
| ok/python-full-producer-bound | verify_ok + admit_ok (`OK`) | — |
| ok/python-full-artifact-claim | verify_ok + admit_ok | — |
| ok/claim-none | verify_ok + admit_ok | — |
| ok/ineligible-source-artifact-claim | graph `values/int-beyond-int64`, claim `artifact`: verify_ok (eligibility `ineligible INTEGER_OUT_OF_INT64` stored and re-derived) + admit_ok | — |
| ok/optional-unknown-preserved | verify_ok, `unrecognized_optional` has one entry, admit_ok | — |
| ok/empty-capabilities | verify_ok | — |
| ok/known-test-capability-required | registry `test`: verify_ok (`x-igx-test ^1` REQUIRED) | — |
| ok/reserialize-stable | `from_ison(to_ison(b)).to_ison() == to_ison(b)`, equal digest, and `digest == sha256(file bytes)` | — |
| ok/retired-baseline-verifies | retired test baseline whose recorded runtime hashes **differ** from the installed Core; claim `artifact`: verify_ok with `semantic_verification = limited`; admit:`STALE_BINDING`; admit_ok with `allow_retired_baselines` | A1 |
| admit/retired-limited-producer-bound | same baseline, claim `producer_bound`: verify_ok (limited); with `allow_retired_baselines` → admit:`IDENTITY_CLAIM_INADMISSIBLE`, reason `SEMANTIC_REVERIFICATION_UNAVAILABLE` | A2 |
| reject/noncanonical-binding-text | same document with a trailing newline → `MALFORMED_BINDING` field `canonical_form` | V1 |
| reject/duplicate-igx-block | `MALFORMED_BINDING` | V1 |
| reject/unexpected-block | `MALFORMED_BINDING` | V1 |
| reject/semantic-digest-set | `MALFORMED_BINDING` | V1 |
| reject/writer-port-mismatch | `MALFORMED_BINDING` | V1 |
| reject/source-canonical-token-disallowed | ts producer with `source_canonical "true"` → `MALFORMED_BINDING` | V1 |
| reject/wrong-core-commit | `CORE_BASELINE_UNSUPPORTED` | V2 |
| reject/wrong-corpus-digest | `CORPUS_DIGEST_MISMATCH` | V2 |
| reject/wrong-receipt-digest | `RECEIPT_REFERENCE_INVALID` | V3 |
| reject/posture-not-in-receipt | `RECEIPT_REFERENCE_INVALID` (binding says FULL, receipt says KNOWN_DEFECT) | V3 |
| reject/receipt-crossfield-mismatch | test baseline whose stored receipt carries a foreign `core_commit` → `RECEIPT_REFERENCE_INVALID` field `receipt.core_commit` | V3 |
| reject/wrong-artifact-sha | `SOURCE_BINDING_MISMATCH` | V4 |
| reject/python-writer-noncanonical-bytes | graph `serialization/non-canonical-order` with a Python claim → `SOURCE_WRITER_MISMATCH` | V4 |
| reject/python-claim-crlf-bytes | python claim over a CRLF-rewritten copy of `ids/positive-int` (`artifact_sha256` of those bytes, so V4's first check passes) → `SOURCE_WRITER_MISMATCH` field `source_canonical` | V4 |
| reject/eligibility-stored-mismatch | graph `values/int-beyond-int64` with stored `eligible` → `SOURCE_ELIGIBILITY_MISMATCH` | V4 |
| reject/unknown-required | registry `empty` → `UNSUPPORTED_CAPABILITY` | V5 |
| reject/required-range-excludes-registered | registry `test`, `x-igx-test =2.0.0` → `UNSUPPORTED_CAPABILITY` | V5 |
| reject/two-faults-first-wins | wrong corpus digest **and** unknown required → `CORPUS_DIGEST_MISMATCH` | V2 |
| admit/known-defect-producer-bound | verify_ok; admit:`IDENTITY_CLAIM_INADMISSIBLE`, reason `CORE_BLOCKING_DIVERGENCE` (ts producer) | A2 |
| admit/ineligible-source-producer-bound | graph `values/int-beyond-int64`, python, claim `producer_bound`: verify_ok; admit:`IDENTITY_CLAIM_INADMISSIBLE`, reason `SOURCE_NOT_ELIGIBLE:INTEGER_OUT_OF_INT64` | A2 |
| admit/multigraph-source-producer-bound | graph `structure/multigraph-document`, python: verify_ok; admit:`IDENTITY_CLAIM_INADMISSIBLE`, reason `SOURCE_NOT_ELIGIBLE:MULTIGRAPH_DOCUMENT` | A2 |
| admit/cross-port-reserved | verify_ok; admit:`IDENTITY_CLAIM_INADMISSIBLE`, reason `SEMANTIC2_NOT_FROZEN` | A2 |
| admit/lossy-producer-bound-reserved | synthetic `LOSSY_KNOWN` receipt in a test baseline: verify_ok; admit:`IDENTITY_CLAIM_INADMISSIBLE`, reason `LOSSY_PRODUCER_BOUND_RESERVED` | A2 |
| admit/lossy-policy-field-ignored | same, with `accept_lossy_domains={"binary64-inexact-int"}`: still denied, reasons also contain `POLICY_FIELD_RESERVED` | A2 |
| admit/consumer-known-defect-reported | producer python FULL, consumer ts → admit_ok, `receipt_posture = CORE_BLOCKING_DIVERGENCE` | A3 |

Graph inputs reuse Core corpus documents by copy into `vectors/igx1/graphs/` (they are inputs here, not corpus vectors; the copies carry the Core commit they came from in a `SOURCES.ison` with per-file sha256). Vectors needing a synthetic baseline (retired, `LOSSY_KNOWN`, foreign receipt) use `tests/fixtures/baselines/test-*` that exist only under `tests/`. Binding files in `vectors/igx1/bindings/` are stored byte-exact (`.gitattributes`: `-text` so no EOL rewriting ever touches them).

## 6. Baselines as immutable release assets

```text
baselines/
  <core_commit>/
    MANIFEST.ison        meta.baseline (16 §1 values + core_runtime_dist[_version] + canonical_writer_dist[_version] = the ison-py the receipts and bindings are canonicalised with) · table.files (path sha256)
                         · table.core_runtime (module sha256) — module = ison_graph/__init__.py, multigraph.py,
                           query.py, schema.py, structural.py, viz.py as they exist at core_commit
    receipts/<port>.ison the six receipt files, bytes identical to Core's output
    domains.ison         per-port lossy/defect domain tags (§4.2)
```

Rules: never edited after the release that introduced them; a new Core adoption adds a new directory and a new Ext release (`16` §6); retiring a baseline flips `retired` in the *new* release's registry, not the old directory. The generator **fails closed**: it refuses to write into an existing baseline directory and only ever appends a registry row; a separate non-mutating verify mode regenerates into a scratch directory and compares byte-for-byte. Loading a baseline validates receipt **content**, not only hashes: posture ∈ the six values, `pass + canonicalized + lossy + defect + rejected_as_expected + todo == total`, and posture/counter consistency per Core's `corpus_receipt.py` rules (`FULL` ⇒ no todo/lossy/defect; `LOSSY_KNOWN` ⇒ lossy > 0, no todo/defect; `KNOWN_DEFECT` ⇒ defect > 0, no todo; `PARTIAL` ⇒ todo == total; `INCONCLUSIVE` ⇒ todo > 0). Tests: `MANIFEST.ison` hashes match the files; the built wheel and sdist contain every baseline file with matching hashes; `DEFAULT_BASELINE` is the newest non-retired entry; a release lane reproduces the baseline directory from the pinned Core commit; **the installed `ison-graph==1.4.1` distribution's modules hash to `table.core_runtime`** (this is also V0 at runtime — CI proves the pin is the baseline implementation, and the Core repo's `ison-graph/src` is byte-identical between tag `v1.4.1` and `ce9d3b7`, which is why the published wheel qualifies).

## 7. Repository

```text
isongraph-ext/                       ISON-format/isongraph-ext, MIT (Copyright (c) 2026 Mahesh Vaikri)
├── LICENSE  README.md  CHANGELOG.md  CONTRIBUTING.md      (shared-version convention from day one)
├── isongraph-ext/                    Python package: pyproject.toml, src/isongraph_ext/{__init__,igx,baselines}.py, tests/
├── baselines/                        §6 (package data, included via pyproject)
├── vectors/igx1/                     §5
├── docs/blueprint/                   this blueprint, versioned with the code
└── .github/workflows/ci.yml          pytest on 3.12; builds wheel+sdist and runs the packaging + runtime-pin tests
```

Version `0.1.0`. No TypeScript in E1; the vector manifest's `step` column is what makes TS parity checkable later.

## 8. Out of scope

Provenance, revision, delta, Datamatics, projection, DAG; Semantic/2 digest values; lossy producer-bound admission; cryptographic signatures; TS runtime; a capability registry with real entries; network or git access at runtime; any change to Core.

## 9. Changes this spec makes to earlier documents

- `16` §4: "unconditional" → `producer_bound`; `producer_bound` additionally requires source eligibility and a `full` re-verification; `LOSSY_KNOWN` row becomes reserved for E1; `cross_port` added as reserved. `16` §5 gains `MALFORMED_BINDING`, `SOURCE_WRITER_MISMATCH`, `SOURCE_ELIGIBILITY_MISMATCH`, `CORE_RUNTIME_MISMATCH`, `VERIFICATION_RESULT_MISMATCH`; verify/admit split named. `16` §7 scope names the classifier and the runtime pin.
- `03`: field list superseded by §2 here.

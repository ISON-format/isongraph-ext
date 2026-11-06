# E0.8 Core Baseline + E0.10 Ext/Core Compatibility Contract

Status: **FROZEN 2026-11-05** · Evidence: Core `main` @ `ce9d3b7` CI run `42125402035` (success) and CodeQL run `42125402247` (success), both on the merge of PR #3. Receipts in `receipts/` were generated from that commit.

This is the document E1 (IGX/1) implements. It freezes what Ext is allowed to trust about Core and how a Core Conformance Receipt turns into an admission decision. Changing anything in §1–§5 is a new contract version.

## 1. Ext-supported Core baseline (E0.8)

```text
Core baseline
  core_format               isongraph
  core_version              1.4.1
  core_commit               ce9d3b78afd79cbdffdd67546bcb5278dc38be70
  core_semantic_spec        ISONGraph-Semantic/2-draft        (13-SEMANTIC-2.md; freezes to /2 at G-ID)
  core_vector_corpus_version 1
  core_vector_corpus_commit f88af8bd29680e7b6e7716585be936d5738eb55f
  core_vector_corpus_digest 1d1a6648abeeadece24b43a163949d02241911706866236cc32bd6b61745bcb0

Reference producer
  python                    posture FULL          receipt sha256 cece1259ac61172a1d519b5ad31cef8b29ff3e466f629f4cb72b4f34fdda9ac0

Other admitted ports
  ts                        posture KNOWN_DEFECT  receipt sha256 393ba7e64e6c2be3606f2e8b03124dd2ff0cef33d069f38c6cb0b075dec268c4
  js                        posture KNOWN_DEFECT  receipt sha256 acbe2104736148bf19c0d93649781b9c142066bec4fe1ab0b6fdc116abc39ed6

Not admitted (no corpus runner)
  rust                      posture PARTIAL       receipt sha256 6dd9c2dcf5407f598233f6c3f21bf831a02f141a509ff45b112729ae35690040
  cs                        posture PARTIAL       receipt sha256 f37d41566cf69c3e6b933483946bc8559c8ceb160c2d6d4ea36caab8f94ccfc7
  cpp                       posture PARTIAL       receipt sha256 b330dc23e4d882c71942d035d1848f03841f932345c823f93b560c86f40e83a8
```

A receipt's identity is `sha256` of the exact ISON bytes `scripts/corpus_receipt.py --port <p>` prints for that commit (UTF-8, LF, trailing newline as printed). The six files in `receipts/` are those bytes. *Re-pinned 2026-11-05 (E1 Task 3): the first capture went through Windows text-mode stdout and stored CRLF; the digests above are of the LF bytes the script defines, verified by regenerating every receipt from `corpus_receipt.py` at `ce9d3b7`. Content is unchanged; the CRLF digests (`027c43…`, `f69d17…`, `5e8527…`, `c1a621…`, `8d9b6d…`, `8d230b…`) are void.*

**Ext v1 canonical reference operations are defined against a FULL Core port.** Python is therefore the current reference implementation.

## 2. Two concepts that must not be merged

```text
PRODUCER TRUST                         CROSS-PORT IDENTITY
  producer port posture FULL             producer posture
          ↓                              + consumer posture
  artifact may receive a canonical       + input semantic domain
  Core-semantic identity                         ↓
                                         identity equivalence admissible / inadmissible
```

> **Python is currently the only admitted port from which Ext may accept a producer-bound Core-semantic identity claim. Cross-port equivalence remains subject to the participating ports' conformance posture and the artifact's semantic domain, and is reserved until Semantic/2 freezes.**

Identity vocabulary (frozen by `17` §1): `identity_claim ∈ { none, artifact, producer_bound, cross_port }`. "Unconditional" in earlier drafts meant `producer_bound` from a `FULL` producer — never cross-port.

"Python is FULL" does **not** mean a Python-produced artifact is identical across ports: a `KNOWN_DEFECT` or lossy consumer can still fail to preserve the semantics on its side (the MultiGraph divergence and the JS numeric domain are the live examples). Every Ext receipt therefore records *both* the producer's posture and, where a consumer is named, the consumer's.

## 3. What an IGX/1 binding carries (E0.10)

Required, no defaults, never inferred after the fact:

```text
core_format                     isongraph
core_version                    1.4.1
core_commit                     <40-hex>
core_semantic_spec              ISONGraph-Semantic/2-draft | ISONGraph-Semantic/2
core_vector_corpus_version      1
core_vector_corpus_commit       <40-hex>
core_vector_corpus_digest       <64-hex>
producer_port                   python | ts | js | rust | cs | cpp
producer_port_version           1.4.1
producer_core_posture           FULL | LOSSY_KNOWN | KNOWN_DEFECT | PARTIAL | INCONCLUSIVE | NONCONFORMANT
core_conformance_receipt        <64-hex>   sha256 of the producer port's receipt bytes (§1)
```

Optional, present when an operation names a consumer (projection for a target runtime, delta application, cross-port verification):

```text
consumer_port, consumer_port_version, consumer_core_posture, consumer_conformance_receipt
```

Validation at bind time (each failure is a stable code, §5): the four Core pins must match the baseline the Ext runtime supports; the receipt digest must match a receipt the runtime holds or can regenerate for `core_commit`; the posture stated must equal the posture in that receipt (a binding may not claim a posture its receipt does not).

## 4. Admission rules — receipts as controls

Evaluation is two-phase (`17` §3–§4): **verify** asks whether a binding is historically valid against the baseline it pins — retired baselines still verify, so old receipts never become unverifiable; **admit** asks whether this runtime may use it now and whether its identity claim is admissible. `STALE_BINDING` is an admission outcome, not a verification failure.

| producer posture | identity-sensitive Ext operation (revision, delta, projection/DAG receipt, provenance binding) |
|---|---|
| `FULL` | allowed; the result may carry a `producer_bound` Core-semantic identity **only when the artifact is Semantic/2-draft eligible** (`17` §4.1 — a `FULL` port loads `out_of_domain` documents too); an `artifact` byte identity is always available |
| `LOSSY_KNOWN` | **reserved in E1**: no `producer_bound` claim (a policy waiver is not evidence that meaning survived); enabled once artifact-level domain classification exists (E7), then only where the policy accepts the affected domain (today: binary64-inexact integers, `1.0`→`1`) with `receipt_posture = CORE_LOSSY` |
| `KNOWN_DEFECT` | allowed for port-bound results only; **no unconditional cross-port identity claim**; result carries `CORE_BLOCKING_DIVERGENCE` when the input touches the defective class (today: MultiGraph documents) and `CORE_LOSSY` when it touches a lossy class |
| `PARTIAL` | no conformance-backed identity claim at all; results are unverified |
| `INCONCLUSIVE` | fail closed: identity-sensitive operations refuse |
| `NONCONFORMANT` | fail closed |

Cross-port equivalence (`A` produced it, `B` consumes it) is **admissible** only when: both postures are `FULL`, or each non-`FULL` side is `LOSSY_KNOWN` with the operation's policy accepting the affected domain, **and** the artifact's semantic posture is `identifiable`. Otherwise it is **inadmissible** and the receipt says so rather than staying silent.

Load posture, semantic posture and extension posture stay separate columns in every Ext receipt (`02` law 11, `13` §6.1).

## 5. Failure codes E1 must implement

```text
verification (17 §4 V0–V5) — raised as IGXError
CORE_RUNTIME_MISMATCH          installed ison-graph is not the pinned implementation of a CURRENT baseline (dist or module
                               hash); for a RETIRED baseline the mismatch yields a `limited` verification instead
VERIFICATION_RESULT_MISMATCH   admit() given a VerificationResult whose binding_digest is not this binding's (step A0)
MALFORMED_BINDING              shape: non-canonical bytes, missing/duplicate/unexpected block or field, bad enum,
                               non-null reserved field, cross-field token rule broken
CORE_BASELINE_UNSUPPORTED      core_commit unknown, or core_format/version/semantic_spec differ from that baseline
CORPUS_DIGEST_MISMATCH         corpus version, commit or digest differs from the baseline
RECEIPT_REFERENCE_INVALID      receipt digest unknown; stated port version/posture, or any cross-field inside the
                               receipt (core_commit, core_format, core_version, corpus_*, semantic_spec), disagrees
SOURCE_BINDING_MISMATCH        artifact_sha256 differs from the supplied bytes                (03)
SOURCE_WRITER_MISMATCH         derived canonicality != stored source_canonical (incl. a Python claim the writer contradicts)
SOURCE_ELIGIBILITY_MISMATCH    derived semantic eligibility/reason != stored fields
UNSUPPORTED_CAPABILITY         unknown REQUIRED extension, or range excludes the registered version (03)

admission (17 §4.2 A1–A2) — returned in AdmissionResult, never raised
STALE_BINDING                  baseline retired for new operations (still verifies)
IDENTITY_CLAIM_INADMISSIBLE    §4 forbids the identity claim the binding/operation makes (reasons carry the sub-cause)
```

Each is deterministic, carries the offending field, and never degrades to a warning.

## 6. What moves the baseline — and what does not

Moves it (new contract version, receipts regenerated, `receipts/` replaced, this file re-frozen): a new `core_commit` adopted by Ext; a corpus `version` bump; a Semantic/2 spec freeze.

Does **not** move IGX/1: a port's posture changing in a new receipt (e.g. TS/JS leaving `KNOWN_DEFECT` once they refuse MultiGraph documents). That shows up as new receipt digests and new admission outcomes with no change to the binding format — the test that this architecture is right.

## 7. Scope handed to E1

Build only (`17` is the normative detail): `ExtensionBinding`, `Baseline`/`Receipt`, `Capability` (`REQUIRED` / `OPTIONAL`) with an injectable registry, the E1 source-eligibility classifier (`17` §4.1), verify (V0–V5, raising) and admit (A1–A3, returning) producing the §5 codes, canonical-by-construction serialization of the binding, baselines as immutable package data with the pinned Core runtime's module hashes, and the `17` §5 conformance vectors. No provenance, revision, Datamatics or projection; no lossy producer-bound admission.

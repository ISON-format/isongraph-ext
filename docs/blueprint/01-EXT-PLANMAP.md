# ISONGraphExt PlanMap — E0–E13

Status values: `NOT_STARTED · READY · ACTIVE · BLOCKED · INCONCLUSIVE · DONE`

Core baseline: ISONGraph **1.4.1** (tag `v1.4.1` = `027fb77`, released 2026-11-05), ison-py 1.2.0. Forensics in `14-E0-FORENSICS.md` (run against 1.4.0); identity contract in `13-SEMANTIC-2.md`.

| ID | Milestone | Depends on | Status |
|---|---|---|---|
| E0 | Core Semantic Baseline (forensics + corpus + frozen contract) | shipped core | DONE except E0.9 (Rust/C#/C++) |
| E1 | IGX/1 Extension Binding + Capability Model | E0.10 (`16`) | READY — next |
| **G-ID** | **Graph Identity Soundness gate** (`13-SEMANTIC-2.md` §7) | E0, E1, Core 1.4.1 ✓ | BLOCKED on id-typing decision + corpus |
| E2 | IGPV/1 Provenance | E1 | NOT_STARTED |
| E3 | IGRV/1 Revision + IGD/1 Delta | E2, **G-ID** | BLOCKED |
| E4 | IGDM/1 Datamatics | E1,E2 | NOT_STARTED |
| E5 | IGP/1 Purpose Projection | E3,E4 | NOT_STARTED |
| E6 | IGDAG/1 DAG Projection | E5 | NOT_STARTED |
| E7 | IGRCP/1 Receipts + ISONCS Binding | E3,E5,E6 | NOT_STARTED |
| E8 | Public API + CLI | E4,E5,E6 | NOT_STARTED |
| E9 | Trust/capability/failure semantics | E1,E2,E3 | NOT_STARTED |
| E10 | Python reference conformance | E6,E7,E8,E9 | NOT_STARTED |
| E11 | TypeScript parity | E10 | NOT_STARTED |
| E12 | Core interoperability + benchmarks | E10,E11 | NOT_STARTED |
| E13 | Docs, packaging, OSS release | E12 | NOT_STARTED |

## E0 — Core Semantic Baseline
Re-cut 2026-11-05 around the executable Core corpus (`15-CORE-CONFORMANCE-CORPUS.md`). E0 no longer means "inspect what Core does"; it means "pin an executable statement of what Core means". Forensic findings live in `14-E0-FORENSICS.md`.
- E0.1 Pin Core release/commit — `DONE` (`v1.4.1` = `027fb77`)
- E0.2 Pin Semantic/2 version — `ACTIVE` (`13-SEMANTIC-2.md` draft; freeze at G-ID)
- E0.3 Run Core conformance corpus — `DONE` (Core PR #3 merged as `ce9d3b7`; 32 vectors, Py/TS/JS runners green in CI)
- E0.4 Capture corpus commit — `DONE` (`f88af8bd29680e7b6e7716585be936d5738eb55f`; see `receipts/`)
- E0.5 Capture corpus digest — `DONE` (`receipts/corpus_digest.txt`)
- E0.6 Capture per-port posture (Core Conformance Receipt) — `DONE` (`receipts/<port>.ison`: python FULL; ts, js KNOWN_DEFECT; rust, cs, cpp PARTIAL)
- E0.7 Record known Core divergences — `ACTIVE` (14-E0 §2–§5; corpus Findings will extend it)
- E0.8 Establish Ext-supported Core baseline — `DONE` (`16-CORE-BASELINE-AND-COMPATIBILITY-CONTRACT.md` §1–§2; evidence: `ce9d3b7` CI + CodeQL green. Python is the only port from which Ext accepts an unconditional Core-semantic identity claim; cross-port equivalence is a separate admission decision)
- E0.9 Parser/serializer forensics not covered by the corpus — `DONE` for Py/TS/JS, `ACTIVE` for Rust/C#/C++ (string ids, no MultiGraph; see 14-E0 §5)
- E0.10 Freeze Ext/Core compatibility contract — `DONE` (`16` §3–§7: binding fields, receipt-by-digest, admission rules, failure codes, E1 scope)

## E1 — IGX/1
Extension identity/version; graph binding; REQUIRED/OPTIONAL capability; dependencies; unknown-extension behavior; canonical extension identity; vectors. Implements the frozen contract in `16` §3–§7: the binding carries the Core baseline pins and the producer's Core Conformance Receipt by digest, validation emits the `16` §5 codes, and admission follows `16` §4. Scope is exactly `16` §7 — no provenance/revision/Datamatics/projection.

## E2 — Provenance
Graph/node/edge provenance scopes; source artifacts; extractor identity; transformations/collapse chains; merge rules; compactness; vectors.

## G-ID — Graph Identity Soundness gate
Nine conditions in `13-SEMANTIC-2.md` §7. E3 cannot open until all nine pass. Exit criteria: Core release carrying the identity patch (and the Rust/C#/C++ follow-ups), Semantic/2 tag bytes frozen, pre-E3 golden corpus executing on Python **and** TypeScript.

## E3 — Revision + Delta
Revision identity/base/parent; node/edge/group/property changes; application/rejection rules; revision/delta receipts; round-trip vectors. Depends on the Semantic/2 digest — not on ISONCS bytes.

## E4 — Datamatics
Node/edge/group presentation semantics; layout/LOD/interaction/temporal/accessibility hints; theme separation; compactness; vectors.

## E5 — Projection
Source revision pinning; anchors/selectors; direction/depth; mandatory material; budgets; provenance retention; deterministic ordering; receipts; runtime; vectors.

## E6 — DAG Projection
SCC detection; `collapse_scc`; `edge_class_filter`; `temporal_cut`; `fail_if_cycle`; topological-order artifact; provenance; acyclicity proof; vectors.

## E7 — Receipts/ISONCS
Canonical source, policy and result identity; projection/DAG/delta receipts; ISONCS vectors.

## E8 — API/CLI
Python/TS API; validate; project; project-dag; diff; apply-delta; verify receipt; acceptance fixtures.

## E9 — Trust/failure
Unknown required extension; stale binding; invalid delta; unsatisfiable projection budget; hostile input limits; adversarial vectors.

## E10/E11 — Reference implementations
Full Python conformance, then TypeScript vector parity.

## E12 — Interop/benchmarks
Legacy base-graph compatibility; extension-aware consumption; compactness/token cost; projection/DAG/delta performance; future language-parity matrix.

## E13 — Release
Specs, APIs, examples, conformance kit, packages, canonical verification, OSS receipt.

### Hard stops
- No base grammar mutation before E0 + ADR.
- No arbitrary DAG edge deletion.
- No domain-specific Datamatics.
- No renderer code.
- No Betterify/SkillDen/BrainLanding imports.

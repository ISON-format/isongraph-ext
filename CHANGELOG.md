# Changelog

## [Unreleased]

- CLI input is read within the byte budgets (`igp`, `igpv`, `igdm`): at most the budget plus one byte of a file is read before the library refuses it, instead of loading a whole oversized file first. `igpv origins` with an argument that is not valid UTF-8 now exits 64 instead of raising a traceback. `igp` passes one limits object to both file reading and the library. IGX has no byte budget yet and is unchanged.
- Tests: 13 new tests pin IGP/1 rules the 0.4.0 audit found unpinned (budget tie-breaks, mandatory-node distance, twin ids across anchors and mandatory, inclusive limits, INT64 maximum, foreign producers in verification). Each was shown to fail against the mutation it targets.
- `igp project --out` writes each output file atomically (temp file, then rename), so an interrupted run never leaves a half-written `result.ison`. Two more admission reasons are now tested (`SOURCE_UNCLASSIFIED`, `CONSUMER_POSTURE_LOSSY_KNOWN`).
- Documentation: refreshed timings (about 2 s for a full 10,000-node check), test count, IGP/1 in the PyPI long description, package description and examples guide; corrected vector counts in older CHANGELOG entries.

## [0.4.0] — 2026-11-09 — E5 IGP/1

- IGP/1 structural projection (`docs/blueprint/21-IGP1-DESIGN.md`, FROZEN rev 1): `isongraph_ext.igp.project(source, policy)` returns an ordinary directed ISONGraph plus an IGPV/1 lineage payload; a canonical policy file `<name>.igp.ison` (explicit anchors, node-type and relation allow-lists, direction, depth, mandatory nodes, node and edge budgets); exact source acceptance (directed simple canonical ison-v1 only); deterministic farthest-first budget pruning; `verify_projection` by recomputation; a byte-identical whole-graph result is lineage by self-attribution; `IGP_IMPLEMENTATION_VERSION` independent of the package version; CLI `python -m isongraph_ext.igp project|verify`; 61 conformance vectors under `vectors/igp1/`, each lineage additionally admitted by `igpv.verify_and_admit`. No change to IGX/1, IGPV/1, IGDM/1 or Core.
- IGX/1 verification loads the source artifact once instead of twice, and `bind()` twice instead of four times (new `igx.source.load_source`, with optional `loaded=` arguments on `derive_canonical` and `classify_eligibility`). Same answers, measured about 2x faster verification and bind on a 10,000-node graph. No wire, spec or API removal.

## [0.3.0] — 2026-11-08 — first public release (E4 IGDM/1)
- First release published to PyPI as `isongraph-ext` (alpha). It contains everything from the internal milestones 0.1.0 (IGX/1) and 0.2.0 (IGPV/1) listed below.
- Release plumbing: a Trusted Publishing workflow (`publish-pypi.yml`), `SECURITY.md`, Dependabot for GitHub Actions, a Releasing section in `CONTRIBUTING.md`; a rewritten README with an architecture section, and a PyPI long description with package metadata (keywords, classifiers, project URLs).
- `examples/`: adoption demonstrations (institutional evidence with IGX+IGPV, supply-chain assets with IGX+IGDM, a minimal generic IGDM-to-SVG adapter, a Core-only consumer, informational timings) with smoke tests and a fresh-venv wheel check. No library or protocol change.
- IGDM/1 datamatics (`docs/blueprint/19-IGDM1-DESIGN.md`, FROZEN rev 1): companion `<graph>.igdm.ison` of renderer-neutral presentation and interaction intent, canonical by construction, bound through IGX/1 as capability `igdm 1.0.0`.
- Node/edge hints (semantic, shape and pattern roles, emphasis, badge, ring, label, visibility/LOD, interaction markers, temporal state, accessibility text/role), groups (`hull` / `hierarchy` / `collapse` / `aggregate` over explicit members, acyclic parent tree, exclusivity and chain rules), layout hints; closed vocabularies plus a preserved-and-reported `x-` namespace; no appearance columns exist (theme separation).
- `verify()` with byte-budget preflight and D0–D4 (runs IGX/1 verification itself; object resolution reuses IGPV/1's), `bind()`, `verify_and_admit()` (admission is the binding's), CLI `python -m isongraph_ext.igdm verify` (exit 0/1/2, 64 on usage).
- `igx.DEFAULT_REGISTRY = {"igpv": "1.0.0", "igdm": "1.0.0"}`; `igpv.payload` wire helpers parameterised for reuse (E2 behaviour unchanged).
- 50 conformance vectors under `vectors/igdm1/` with generator and reference runner.
- Fix (post-audit, 2026-11-06): a `magnitude` whose `str()` is an exponent form (any float below 1e-4, e.g. `0.00001`) has no numeric wire form (`19` §1.1) and is now rejected at D1 in memory (`MALFORMED_DATAMATICS`), so `to_ison()`/`bind()` can no longer emit a payload and binding that every consumer rejects. Wire grammar and error contract unchanged; vector `reject/magnitude-exponent-form`.

## [0.2.0] — internal milestone, first published within 0.3.0 — E2 IGPV/1
- IGPV/1 provenance (`docs/blueprint/18-IGPV1-DESIGN.md`, FROZEN rev 1): companion `<graph>.igpv.ison`, canonical by construction (the canonical writer orders rows), bound through IGX/1 as capability `igpv 1.0.0`.
- Source attribution (SHA-256 artifacts, optional `bytes/1` / `lines/1` / `x-*` locators with runtime-derived `VERIFIED`/`UNVERIFIED` posture), producer attribution, graph/node/edge objects addressed by `NodeRef/2` / `EdgeAddress/2` (INT64 ids, ID-TWIN-INVARIANT), derivation lineage (`identity` / `collapse` / `rewrite`, artifact-to-artifact).
- `verify()` with byte-budget preflight and P0–P5 (runs IGX/1 verification itself), `bind()`, `verify_and_admit()` (admission is the binding's), bounded `Lineage` queries with object-level cycle detection, CLI `python -m isongraph_ext.igpv verify|origins` (exit 0/1/2, 64 on usage).
- `igx.DEFAULT_REGISTRY = {"igpv": "1.0.0"}` is the production registry default; `EMPTY_REGISTRY` remains for tests and the E1 vectors.
- 71 conformance vectors under `vectors/igpv1/` with generator and reference runner.

## [0.1.0] — 2026-11-05, internal milestone, first published within 0.3.0 — E1 IGX/1
- IGX/1 binding protocol (`docs/blueprint/17-IGX1-DESIGN.md`, FROZEN rev 3): companion `<graph>.igx.ison`, canonical by construction.
- Identity claims `none | artifact | producer_bound | cross_port`; `producer_bound` requires a `FULL` producer **and** a Semantic/2-draft-eligible artifact **and** a full (not limited) re-verification; `cross_port` reserved; lossy producer-bound admission reserved.
- `verify()` V0–V5 (raises `IGXError`; `limited` mode for retired baselines whose runtime is no longer installed), `admit()` A1–A3 (returns `AdmissionResult`; refuses evidence for another binding), `verify_and_admit()`, `bind()`, CLI `python -m isongraph_ext.igx verify|admit` (exit 0/1/2, 64 on usage).
- Core baseline `ce9d3b78afd79cbdffdd67546bcb5278dc38be70` embedded as immutable package data: six Core Conformance Receipts (LF bytes as `corpus_receipt.py` defines them), lossy/defect domain tags, pinned runtime module hashes (`ison-graph==1.4.1`, `ison-py==1.2.0`); generator fails closed, `--verify` reproduces from the pinned Core commit in CI.
- 35 conformance vectors under `vectors/igx1/` with a reference runner, generator and a spec-literal oracle.

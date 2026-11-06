# Changelog

## [Unreleased]

## [0.1.0] — 2026-11-05 — E1 IGX/1
- IGX/1 binding protocol (`docs/blueprint/17-IGX1-DESIGN.md`, FROZEN rev 3): companion `<graph>.igx.ison`, canonical by construction.
- Identity claims `none | artifact | producer_bound | cross_port`; `producer_bound` requires a `FULL` producer **and** a Semantic/2-draft-eligible artifact **and** a full (not limited) re-verification; `cross_port` reserved; lossy producer-bound admission reserved.
- `verify()` V0–V5 (raises `IGXError`; `limited` mode for retired baselines whose runtime is no longer installed), `admit()` A1–A3 (returns `AdmissionResult`; refuses evidence for another binding), `verify_and_admit()`, `bind()`, CLI `python -m isongraph_ext.igx verify|admit` (exit 0/1/2, 64 on usage).
- Core baseline `ce9d3b78afd79cbdffdd67546bcb5278dc38be70` embedded as immutable package data: six Core Conformance Receipts (LF bytes as `corpus_receipt.py` defines them), lossy/defect domain tags, pinned runtime module hashes (`ison-graph==1.4.1`, `ison-py==1.2.0`); generator fails closed, `--verify` reproduces from the pinned Core commit in CI.
- 34 conformance vectors under `vectors/igx1/` with a reference runner, generator and a spec-literal oracle.

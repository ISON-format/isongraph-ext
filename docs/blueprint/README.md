# ISONGraphExt — Formal Blueprint

Status: **E0 ACTIVE · G-ID DRAFTED · E3+ BLOCKED ON G-ID**

Core baseline: ISONGraph **1.4.1** (tag `v1.4.1` = `027fb77`, released 2026-11-05 to PyPI, crates.io, npm ×2 and NuGet) · ison-py 1.2.0. Forensics in `14` were run against 1.4.0 @ `3787f22`; the defects they found are what 1.4.1 fixes.

Recommended repo: `ISON-format/isongraph-ext`

Reading order for a new agent: this file → `00` → `01` (PlanMap, incl. G-ID) → `02` → `13-SEMANTIC-2.md` → `14-E0-FORENSICS.md` → `11`. The `Q_A*.md` files are design history that `13` supersedes.

ISONGraphExt is an additive, versioned extension layer for the already-shipped ISONGraph ecosystem. It does **not** replace ISONGraph Core and v1 does **not** require a breaking change to the existing `nodes.* / edges.*` wire grammar.

## Mission

Add cross-domain capabilities that multiple ISONGraph applications can reuse:
- extension binding/capability negotiation;
- provenance;
- graph revision and delta;
- Datamatics;
- deterministic purpose projection;
- deterministic DAG projection;
- ISONCS-backed receipts/integrity;
- conformance vectors and multi-language interoperability.

Projected graphs and DAG outputs remain valid ISONGraph graphs.

Start with **E0.1** in `01-EXT-PLANMAP.md`.

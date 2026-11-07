# isongraph-ext

Extension bindings over [ISONGraph Core](https://github.com/ISON-format/isongraph): IGX/1 companion
bindings whose identity claims (`none`, `artifact`, `producer_bound`, `cross_port`) are verifiable offline
against a frozen Core baseline and its Core Conformance Receipts.

Status: E4 (IGX/1 + IGPV/1 + IGDM/1). Specs: `docs/blueprint/17-IGX1-DESIGN.md`, `docs/blueprint/18-IGPV1-DESIGN.md`, `docs/blueprint/19-IGDM1-DESIGN.md`. Contract: `docs/blueprint/16-CORE-BASELINE-AND-COMPATIBILITY-CONTRACT.md`.

```bash
pip install isongraph-ext          # pins ison-graph==1.4.1, ison-py==1.2.0
python -m isongraph_ext.igx verify graph.ison graph.igx.ison
python -m isongraph_ext.igx admit  graph.ison graph.igx.ison
python -m isongraph_ext.igpv verify graph.ison graph.igx.ison graph.igpv.ison [--source SHA256=PATH]
python -m isongraph_ext.igpv origins <graph-sha256> graph.igpv.ison --node p 1
python -m isongraph_ext.igdm verify graph.ison graph.igx.ison graph.igdm.ison
```

A verified binding proves reproducibility and consistency, not authorship: `producer_port` is a checked
claim, not cryptographic authentication (spec §1.1). Provenance establishes origin and lineage, not that an
extracted assertion is true, and a SHA-256 identifies bytes without authenticating their origin (IGPV/1 §0.1). Datamatics carries rendition intent (roles, never colours or coordinates); ISONGraph Visualize interprets it and owns the renderer's own accessibility obligations (IGDM/1 §1.3).

Runnable end-to-end examples (a non-software provenance graph, a supply-chain presentation graph, a minimal generic SVG adapter, a Core-only consumer) are in [`examples/`](examples/README.md).

## Layout

- `isongraph-ext/` — the Python distribution (`src/isongraph_ext`, `tests/`); baselines ship inside the package.
- `vectors/igx1/`, `vectors/igpv1/`, `vectors/igdm1/` — conformance vectors (`manifest.ison`, byte-exact bindings, payloads and graph inputs).
- `scripts/` — `make_baseline.py` (embed a Core baseline, fail-closed; `--verify` reproduces), `make_vectors.py` / `make_vectors_igpv.py` / `make_vectors_igdm.py` (regenerate vectors).
- `docs/blueprint/` — the ISONGraphExt blueprint; `16` is the Ext/Core contract, `17` the IGX/1 spec, `18` the IGPV/1 spec, `19` the IGDM/1 spec.

MIT - Copyright (c) 2026 Mahesh Vaikri

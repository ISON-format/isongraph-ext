# isongraph-ext

Extension bindings over [ISONGraph Core](https://github.com/ISON-format/isongraph): IGX/1 companion
bindings whose identity claims (`none`, `artifact`, `producer_bound`, `cross_port`) are verifiable offline
against a frozen Core baseline and its Core Conformance Receipts.

**Status: early-stage, unreleased (alpha).** Not published to PyPI and not versioned for release; install from a clone of this repository as shown below. Python 3.12 or newer; pure Python; depends on exactly `ison-graph==1.4.1` and `ison-py==1.2.0`.

Supported: IGX/1 bindings (spec `docs/blueprint/17-IGX1-DESIGN.md`), IGPV/1 provenance (`18`) and IGDM/1 datamatics (`19`), each optional and independent of the others. Contract with Core: `docs/blueprint/16-CORE-BASELINE-AND-COMPATIBILITY-CONTRACT.md`.

Limitations: a Python reference implementation only; the `cross_port` identity claim and lossy `producer_bound` admission are reserved; no revision, delta, projection or DAG capability; IGDM/1 carries presentation intent only and renders nothing; verification is an offline cost (about 5 s for a 10,000-node graph with a capability, see `examples/README.md`); examples were verified on Windows and in Linux CI, not on macOS.

```bash
# From a clone of this repository (there is no PyPI release)
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install build
python -m build isongraph-ext                         # writes isongraph-ext/dist/
pip install isongraph-ext/dist/isongraph_ext-0.3.0-py3-none-any.whl     # also installs ison-graph==1.4.1, ison-py==1.2.0

# Make a sample graph, binding and Datamatics payload, then use the command-line tools on them
python examples/supply_chain_assets.py --write out/
python -m isongraph_ext.igx verify out/assets.ison out/assets.igx.ison          # exit 0 ok, 1 invalid, 64 usage
python -m isongraph_ext.igx admit  out/assets.ison out/assets.igx.ison          # exit 0 admitted, 2 denied
python -m isongraph_ext.igdm verify out/assets.ison out/assets.igx.ison out/assets.igdm.ison

# Provenance tools (IGPV/1): examples/institutional_evidence.py runs the full flow, including these two commands
python -m isongraph_ext.igpv verify graph.ison graph.igx.ison graph.igpv.ison [--source SHA256=PATH]
python -m isongraph_ext.igpv origins <graph-sha256> graph.igpv.ison --node p 1
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

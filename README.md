# isongraph-ext

Extension bindings over [ISONGraph Core](https://github.com/ISON-format/isongraph): IGX/1 companion
bindings whose identity claims (`none`, `artifact`, `producer_bound`, `cross_port`) are verifiable offline
against a frozen Core baseline and its Core Conformance Receipts.

Status: E1 (IGX/1). Spec: `docs/blueprint/17-IGX1-DESIGN.md`. Contract: `docs/blueprint/16-CORE-BASELINE-AND-COMPATIBILITY-CONTRACT.md`.

```bash
pip install isongraph-ext          # pins ison-graph==1.4.1, ison-py==1.2.0
python -m isongraph_ext.igx verify graph.ison graph.igx.ison
python -m isongraph_ext.igx admit  graph.ison graph.igx.ison
```

A verified binding proves reproducibility and consistency, not authorship: `producer_port` is a checked
claim, not cryptographic authentication (spec §1.1).

MIT - Copyright (c) 2026 Mahesh Vaikri

# isongraph-ext

IGX/1 extension bindings over ISONGraph Core 1.4.1: companion `<graph>.igx.ison` files whose identity claims
(`none`, `artifact`, `producer_bound`, `cross_port`) verify offline against an embedded, immutable Core baseline.

    python -m isongraph_ext.igx verify graph.ison graph.igx.ison   # exit 0 ok, 1 invalid, 64 usage
    python -m isongraph_ext.igx admit  graph.ison graph.igx.ison   # exit 0 admitted, 2 denied

Spec and contract: https://github.com/ISON-format/isongraph-ext/tree/main/docs/blueprint (`17`, `16`).
A verified binding proves reproducibility and consistency, not who authored the artifact.
MIT - Copyright (c) 2026 Mahesh Vaikri

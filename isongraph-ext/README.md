# isongraph-ext

IGX/1 extension bindings, IGPV/1 provenance and IGDM/1 datamatics over ISONGraph Core 1.4.1: companion `<graph>.igx.ison` files whose
identity claims (`none`, `artifact`, `producer_bound`, `cross_port`) verify offline against an embedded, immutable Core
baseline, and companion `<graph>.igpv.ison` payloads that bind source attribution and derivation lineage to an exact
graph artifact.

    python -m isongraph_ext.igx verify graph.ison graph.igx.ison                          # exit 0 ok, 1 invalid, 64 usage
    python -m isongraph_ext.igx admit  graph.ison graph.igx.ison                          # exit 0 admitted, 2 denied
    python -m isongraph_ext.igpv verify graph.ison graph.igx.ison graph.igpv.ison [--source SHA256=PATH]
    python -m isongraph_ext.igpv origins <graph-sha256> graph.igpv.ison --node p 1
    python -m isongraph_ext.igdm verify graph.ison graph.igx.ison graph.igdm.ison

Specs and contract: https://github.com/ISON-format/isongraph-ext/tree/main/docs/blueprint (`17`, `18`, `19`, `16`).
A verified binding proves reproducibility and consistency, not who authored the artifact. Provenance establishes
origin and lineage, not that an extracted assertion is true; a SHA-256 identifies bytes without authenticating their origin.
MIT - Copyright (c) 2026 Mahesh Vaikri

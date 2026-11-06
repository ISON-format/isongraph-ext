# IGDAG/1 — DAG Projection

Derive an acyclic purpose graph from a general ISONGraph without altering source truth.

Cycle policies:
- `collapse_scc`
- `edge_class_filter`
- `temporal_cut`
- `fail_if_cycle`

Arbitrary edge deletion is forbidden.

Output is ordinary ISONGraph, proven acyclic, with provenance to original nodes/edges and an optional deterministic topological-order artifact.

# IGP/1 — Purpose Projection

`project(G, P) -> G'`

`G` is an exact source graph revision, `P` a deterministic policy, and `G'` an ordinary valid ISONGraph with lineage receipt.

Policy building blocks: anchors, node/edge selectors, relation filters, direction, depth, hierarchy scope, state/provenance filters, temporal scope, mandatory nodes/edges/paths and bounded node/edge/byte budgets.

Mandatory material may not be silently pruned. If it exceeds budget: `PROJECTION_BUDGET_UNSATISFIABLE`.

Same source revision + normalized policy + runtime/spec version must yield equivalent result identity.

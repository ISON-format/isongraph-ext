# Core Compatibility Laws

1. ISONGraph Core works without Ext.
2. Ext v1 does not require legacy parsers to understand extension data to parse the base graph.
3. Projection outputs are ordinary ISONGraph.
4. DAG outputs are ordinary ISONGraph plus a proven acyclic invariant.
5. Extension artifacts bind to an exact source graph identity/revision.
6. Any future inline syntax requires its own ADR and compatibility suite.
7. Compactness, deterministic ordering, token efficiency and multi-language parity are constraints.
8. Visualization scene/layout state is not canonical graph truth.
9. **ISONGraphExt MUST NOT redefine the meaning of an ISONGraph document.** Ext receives an already-interpreted Core graph (`text → Core → Core conformance → Ext`), never reinterprets the text.
10. **Core owns `vectors/`.** Ext, Visualize and products consume the Core Conformance Corpus at a pinned commit through the Core Conformance Receipt; they never copy or fork vectors. A missing vector is added upstream.
11. Load posture, semantic posture and extension posture are tracked separately and never collapse into one bit. `Core loaded it` does not imply `semantically identifiable`; an Ext receipt produced through a `pass:lossy` port carries `CORE_LOSSY` and claims no cross-port identity equivalence.

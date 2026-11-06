# ISONGraphExt — Master Architecture

```text
ISON / ISONL
 structured representation
    |
    v
ISONGraph Core
 graph semantics / nodes / edges / refs / traversal / schema
    |
    +----------------------+----------------------+
    |                                             |
Semantic/2                          Core Conformance Corpus
 graph identity contract (13)        vectors/ in Core; executable
    |                                 "same document -> same meaning" (15)
    +----------------------+----------------------+
                           |
                           v
                Core Conformance Receipt
                 commit / semantic spec / corpus digest / per-port posture
                           |
                           v
                      ISONGraphExt
 provenance / revisions / deltas / Datamatics / projection / DAG
                           |
                           +--> ISONGraph Visualize (own corpus: scene/layout/LOD/timeline/a11y)
                           +--> Betterify
                           +--> SkillDen
                           +--> BrainLanding/Cognovel

ISONCS
 canonical bytes / artifact identity / receipts
```

Ext is pinned to an **executable statement of Core semantics** (the receipt), not merely to a Core version.

## Responsibilities

ISONGraphExt owns:
1. IGX/1 extension binding and capability negotiation;
2. provenance standard;
3. graph revision semantics;
4. graph delta semantics;
5. Datamatics;
6. purpose projection;
7. DAG projection;
8. extension receipts and ISONCS binding;
9. conformance vectors;
10. Python and TypeScript reference implementations.

It does **not** own ISONGraph core node/edge semantics, renderer/layout code, or product-specific vocabularies.

## v1 compatibility law

The base graph stays consumable by existing ISONGraph implementations. Extension-aware implementations additionally consume a companion extension binding. Inline grammar changes require a later explicit ADR and compatibility proof.

## Derived-graph law

`source ISONGraph + projection policy -> ordinary derived ISONGraph`

`source ISONGraph + DAG policy -> ordinary acyclic derived ISONGraph`

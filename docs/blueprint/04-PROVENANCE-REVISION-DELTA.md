# Provenance, Revision and Delta

## Provenance
Answers where graph material came from, which extractor/transformation produced it, which source revision supported it, and how derived/collapsed material maps back to original identities.

**Superseded for E2 by `18-IGPV1-DESIGN.md` (FROZEN 2026-11-06, rev 1)**, which is the normative IGPV/1 wire format, addressing, locator, lineage, verification and vector contract. Provenance merge and conflict-resolution rules are not part of IGPV/1 and await their own spec.

## Revision
Identifies an exact graph state and its canonical identity. Parent/base semantics must be explicit where used.

## Delta
Describes a transition between exact revisions: node, edge, group/property and extension add/remove/update.

Delta application rejects wrong base revision, collisions, invalid removals and invalid result state where validation is requested.

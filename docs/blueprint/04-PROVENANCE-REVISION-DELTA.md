# Provenance, Revision and Delta

## Provenance
Answers where graph material came from, which extractor/transformation produced it, which source revision supported it, and how derived/collapsed material maps back to original identities.

## Revision
Identifies an exact graph state and its canonical identity. Parent/base semantics must be explicit where used.

## Delta
Describes a transition between exact revisions: node, edge, group/property and extension add/remove/update.

Delta application rejects wrong base revision, collisions, invalid removals and invalid result state where validation is requested.

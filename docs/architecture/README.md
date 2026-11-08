# Architecture visuals

Two separate views of the implemented 0.3.0 architecture:

- [Full architecture](full-architecture.png): visual overview of artifact, library and external consumer layers.
- [Technical schematic](architecture-schematic.png): detailed verification and admission flow.
- [Editable SVG](architecture-schematic.svg): vector version of the schematic.
- [Generator](create_schematic.py): reproducible SVG/PNG generator (requires Pillow and Windows Segoe UI fonts).

Both diagrams are embedded and explained in the [main README](../../README.md#architecture).

## Reading the diagrams

ISONGraph Core owns graph content and serialization. Ext operates on companion files without rewriting graph bytes. IGX binds exact source bytes and declares capabilities; IGPV and IGDM payload digests are carried in the IGX capability table. Their target metadata also identifies the graph bytes. The payloads are independently optional, but their verification entry points require an IGX binding and rerun IGX verification.

Verification and admission are distinct. A1 checks baseline currency, A2 checks identity-claim admissibility, and A3 reports consumer posture. External applications decide how to use the results. Layout and rendering belong to consumers; IGDM supplies intent.

The schematic summarizes normal wire-payload flow. In-memory payload serialization performs shape checks before P0/D0 because bytes must first be produced. Unknown baseline lookup can fail at V2 before V0; a supported retired baseline without its matching runtime yields limited semantic verification. Missing provenance sources remain unverified, and limited mode skips graph-object resolution. Identity claims do not authenticate authorship.

## Repository evidence

- `../../README.md`: purpose, layering, examples and implementation limits.
- `../blueprint/16-CORE-BASELINE-AND-COMPATIBILITY-CONTRACT.md`
- `../blueprint/17-IGX1-DESIGN.md`
- `../blueprint/18-IGPV1-DESIGN.md`
- `../blueprint/19-IGDM1-DESIGN.md`
- `../../isongraph-ext/src/isongraph_ext/igx/{bind,verify,admit,baselines,registry}.py`
- `../../isongraph-ext/src/isongraph_ext/igpv/{bind,verify,resolve,payload}.py`
- `../../isongraph-ext/src/isongraph_ext/igdm/{bind,verify,payload}.py`
- `../../isongraph-ext/pyproject.toml`: runtime and pinned dependencies.

Diagrams describe this checkout; reserved and future capabilities are not shown as implemented.

# vectors/igdc1 — IGDC/1 consumption vectors (26 §5)

Every row of `manifest.ison` is normative. `op` selects what a runner does, never the presence of a column:
`consume` (inputs -> expected hint file, or the stated error), `verify` (hint document -> C0-C3 result), `derivation` (hint document + inputs -> C4).
Expected hint files are written by the reference deriver in `scripts/make_vectors_igdc.py` (ison_parser only), not by `isongraph_ext.igdc`.
`SHA256SUMS` pins every file. Input-level rejections carry the code and step the EXISTING igx/igdm verification path raises (IGDC propagates them unchanged).

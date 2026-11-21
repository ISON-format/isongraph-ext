# vectors/igs-addr — IGDC/1 typed-address vectors (26 §1, §5)

Hand-written literals, independent of `isongraph_ext.igdc`. Every row of every table is normative: a port claims conformance by passing ALL rows
(the manifest row counts are part of the claim). Values are typed literals (`int:7` is an integer, `str:7` a string, `surrogate:d800` a lone
surrogate); no reader may infer a type from digits. `SHA256SUMS` pins the files; `manifest.ison` is canonical ison-py output.

Tables: `vectors` (tag, parse, node_type, relation) · `edges` · `order` · `edge_order` · `twins`.

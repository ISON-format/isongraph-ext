# Errata to the frozen specifications

These notes are **non-normative**. The frozen texts of IGX/1, IGPV/1, IGDM/1 and IGP/1 are not edited, the behavior they specify does not change, and no conformance vector is regenerated to match prose. Where a published table or example disagrees with the vectors or the writer, the vectors and the writer are authoritative. Each entry names the document, what it says, and what is actually the case.

## E-1. `17-IGX1-DESIGN.md` section 5: `ok/reserialize-stable` is not a vector file

The table lists `ok/reserialize-stable` as if it were one of the IGX/1 vectors. There is no such entry in `vectors/igx1/manifest.ison`. The property it describes (re-serializing an accepted binding gives the same bytes and digest) is asserted by a test over every accepted binding vector (`test_reserialize_stable_over_ok_bindings`). Conversely, the manifest contains `reject/trailing-newline-in-hex-field`, which the table does not list. The manifest has 35 vectors.

## E-2. `18-IGPV1-DESIGN.md` section 6: two listed vectors do not exist, four exist unlisted

- `reject/origin-bytes-wrong` and `reject/document-bytes-wrong` are listed, but neither is in `vectors/igpv1/manifest.ison`. The manifest has `reject/origin-size-wrong` and `reject/document-size-wrong`, whose bytes hash correctly and whose declared size is wrong. The rule that supplied document bytes with the wrong hash fail at P5 is covered by unit tests, not by a vector. Supplied origin-graph bytes with the wrong hash (P4) are specified but have neither a vector nor a dedicated test; the implementation follows the written rule.
- The manifest also contains `reject/duplicate-block`, `reject/self-artifact-document-kind`, `reject/semantic-digest-set` and `reject/unexpected-block`, which the table does not list. The manifest has 71 vectors.

## E-3. `19-IGDM1-DESIGN.md` section 1: the wire example is not byte-canonical

The example payload in section 1 is illustrative and is **not** what the writer emits. Written by the canonical writer, the same content differs in two ways:

1. **Block order.** The writer orders the data tables by name: `table.edges`, `table.groups`, `table.members`, `table.nodes`, after `meta.igdm` and `meta.layout`. The example shows `nodes`, `edges`, `groups`, `members`.
2. **Quoting.** The writer does not quote a plain word: the group label is `Cluster`, not `"Cluster"`. It quotes values that would otherwise parse as something else (the `"true"`/`"false"` tokens and numeric-looking text such as `"0"` and `"3"`), as the example's closing note says.

A verifier rejects the example as written with `MALFORMED_DATAMATICS` at `canonical_form`, which is the rule in section 3. Use the vectors under `vectors/igdm1/` for byte-exact payloads. The text of the example block itself is left as published.

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

## IGAR/1 and IGDC/1 (specs 25 and 26)

The same rule applies: `25-IGAR1-DESIGN.md`, `26-IGDC1-DESIGN.md` and their plans are frozen (digests in `FREEZE-DIGESTS-igar1-igdc1.sha256`) and are not edited. Where they differ from the implementation or its vectors, the implementation and the vectors are authoritative. Entries E-4 to E-7 record decisions accepted by the owner on 2026-11-22.

### E-4. `25-IGAR1-DESIGN.md` section 5: CLI exit 2 also covers `RECOMPUTE_UNAVAILABLE`

Section 5 lists three codes for exit 2 (refused): `RECEIPT_POLICY_UNSATISFIED`, `RECEIPT_NOT_PINNED`, `RECEIPT_SUBJECT_MISMATCH`. The CLI also exits 2 for `RECOMPUTE_UNAVAILABLE` (the `recompute` command could not run under the receipt's profile, version or runtime). That is a refusal to judge, not a verdict on the receipt, so it is kept apart from exit 1. `RECEIPT_RECOMPUTE_MISMATCH` exits 1, as every other `IGARError` outside the refused set does.

### E-5. `25-IGAR1-DESIGN.md` sections 2.1 and 3: "first failure wins V0 to V5, then D0 to D4" is not exact for oversize inputs

An oversize target or payload is reported at D1 (`DATAMATICS_LIMIT_EXCEEDED`) even when the binding would also fail at V2 (the payload schema is invalid). The receipt records the check that the reference implementation reports first, as `meta.failure.check` states. The rule "the step of the first failure" holds within the order the implementation actually runs.

### E-6. `25-IGAR1-DESIGN.md` section 4.3: the example policy is not the vector

The section calls its example "the vector `policies/accept.policy.ison`". The vector is broader: it lists a second `core_commit` (`1111111111111111111111111111111111111111`), three `profile_sha256` values and a verifier row, so that the policy rows `reject/policy-admission-required` and `reject/policy-full-resolution-required` fail at their stated dimension instead of at `profile`. The example block is illustrative only; use `vectors/igar1/policies/` for byte-exact policy files.

### E-7. `25-IGAR1-DESIGN.md` sections 2.4 and 3 (R6): `recompute` with wrong caller bytes

If the target, binding or payload bytes given to `recompute` are not the ones the receipt names, and every precondition holds, the result is `RECEIPT_RECOMPUTE_MISMATCH` at R6. The spec says nothing about this case; a caller who wants the subject check should run `check_subject` (R3, `RECEIPT_SUBJECT_MISMATCH`) first. Also: four recompute cases are unit-tested but have no vector row, because the vector counts (122 rows, 133 pinned files) are frozen: a hint-derived receipt whose `igdc_sha256` differs, a different ison-py runtime, version and profile both different, and a permissive policy admitting a denied or limited receipt.

### E-8. `26-IGDC1-DESIGN.md`: wording slips, no behaviour change

- **Section 1.3 text order.** The sentence "`i:-1` after `i:0`" is wrong: `-` sorts before `0`, so `i:-1` sorts before `i:0` in the file. The rule that the file's row order is not semantic order stands.
- **Section 1.7 probe table.** The 19-digit decimal string 2^63 is listed as a probed fact; the probe test `test_igdc_probe.py` does not include it. The consumption vector `string-ids-digit-like-and-unicode` covers it.
- **Section 5.2.** `id-types-distinct` is described with four node types; the vector uses three.
- **Section 4, C3.** The `UNRESOLVED_REFERENCE` field for an unknown member group reports the member's node id untagged, because C3 reuses IGDM/1 D3.
- **Status line.** The header still reads "DRAFT rev 2 FOR OWNER FREEZE REVIEW"; the text was frozen on 2026-11-21 and is not edited.
- **Plan `2026-11-17-ext2-ext3-igdc1.md`, Task 6.** The generator block contains "Part B" twice with differing `ok/id-types-distinct` rows. The second copy, which matches section 5.2, is the one shipped.

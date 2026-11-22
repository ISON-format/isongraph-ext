# IGAR/1 trust-policy file (IGAR-POLICY/1)

A canonical ISON document (ison-py `dumps_canonical`; UTF-8, LF, no trailing newline), read with the strict reader: byte budget
(`Limits.max_payload_bytes`) before parsing; no repeated column; no summary row, typed column or reference cell. Blocks, each exactly once:

| block | columns | rule |
|---|---|---|
| `meta.policy` | `policy_spec`, `require_admission`, `require_full_resolution` | one row; `IGAR-POLICY/1`; the two flags are the strings `"true"`/`"false"` |
| `table.verifiers` | `verifier`, `verifier_version` | accepted pairs; empty accepts none |
| `table.core_commits` | `core_commit` | 40 lowercase hex; empty accepts none |
| `table.profiles` | `profile_sha256` | 64 lowercase hex, the digest of an accepted verifier profile; empty accepts none |
| `table.runtime` | `runtime_ison_graph`, `runtime_ison_py` | accepted pairs; empty = do not constrain |

A duplicate row, bad hex digit, bare boolean, unexpected block or summary row is `MALFORMED_POLICY`. A policy that names no verifier,
baseline and profile accepts nothing. A policy match says nothing about provenance: authorization is `authorize_hints` (`25` §4).

## Example

This file is accepted by the reader and says: any `isongraph-ext` 0.4.1 receipt, issued under exactly one verifier profile, against one Core baseline, whose verification and admission passed with full object resolution. The empty `table.runtime` block does not constrain the runtime versions.

```text
meta.policy
policy_spec require_admission require_full_resolution
IGAR-POLICY/1 "true" "true"

table.core_commits
core_commit
ce9d3b78afd79cbdffdd67546bcb5278dc38be70

table.profiles
profile_sha256
437145940b1b0836d357c28ed107e4bfcee91d06f7a74480b638e681a4495b93

table.runtime
runtime_ison_graph runtime_ison_py

table.verifiers
verifier verifier_version
isongraph-ext 0.4.1
```

The profile digest above is the digest of the default verifier profile of this release (`Profile.default().digest`). Take the digest from the profile you actually accept: it is recorded in every receipt as `meta.verifier.profile_sha256`.

## Use

```bash
python -m isongraph_ext.igar policy    receipt.igar.ison --trust-policy trust.policy.ison
python -m isongraph_ext.igar authorize receipt.igar.ison --pins SHA256SUMS --target graph.ison --binding graph.igx.ison \
    --payload graph.igdm.ison --igdc graph.igdc.ison --trust-policy trust.policy.ison
```

`policy` reads the receipt and this file, runs the policy check and nothing else. A success says the policy is satisfied and, in the same output, that this is not an authorization. `authorize` additionally requires that the receipt bytes are pinned in the consumer's own delivery pin file (a `sha256sum`-format file; only the line naming the receipt's file name is used), that the receipt is about exactly the bytes supplied, and that the policy matches. Only then does it print the admitted digests.

## What this file is and is not

- It is the consumer's own statement of which verifiers, profiles and Core baselines it will accept. It is read by `TrustPolicy.from_ison`; a malformed file is refused (`MALFORMED_POLICY`, exit 1), never partly applied.
- It does not authenticate anything. A receipt is unsigned and carries no freshness: it needs a trusted delivery boundary (a controlled, digest-pinned channel the consumer controls), and a policy match is not trust. A forged receipt can match any policy it is written to match.
- It does not name keys, signers or time windows, because IGAR/1 has none of those.

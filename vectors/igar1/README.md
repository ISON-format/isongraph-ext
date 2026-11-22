# vectors/igar1 — IGAR/1 vectors (25 §7)

Every row of `manifest.ison` is normative. `op` selects what a runner does (never the presence of a column):
`issue` (inputs + profile -> expected receipt file), `inspect` (R0-R2), `subject` (R3), `policy` (R4), `authorize` (pinned + bound + policy-fit, all together),
`recompute` (R6, Python only), `profile` (profile document), `policyfile` (policy document).
Expected receipts and profiles are written by the reference builders in `scripts/make_vectors_igar.py` (ison_parser only), never by `isongraph_ext.igar`.
`verifier_version` is injected as `vectors` so receipts do not change with every release. `SHA256SUMS` pins every file.

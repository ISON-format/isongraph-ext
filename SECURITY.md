# Security policy

ISONGraphExt is an early-stage (alpha) library that verifies extension artifacts for ISONGraph; it treats every input as untrusted and validates it, but it has not been independently audited. IGPV/1, IGDM/1 and IGP/1 enforce input-size and row limits, IGX/1 does not, and no byte limit bounds memory: see [docs/resource-limits.md](docs/resource-limits.md).

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub: **Security** tab, then **Report a vulnerability** (private vulnerability reporting). Do not open a public issue for a security problem. Include the affected version, a minimal input that reproduces it, and the impact you observed.

## Scope

In scope: parsing and verification of bindings, provenance and datamatics payloads, resource-limit bypasses, and anything that makes a verification succeed that should fail. A verified binding proves reproducibility and consistency, not authorship (see the README); that is by design and not a vulnerability. An IGAR/1 receipt is unsigned: it needs a trusted delivery boundary and a policy match is not trust, so a forged receipt that matches a policy is not a vulnerability of this package; the trust boundary is described in [`docs/blueprint/25-IGAR1-DESIGN.md`](docs/blueprint/25-IGAR1-DESIGN.md) (section 4) and [`docs/igar-policy-format.md`](docs/igar-policy-format.md). Anything that lets `authorize_hints` succeed without a digest-pinned receipt, exact bytes and a policy match is in scope.

## Supported versions

Only the latest release receives fixes while the project is in alpha.

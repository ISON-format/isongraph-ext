# Security policy

ISONGraphExt is an early-stage (alpha) library that verifies extension artifacts for ISONGraph; it treats every input as untrusted and bounds its work, but it has not been independently audited.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub: **Security** tab, then **Report a vulnerability** (private vulnerability reporting). Do not open a public issue for a security problem. Include the affected version, a minimal input that reproduces it, and the impact you observed.

## Scope

In scope: parsing and verification of bindings, provenance and datamatics payloads, resource-limit bypasses, and anything that makes a verification succeed that should fail. A verified binding proves reproducibility and consistency, not authorship (see the README); that is by design and not a vulnerability.

## Supported versions

Only the latest release receives fixes while the project is in alpha.

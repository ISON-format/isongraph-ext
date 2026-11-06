# IGX/1 — Extension Binding

IGX/1 gives all extensions one binding/capability model.

Normative concepts:
- extension ID + semantic version;
- exact source graph ID/digest/revision;
- REQUIRED or OPTIONAL capability;
- extension dependency/capability range;
- payload identity/digest;
- canonical receipt identity.

Unknown REQUIRED extension -> `UNSUPPORTED_CAPABILITY`.
Unknown OPTIONAL extension -> base graph remains consumable and the extension must not be silently reinterpreted.
Wrong graph/revision -> `SOURCE_BINDING_MISMATCH`.

The exact ISON serialization is frozen after E0. The default v1 architecture is a companion extension artifact rather than a base-grammar break.

The binding's wire format, runtime API, verification/admission order, failure codes and vectors are specified in `17-IGX1-DESIGN.md`; the contract it implements is `16` §3–§5. IGX/1 is the binding *protocol* (recognised by `meta.igx.binding_spec`), not a capability — the capability registry starts empty.

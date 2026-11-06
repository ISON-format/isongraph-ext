# IGDM/1 conformance vectors

`manifest.ison` → `table.vectors`: `id target binding payload expect step detail`.

- `target`: graph under `graphs/synthetic/` — every graph is generator-made with the pinned Core (`ison-graph==1.4.1`), byte-exact.
- `binding`: IGX/1 binding under `bindings/` carrying the `igdm` capability row (derived from the shipped payload bytes unless the row tests the binding itself).
- `payload`: file under `payloads/`, byte-exact. Some are deliberately non-canonical or malformed.
- `expect`: `+`-joined `verify_ok | reject:<CODE> | admit_ok | admit:<CODE>`.
- `step`: the D step that must fire first (`A1` for an admission outcome); an `IGXError` raised while IGDM/1 runs IGX/1 verification inside D0 is recorded as `D0`.
- `detail`: `;`-separated assertions — `roles:<csv>` (the exact `unrecognized_roles` tuple), `resolution:skipped`, `limits:<name>=<int>` — plus free text.

Regenerate with `scripts/make_vectors_igdm.py`; the generator asserts every row against the runtime before writing.

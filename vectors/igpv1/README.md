# IGPV/1 conformance vectors

`manifest.ison` → `table.vectors`: `id target binding payload sources expect step detail`.

- `target`: graph under `graphs/synthetic/` — every graph is generator-made with the pinned Core (`ison-graph==1.4.1`), byte-exact; `none` for lineage rows.
- `binding`: IGX/1 binding under `bindings/` carrying the `igpv` capability row; `none` for lineage rows.
- `payload`: file(s) under `payloads/`, byte-exact; `+`-joined for lineage rows (the first is the query root). Some are deliberately non-canonical or malformed.
- `sources`: `none`, or `+`-joined file names under `sources/`; each name is the sha256 of the file's bytes (the runner supplies them as `{sha256: bytes}`).
- `expect`: `+`-joined `verify_ok | reject:<CODE> | admit_ok | admit:<CODE> | lineage_ok | lineage:<CODE>`.
- `step`: the P/L step that must fire first; an `IGXError` raised while IGPV/1 runs IGX/1 verification inside P0 is recorded as `P0`.
- `detail`: `;`-separated assertions — `locator:<attribution_id>=<VERIFIED|UNVERIFIED>`, `origin:<artifact_id>=<verified|unverified>`, `resolution:skipped`, `origins:<n>` (derivation steps returned), `terminal:<name>`, `query:<object_id>`, `limits:<name>=<int>` — plus free text.

Regenerate with `scripts/make_vectors_igpv.py`; the generator asserts every row against the runtime before writing.

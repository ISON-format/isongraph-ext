# IGX/1 conformance vectors

`manifest.ison` → `table.vectors`: `id graph binding registry expect step detail`.

- `graph`: input under `graphs/` (byte-exact copies of Core corpus documents, provenance in `SOURCES.ison`; `graphs/synthetic/` holds generator-made mutations such as a CRLF rewrite and is not in `SOURCES.ison`).
- `binding`: file under `bindings/`, byte-exact. Some are deliberately non-canonical or malformed.
- `registry`: `empty` (production) or `test` (`x-igx-test 1.0.0`).
- `expect`: `+`-joined `verify_ok | reject:<CODE> | admit_ok | admit:<CODE> | admit_posture:<POSTURE> | retired_ok | retired:<CODE>` (`retired*` tokens are evaluated with `allow_retired_baselines=True`).
- `step`: the V/A step that must fire first (a second runner must agree on *where*, not just *that*).
- `detail`: free text; `limited` marks a vector whose verification must be `semantic_verification = limited`; `reason:<TOKEN>` names a reason the admission result must carry.

Regenerate with `scripts/make_vectors.py`; the generator asserts every row against the runtime before writing.
Synthetic baselines (`1…1` retired with a historical runtime, `2…2` LOSSY_KNOWN, `3…3` foreign receipt) live in `isongraph-ext/tests/fixtures/baselines/`.

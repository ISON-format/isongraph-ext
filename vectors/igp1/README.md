# IGP/1 conformance vectors

`manifest.ison` → `table.vectors`: `id source policy result payload expect step detail`.

- `source`: graph under `sources/` — generator-made with the pinned Core (`ison-graph==1.4.1`), byte-exact; some are deliberately unsupported or malformed.
- `policy`: file under `policies/`, byte-exact (some deliberately non-canonical or malformed).
- `result`, `payload`: files under `expected/`, or `none`. For passing vectors they are the exact expected outputs of `project()`; for `verify:` vectors they are deliberately tampered artifacts handed to `verify_projection()`.
- `expect`: `ok` or `reject:<CODE>`. `step`: the Q step that must fire first.
- `detail`: `;`-separated assertions — `nodes:<csv of node ids>`, `stats:<name>=<value>,…`, `result:source` (result bytes equal the source bytes), `limits:<name>=<int>` (`lineage.`-prefixed names set the IGPV/1 limits), `verify:<result|payload|version|policy>` — plus free text.

Every successful projection's lineage is additionally admitted by `igpv.bind` and `igpv.verify_and_admit` with the source supplied, in both the runner and the generator.

Regenerate with `scripts/make_vectors_igp.py`; the generator asserts every row against the runtime before writing, and regenerating leaves the files byte-identical.

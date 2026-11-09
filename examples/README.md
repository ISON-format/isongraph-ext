# ISONGraphExt adoption examples

Small, runnable demonstrations that the released capabilities (IGX/1, IGPV/1, IGDM/1; IGP/1 projection is described in the main README) can be consumed by someone who has never heard of any product built on them. None of them uses software-engineering vocabulary, and none imports anything but `ison_graph`, `ison_parser`, `isongraph_ext` and the standard library.

## Install and run

```bash
git clone https://github.com/ISON-format/isongraph-ext.git && cd isongraph-ext
python -m venv .venv && . .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install isongraph-ext                               # the examples live in the repository, not in the wheel
python examples/institutional_evidence.py
python examples/supply_chain_assets.py --write out/
python examples/igdm_to_svg.py out/assets.ison out/assets.igx.ison out/assets.igdm.ison out/assets.svg
python examples/core_only.py
python examples/measure.py            # optional: python examples/measure.py 10000
```

Each script prints what it checked and ends with an `OK: ...` line. `pytest isongraph-ext/tests/test_examples.py` runs them as smoke tests; `--built` additionally installs the built wheel into a fresh virtual environment and runs them from there.

## What each one shows

| Example | Shows |
|---|---|
| `institutional_evidence.py` | Board minutes and a facilities report → a raw extraction graph → a curated decision/evidence graph. IGX binds each graph; IGPV attributes nodes to document line spans, verifies the spans against the real bytes, rejects a tampered source, traces a collapsed decision back to its raw rows, and behaves honestly (`UNVERIFIED`) when the sources are not supplied. Includes the CLI path. |
| `supply_chain_assets.py` | Suppliers, facilities and components with regional hulls, a bill-of-materials hierarchy, a collapsed sub-assembly, visual state and a product-private `x-` role and capability. IGX binds, IGDM carries presentation intent, verification rejects hints for absent nodes and illegal group combinations. Lists what IGDM/1 cannot express. `--write DIR` leaves the three files on disk. |
| `igdm_to_svg.py` | A generic consumer of about 130 lines: verify, then draw a static SVG from the closed IGDM/1 vocabulary. Fixed grid, basic shapes, a static role→fill table; only `hull` groups are drawn. Simple `ison-v1` graphs only: a verified MultiGraph or ISONL graph is refused with exit 2, not drawn. Every `x-` token is treated as "no hint" and never interpreted. Refuses to render a payload that fails verification. |
| `core_only.py` | A consumer that imports only `ison_graph`, never `isongraph_ext`, and reads no companion file. The graph is an ordinary ISONGraph. |
| `measure.py` | Informational timings, reported separately (see below). |

## What this does and does not prove

Proves: the public APIs and CLIs are usable end to end on two non-software graphs; extensions are optional (a Core-only consumer pays nothing for them; an unknown `OPTIONAL` capability is reported, an unknown `REQUIRED` one fails closed); presentation intent is consumable by a consumer that knows nothing about any product.

Does not prove: external demand or adoption, a second implementation, production readiness, a real renderer (the SVG adapter is deliberately not a layout engine and is not ISONGraph Visualize), real-world documents, or interactive-latency performance.

## Measured costs (informational, no thresholds)

`measure.py` times, separately and from single runs: a Core parse; an IGX verification; IGPV and IGDM verification (each runs an IGX verification inside, so the table also reports `*_extra` = total minus the IGX run, an approximation because it is a difference of two single samples); and SVG generation from an already-parsed graph and already-verified payload (no parse inside the figure). Output of `python examples/measure.py 100 1000 10000` on a development machine (Windows, Python 3.12, 0.4.0), graph with N nodes and 2N edges; seconds:

| N | core_parse | igx_verify | igpv_extra | igdm_extra | svg_render |
|---|---|---|---|---|---|
| 100 | 0.005 | 0.008 | 0.012 | 0.011 | 0.001 |
| 1000 | 0.030 | 0.075 | 0.134 | 0.116 | 0.010 |
| 10000 | 0.411 | 0.762 | 1.250 | 1.060 | 0.082 |

A full IGPV or IGDM verification is `igx_verify + *_extra`: about 2 s at 10,000 nodes here (measured again for 0.4.0). Larger graphs have not been re-measured. That is an offline-validation cost, not an interactive one. No caching or optimisation is applied. A graph without companion files costs exactly a Core parse.

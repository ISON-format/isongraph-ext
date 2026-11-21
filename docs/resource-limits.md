# Resource limits

`isongraph-ext` is a Python reference implementation. Read this before you feed it input you do not control.

## What is limited, and what is not

| Capability | Input limits |
|---|---|
| IGPV/1 | Explicit byte and row budgets (`Limits`): graph, payload and per-table rows. |
| IGDM/1 | Explicit byte and row budgets (`Limits`). |
| IGP/1 | Explicit byte and row budgets for source, policy, result and lineage payload; node and edge budgets bound the *result*, not the work done to read the source. |
| IGDC/1 | Reuses the IGDM/1 `Limits` (nothing new). The hint document's byte size is checked against `max_payload_bytes` before any decoding or parsing, and its row count against `max_rows_per_table` after the parse; the derived document is refused (`DATAMATICS_LIMIT_EXCEEDED`, step P1) if it exceeds `max_payload_bytes`. |
| IGX/1 | **None.** IGX/1 does not define equivalent limits. It is frozen, and no limits are planned. |

The byte budgets cap how many bytes of a file are accepted. They do **not** cap memory. The graph is parsed by ISONGraph Core into an in-memory property graph, and that representation is many times larger than the file. An input that is within every budget can still use a great deal of memory and time. A 256 MB source limit does not prevent an out-of-memory condition.

IGDC/1 adds no budget of its own. As above, its byte budget bounds the *file*, not memory. `consume` first runs IGDM/1 verification (which includes IGX/1 verification and a Core load of the target), then loads the target through Core once more to read its direction and multigraph flags, so deriving costs about one further Core load of the target on top of verification (see the Core load column below). Checking a hint document on its own (`verify_hints`, C0 to C3) loads no graph. Memory and time for IGDC/1 are **not measured**; do not infer them from the table below. The byte budget does not bound time either: parse time grows superlinearly with the number of columns in a table header (this is ison-py's own header handling; the reader's duplicate-column scan in this package is linear), so a small document with a very wide header can still take long to check. Measured on one development machine, reading a table header of 20,000 extra columns (about 229 KB) through the strict reader took about 3 s after the reader's own scan was made linear, against about 5 s before; the remaining time is inside ison-py and is not changed by this package.

## Measured memory use

One synthetic family of graphs, one machine, one run each; treat the numbers as an order of magnitude, not a guarantee.

- Graph: `n` nodes of one type with two short string properties each, joined in a chain by `n-1` directed edges, written by Core as canonical `ison-v1`.
- Software: Python 3.12.7 on Windows 11; `ison-graph` 1.4.1, `ison-py` 1.2.0, `isongraph-ext` 0.4.1.
- Method: one fresh process per measurement; the figure is the process's peak working set (`PeakWorkingSetSize` from the Windows API, after the file was read into memory), so it includes the interpreter and the input bytes.
- Operations: `core` = `ISONGraph.from_ison` only; `igx` = `igx.bind` then `igx.verify`; `igp` = `igp.project` from one anchor with depth 2.

| Nodes | File | Core load | IGP/1 project | IGX/1 bind + verify |
|---:|---:|---:|---:|---:|
| 30,000 | 1.2 MB | 73 MB | 107 MB | 164 MB |
| 120,000 | 4.8 MB | 231 MB | 352 MB | 573 MB |
| 250,000 | 10.5 MB | 460 MB | 703 MB | 1,163 MB |

Over this range peak memory grew roughly in step with the input (about 45x the file size for the Core load alone, about 65-70x for IGP/1 and about 110x for IGX/1), and IGX bind plus verify took 32 s at 250,000 nodes. Nothing larger was measured, and denser graphs or longer property values will change the ratios. The measurements say nothing about how memory behaves at the byte limits.

## What to do with untrusted input

Apply your own process-level controls around every call: a memory limit (container or OS limit), a wall-clock timeout, and your own smaller input-size cap chosen from the table above. Run verification in a separate process you can kill. Do not rely on this library's budgets as a resource guarantee.

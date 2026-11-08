<p align="center">
  <img src="assets/isongraph-banner.png" alt="ISONGraph" width="760">
</p>

<h1 align="center">ISONGraphExt</h1>

<p align="center">
  <strong>Prove what a graph is, where it came from, and how to show it — without changing the graph.</strong>
</p>

<p align="center">
  <a href="https://github.com/ISON-format/isongraph-ext/actions/workflows/ci.yml"><img src="https://github.com/ISON-format/isongraph-ext/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/status-alpha-orange.svg" alt="Alpha">
  <img src="https://img.shields.io/badge/dependencies-ison--graph%20%2B%20ison--py-informational.svg" alt="Two pinned dependencies">
</p>

<p align="center">
  <a href="#try-it-in-two-minutes">Try it</a> ·
  <a href="#what-you-get">What you get</a> ·
  <a href="#from-the-command-line">CLI</a> ·
  <a href="#examples">Examples</a> ·
  <a href="#where-it-fits">Where it fits</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#status-and-limits">Status</a> ·
  <a href="docs/blueprint/README.md">Specs</a>
</p>

---

[ISONGraph](https://github.com/ISON-format/isongraph) stores a graph as a compact, token-efficient file. That file deliberately says nothing about **who made it**, **where its facts came from**, or **how a viewer should draw it**. ISONGraphExt answers those three questions with small **companion files that sit next to the graph** and are tied to its exact bytes by SHA-256. The graph itself is never modified, and everything works offline.

```mermaid
flowchart LR
    G["<b>graph.ison</b><br/>an ordinary ISONGraph<br/>(Core reads it as before)"]
    X["<b>graph.igx.ison</b><br/>IGX/1 · binding"]
    P["<b>graph.igpv.ison</b><br/>IGPV/1 · provenance"]
    D["<b>graph.igdm.ison</b><br/>IGDM/1 · datamatics"]
    G -. "SHA-256" .- X
    G -. "SHA-256" .- P
    G -. "SHA-256" .- D
    X --> V{{"verify · admit"}}
    P --> V
    D --> V
```

Core works without any of it. Add a companion only when you need the answer it gives.

## What you get

| Question | Companion | In one line |
|---|---|---|
| *Is this really the graph I was promised?* | **IGX/1** binding | Pins the exact bytes, the Core version they were written with, and an identity claim (`none`, `artifact`, `producer_bound`). Unknown capabilities are reported or refused, never silently ignored. |
| *Where did this come from?* | **IGPV/1** provenance | Attributes nodes and edges to source documents, with byte or line spans you can check against the real bytes, and records derivation lineage: *this node stands for those nodes in an earlier graph*. |
| *How should a viewer present it?* | **IGDM/1** datamatics | Renderer-neutral presentation **intent**: semantic roles, emphasis, badges, groups, layout hints and accessibility text. Never colours, fonts or coordinates. |

Each is optional and independent. A consumer that knows none of them still has the whole graph.

## Try it in two minutes

Until the first PyPI release, install from a clone (Python 3.12+; the only dependencies are `ison-graph==1.4.1` and `ison-py==1.2.0`):

```bash
git clone https://github.com/ISON-format/isongraph-ext.git && cd isongraph-ext
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install build
python -m build isongraph-ext                         # writes isongraph-ext/dist/
pip install isongraph-ext/dist/isongraph_ext-0.3.0-py3-none-any.whl
```

Bind a graph to its bytes, verify it, then change one byte:

```python
from ison_graph import ISONGraph
from isongraph_ext import igx

g = ISONGraph()
g.add_node("person", "ada", name="Ada")
g.add_node("person", "grace", name="Grace")
g.add_edge("knows", ("person", "ada"), ("person", "grace"))
data = g.to_ison().encode("utf-8")

binding = igx.bind(data, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")
result, decision = igx.verify_and_admit(binding, data)
print("admitted:", decision.admitted, "| steps:", ", ".join(result.steps_passed))

try:
    igx.verify(binding, data + b"\n# edited")
except igx.IGXError as e:
    print("tampered:", e.code, "at", e.step)
```

```text
admitted: True | steps: V0, V1, V2, V3, V4, V5
tampered: SOURCE_BINDING_MISMATCH at V4
```

Verification is a fixed sequence of numbered steps, and every failure names the step and a stable error code.

## From the command line

```bash
python examples/supply_chain_assets.py --write out/      # makes a graph, a binding and a datamatics payload
python -m isongraph_ext.igx verify out/assets.ison out/assets.igx.ison
```

```text
meta.verification
binding_digest semantic_verification source_canonical source_semantic_eligibility source_semantic_reason steps_passed unrecognized_optional
7057257e8d09a62d5c0a03ec2983bd38155e6579e04a1446c62116c45009c292 full "true" eligible null V0,V1,V2,V3,V4,V5 x-asset-ledger
```

Output is itself ISON, so receipts can quote it verbatim. Exit codes are stable: `0` ok, `1` invalid, `2` admission denied, `64` usage.

```bash
python -m isongraph_ext.igx   admit  out/assets.ison out/assets.igx.ison
python -m isongraph_ext.igdm  verify out/assets.ison out/assets.igx.ison out/assets.igdm.ison
python -m isongraph_ext.igpv  verify graph.ison graph.igx.ison graph.igpv.ison [--source SHA256=PATH]
python -m isongraph_ext.igpv  origins <graph-sha256> graph.igpv.ison --node person ada
```

## Examples

Runnable demonstrations that use only the public API. Neither involves software.

| Example | What it shows |
|---|---|
| [`institutional_evidence.py`](examples/institutional_evidence.py) | Board minutes become decisions and evidence. Provenance links each node to the exact lines it came from, **rejects a tampered source**, and traces a merged decision back to the raw rows it replaced. |
| [`supply_chain_assets.py`](examples/supply_chain_assets.py) | Suppliers, facilities and components with regions, a bill of materials and visual states carried as datamatics. Also lists what the contract cannot express. |
| [`igdm_to_svg.py`](examples/igdm_to_svg.py) | A deliberately tiny, generic consumer: verify first, then draw a static SVG from the closed role vocabulary. Unknown `x-` roles are ignored, not interpreted. |
| [`core_only.py`](examples/core_only.py) | A consumer that never imports the extension package. The graph is just a graph. |

See [`examples/README.md`](examples/README.md) for how to run them, the timings, and what they do not prove.

## Where it fits

| Layer | Owns |
|---|---|
| **ISONGraph Core** | The graph: nodes, edges, properties, parsing and writing |
| **ISONGraphExt** *(this repository)* | Binding, provenance and presentation intent as verifiable companion files |
| **ISONGraph Visualize** | Layout, interaction, animation and rendering of datamatics |
| **Your application** | Domain meaning, policy and user experience |

Ext never reinterprets the document, and it carries no vocabulary from any one domain.

## Architecture

ISONGraphExt is an offline Python library with CLI entry points. **The graph stays in Core; extensions live in companion files.** The following overview shows how producers, artifacts, verification and consumers connect.

[![Full ISONGraphExt architecture: producers, graph and companion files, verification library, admission policy and external consumers](docs/architecture/full-architecture.png)](docs/architecture/full-architecture.png)

### Files and responsibilities

An application uses ISONGraph Core to produce `graph.ison`, containing nodes, edges and properties. It can then add the companions it needs:

| File | Responsibility | What connects it to the graph |
|---|---|---|
| `graph.igx.ison` | **Binding:** records the Core baseline, conformance receipt, identity claim and declared capabilities. | SHA-256 of the exact graph bytes. Capability rows also pin the bytes of declared payloads. |
| `graph.igpv.ison` | **Provenance:** records source artifacts, producers, object attributions and derivation lineage. | Target graph digest and serialization profile; its payload digest is declared in IGX. |
| `graph.igdm.ison` | **Presentation intent:** describes roles, emphasis, badges, groups, layout hints and accessibility text. | Target graph digest and serialization profile; its payload digest is declared in IGX. |

IGPV and IGDM are independently optional; neither requires the other. Their verification APIs require an IGX binding. A Core-only consumer can read the original graph without loading any extension.

### Verification and admission flow

The schematic expands the implementation into its verification stages, shared support modules and consumer boundary. Open the image for full-size detail, or use the [editable SVG](docs/architecture/architecture-schematic.svg).

[![Technical schematic of IGX V0–V5, IGPV P0–P5, IGDM D0–D4 and admission A1–A3](docs/architecture/architecture-schematic.png)](docs/architecture/architecture-schematic.png)

1. **Produce and bind.** Create the graph, serialize any payloads, and create an IGX binding that records their digests. The graph bytes are unchanged.
2. **Verify the binding.** IGX checks the runtime, binding shape, Core baseline, receipt references, source bytes and capability support through V0–V5. Shared support includes embedded baselines and receipts, canonical ISON serialization, SHA-256 and a capability registry.
3. **Verify each supplied payload.** IGPV runs P0–P5 to check the payload binding, structure, references, graph objects and supplied source locators. IGDM runs D0–D4 to check its binding, structure, references and graph objects. Each payload verifier invokes IGX verification itself. Byte and row budgets bound input processing; unavailable provenance evidence remains explicitly unverified.
4. **Apply admission policy.** `verify_and_admit` passes the fresh verification result into admission: A1 checks baseline currency, A2 checks whether the identity claim is admissible, and A3 reports consumer posture. Successful verification and permission to use the binding are separate results.
5. **Consume the result.** Applications decide how to use the reports and admission decision. Viewers combine the graph with verified IGDM intent and choose layout, styling and interaction. Rendering belongs to the consumer; Ext supplies no renderer.

The reference runtime pins `ison-graph==1.4.1` and `ison-py==1.2.0`. These checks establish byte consistency and checkable lineage; they do not authenticate authorship or establish that source statements are true. See the [architecture notes](docs/architecture/README.md) for source references and verification-order details, and the [normative specifications](docs/blueprint/README.md) for the complete contracts.

## Built to be checked

- **Byte-exact.** Companion files are canonical by construction: one graph, one companion, one set of bytes, one SHA-256.
- **Specified before coded.** Each capability has a frozen specification in [`docs/blueprint/`](docs/blueprint/README.md); the code follows it, never the reverse.
- **Conformance vectors.** 156 byte-exact vectors in [`vectors/`](vectors) (IGX/1 35, IGPV/1 71, IGDM/1 50) and about 450 tests, replayed in CI on every change.
- **Pinned to a measured Core.** The package embeds the Core baseline it was verified against, plus Core's own conformance receipts, so identity claims are checkable rather than asserted.
- **Hostile-input safe.** Parsing is bounded by explicit size and row budgets, and verification reports the first failing step instead of guessing.

## Status and limits

ISONGraphExt is **early-stage (alpha)** and **not yet released on PyPI**. Know what it does not do:

- A verified binding proves **reproducibility and consistency, not authorship**. `producer_port` is a checked claim, not authentication.
- Provenance proves origin and lineage, **not that an extracted statement is true**; a SHA-256 identifies bytes without authenticating where they came from.
- The cross-port identity claim and lossy producer-bound admission are reserved. Revision, delta, projection and DAG capabilities are not implemented.
- IGDM/1 carries presentation **intent only** and renders nothing.
- It is a Python reference implementation. Verification is an offline cost: roughly 5 seconds for a 10,000-node graph with a capability (see [`examples/README.md`](examples/README.md)).
- The examples were verified on Windows and in Linux CI, not on macOS.

## Documentation

[`docs/blueprint/`](docs/blueprint/README.md) holds the normative texts: the Ext/Core contract (`16`), IGX/1 (`17`), IGPV/1 (`18`) and IGDM/1 (`19`). [`CHANGELOG.md`](CHANGELOG.md) lists what changed, [`CONTRIBUTING.md`](CONTRIBUTING.md) explains how to work on the project and how releases are made, and [`SECURITY.md`](SECURITY.md) explains how to report a vulnerability privately.

## License

MIT — Copyright (c) 2026 Mahesh Vaikri. See [`LICENSE`](LICENSE).

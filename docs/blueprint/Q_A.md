Yes. I would treat this review as an **identity-contract correction**, not eight independent cleanup items.

The key observation is your F4+F5 point: until those are closed, the current digest cannot safely serve as graph identity. That means **E3 must not depend on it yet**.

I would lock the decisions this way:

| Finding                 | Decision                                                             | Must close                            |
| ----------------------- | -------------------------------------------------------------------- | ------------------------------------- |
| **F7 edge addressing**  | **4-tuple canonical address**                                        | Before E1                             |
| **F6 ordinal ordering** | **Ordinal is opaque string; compare UTF-8 bytes lexicographically**  | Before E1                             |
| **F4 directedness**     | **Fix Core**, include graph semantics in semantic digest             | Before E3                             |
| **F5 writer version**   | Required receipt field, no default; separate semantic vs byte digest | Before E3 contract; implemented in E7 |
| **F8 vector corpus**    | Core/upstream-owned conformance corpus                               | Before E11/E12                        |

### F7 — choose the 4-tuple

Canonical edge identity should be:

```text
EdgeAddress =
(
    source_ref,
    relation_type,
    target_ref,
    ordinal
)
```

The **3-tuple can remain ergonomic API sugar**, but it must never be the canonical serialized/digested address.

For a simple graph:

```text
(A, KNOWS, B)
```

may resolve internally to:

```text
(A, KNOWS, B, "0")
```

For multigraphs:

```text
(A, KNOWS, B, "0")
(A, KNOWS, B, "1")
(A, KNOWS, B, "reply")
```

can coexist.

That means every downstream format has one edge-address model instead of discovering at E5 that simple and multi-edge identity were defined differently.

### F6 — make ordinal an opaque string

I would **not parse it numerically**.

Normative comparison:

```text
UTF8(ordinal_a) < UTF8(ordinal_b)
```

using unsigned bytewise lexicographic ordering.

Therefore:

```text
"10" < "2"
```

is intentionally true.

If a producer wants numeric ordering, it should generate canonical sortable strings such as:

```text
"0000000001"
"0000000002"
"0000000010"
```

Why choose this? Because arbitrary edge keys may eventually be nonnumeric, and UTF-8 byte ordering is trivial to reproduce identically in Python, Rust, TypeScript, C++, etc. We should not let individual implementations decide whether `"10"` means ten or two characters.

---

## F4 + F5 reveal that we actually need **two digests**

This is the larger fix I would make.

Right now we are trying to make one digest answer two different questions:

> Is this the same graph?

and:

> Is this the exact same serialized artifact?

Those should not be the same primitive.

Define:

```text
Graph Semantic Digest
        ≠
Artifact Byte Digest
```

### 1. Semantic graph digest

Something like:

```text
ISONGraph-Semantic/2
```

It hashes graph meaning:

```text
graph metadata
├── directed
├── multigraph
└── semantic graph properties

nodes
├── identity
└── semantic properties

edges
├── source
├── relation
├── target
├── ordinal
└── semantic properties
```

It must be independent of:

```text
writer version
serialization whitespace
block ordering
file extension
physical byte layout
```

Therefore:

```text
Python writer 1.2
        │
        ├── different bytes
        │
Python writer 1.3
        │
        ▼

same semantic graph
        ↓
same semantic digest
```

That's the identity E3/E5/E6 should depend on.

### 2. Artifact digest

Separate:

```text
artifact_sha256 =
SHA256(exact_written_bytes)
```

Now writer differences are completely legitimate:

```text
writer 1.2
artifact_sha256 = AAA

writer 1.3
artifact_sha256 = BBB

semantic_graph_digest = XYZ
```

No contradiction.

This also makes F5 much cleaner.

---

## F4 should be fixed in Core

I agree with the review here.

If directedness affects the meaning of an ISONGraph, **Core's identity must know whether the graph is directed**.

Do not make Ext repair an incomplete graph identity forever.

I would normalize simple Graph and MultiGraph metadata around:

```text
meta.graph
├── directed: true | false
└── multigraph: true | false
```

Then the semantic digest starts with something equivalent to:

```text
graph_kind {
    directed
    multigraph
}
```

so:

```text
Undirected:
A — B
```

cannot collide with:

```text
Directed:
A → B
B → A
```

even if their flattened edge sets happen to look equivalent.

And because this changes digest meaning, **version the digest**.

Do not silently alter the current digest algorithm:

```text
ISONGraph-Semantic/1    old
ISONGraph-Semantic/2    directedness-safe
```

Ext can require `/2`.

That is much safer than retroactively giving old fingerprints new meaning.

---

## F5 receipt schema

I would make this mandatory:

```text
core_writer {
    implementation
    version
    serialization_profile
}
```

For example:

```text
implementation: isongraph-python
version: 1.3.0
serialization_profile: ison-v1
```

No `"unknown"` default.

No inferred installed version after the fact.

Receipt should carry both:

```text
semantic_digest:
    algorithm: ISONGraph-Semantic/2
    value: ...

artifact_digest:
    algorithm: SHA-256
    value: ...

core_writer:
    implementation: ...
    version: ...
    serialization_profile: ...
```

Then a receipt can prove both:

> What graph did this mean?

and:

> What exact bytes did this writer produce?

F5 belongs in E7's receipt implementation, as you said, but the **required-field contract must be frozen before E3** because earlier stages must know which identity they are consuming.

---

## F8 should absolutely stay upstream

Ext should consume:

```text
ISONGraph Core Conformance Corpus
```

not own it.

I would structure upstream vectors into two classes:

```text
vectors/
├── semantic/
│   ├── directed-vs-undirected
│   ├── multiedge-ordinal
│   ├── property-order
│   ├── node-order
│   └── expected-semantic-digest
│
└── serialization/
    ├── writer-version
    ├── expected-artifact-bytes/hash
    └── roundtrip
```

This distinction matches the two-digest model.

E11/E12 then consume a pinned corpus revision:

```text
core_vector_corpus_commit
core_vector_corpus_digest
```

Ext verifies the core contract; it doesn't become responsible for proving that contract.

---

## I would change the execution gates

The corrected critical path becomes:

```text
E0
 │
 ├── F6 LOCK
 └── F7 LOCK
        │
        ▼
       E1
        │
        ▼
┌──────────────────────────────┐
│ IDENTITY SOUNDNESS GATE      │
│                              │
│ F4 directedness closed       │
│ F5 digest split frozen       │
│ Semantic/2 specified         │
│ writer receipt field frozen  │
└──────────────┬───────────────┘
               │
               ▼
              E3
               │
          E5 / E6
               │
               ▼
              E7
        receipt implementation
               │
               ▼
         ...
               │
          E11 / E12
               ▲
               │
        Core vector corpus
            upstream
```

So I would add an explicit gate:

> **G-ID — Graph Identity Soundness**

E3 cannot open until it passes.

Its acceptance conditions should be essentially:

```text
directedness participates in semantic identity
multigraph-ness participates in semantic identity
4-tuple edge identity frozen
ordinal ordering frozen
semantic digest version frozen
artifact digest distinguished
writer metadata required
identity test vectors passing
```

That is stronger than letting F4/F5 linger until E7.

The important conceptual correction is therefore:

> **A graph has a semantic identity independent of how a particular writer serialized it. A serialized artifact has a byte identity tied to the writer that produced it.**

Once we establish that distinction, F4, F5, F6, F7, and F8 stop being separate awkward edge cases and become one coherent **ISONGraph identity contract**.

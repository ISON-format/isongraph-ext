Yes. S7 improves the model because it separates **semantic identity** from **persistence capability**, which we had been implicitly treating as the same thing.

The important new law is:

> **A graph may have a valid Semantic/2 identity even when a particular Core implementation cannot persist and reload it correctly.**

That distinction should become explicit before E3.

For the negative-ID case:

```text
Graph G
  node id = INT64(-1)
  edge references that node

Semantic/2
  ↓
valid NodeId/2
  ↓
digest(G) succeeds

Python Core 1.3.0 persistence
  ↓
dump
  ↓
load
  ↓
_resolve_ref("-1")
  ↓
wrong STRING resolution
  ↓
NodeNotFoundError
```

That's **not**:

```text
SEMANTIC_DIGEST_MISMATCH
```

It's:

```text
PERSISTENCE_CONFORMANCE_FAILURE
```

and the distinction will save a lot of debugging later.

## I would revise the contract this way

`NodeId/2` remains:

```text
NodeId/2 ::=
      INT64
    | STRING
```

with:

```text
BOOL    forbidden as integer identity
FLOAT64 forbidden as NodeId
```

So these are valid and distinct:

```text
INT64(1)
INT64(-1)
STRING("1")
STRING("-1")
```

But Core's twin-node invariant guarantees that within the same node type you cannot simultaneously have:

```text
INT64(1)
STRING("1")
```

and presumably likewise:

```text
INT64(-1)
STRING("-1")
```

if the twin check is consistently applied.

Therefore endpoint resolution is simpler than we thought:

```text
:p:1
```

doesn't require Semantic/2 ambiguity resolution because Core guarantees only one legal typed candidate exists.

So I agree: **`AMBIGUOUS_NODE_REFERENCE` should not be an expected Semantic/2 failure.**

Keep the numeric code reserved if desired for defensive validation/future formats, but remove it from the normative reachable taxonomy.

The E0 invariant becomes:

> **ID-TWIN-INVARIANT — Within one node type, Core must reject simultaneous integer-ID and string-ID twins whose canonical decimal spelling is identical.**

And test both:

```text
1     vs "1"
-1    vs "-1"
```

across every construction path:

```text
add_node
load .ison/.isong
load .isonl
language ports
```

---

### The negative integer bug belongs upstream

The Python inconsistency you found is especially useful because the intended behavior is already visible inside the same implementation:

```python
node_id.lstrip("-").isdigit()
```

versus:

```python
text.isdigit()
```

That makes the likely Core correction pretty unambiguous.

The regression vector should be:

```text
nodes.p
id
-1

edges.R
source target
:p:-1 :p:2
```

Expected:

```text
Python       PASS
TypeScript   PASS
JavaScript   PASS
Rust         ?
C++          ?
C#           ?
```

and:

```text
dump → load → digest
```

must preserve the same Semantic/2 identity.

The vector belongs in the **Core semantic/persistence conformance corpus**, not Ext.

---

## Float IDs are a different category

I agree with your distinction.

Negative integer ID:

> Valid format/domain concept, implementation defect in Python persistence.

Float ID:

> Core API currently admits something that the reference syntax cannot reliably resolve.

That should be settled by specification, and I would choose the restrictive answer:

> **ISONGraph node identifiers are STRING or signed integer only. Non-integral numeric identifiers are invalid.**

So construction should reject:

```text
1.5
-4.25
NaN
Infinity
```

rather than teaching every reference parser how to interpret floating identifiers.

There are several reasons:

```text
:p:1.0
```

raises immediate questions about:

```text
1
1.0
1e0
01.0
```

and numeric normalization starts bleeding into graph reference syntax.

There is very little upside.

So `_check_identifier` accepting float IDs looks like a **Core validation gap**, not something Semantic/2 should accommodate.

---

# Semantic identity and persistence now need separate conformance statuses

I would add this explicitly to E0/E11.

For any fixture:

```text
SemanticStatus
PersistenceStatus
```

For example:

| Fixture                            | Semantic/2    | Python persistence  | TS persistence           |
| ---------------------------------- | ------------- | ------------------- | ------------------------ |
| positive INT64 ID                  | IDENTIFIABLE  | PASS                | PASS                     |
| negative INT64 ID                  | IDENTIFIABLE  | **FAIL currently**  | PASS                     |
| STRING ID                          | IDENTIFIABLE  | PASS                | PASS                     |
| FLOAT node ID                      | OUT_OF_DOMAIN | Core should reject  | Core should reject       |
| list property                      | OUT_OF_DOMAIN | lossy serialization | lossy serialization      |
| `10**20` property                  | OUT_OF_DOMAIN | Core accepts        | implementation-dependent |
| finite fractional FLOAT64 property | IDENTIFIABLE  | expected round-trip | expected round-trip      |

This creates a very useful rule:

```text
SEMANTICALLY_IDENTIFIABLE
does not imply
PERSISTENCE_CONFORMANT
```

But:

> **Anything declared persistence-conformant by a Core port must return to the same Semantic/2 identity after round-trip.**

Formally:

```text
if Persistable_port(G):

    Semantic2(G)
        ==
    Semantic2(load_port(dump_port(G)))
```

That is the invariant E11 should actually test.

---

## Revised SemanticIdentityError taxonomy

I would now make the reachable set:

```text
SemanticIdentityError
├── VALUE_OUT_OF_DOMAIN
├── UNDIRECTED_EDGE_CONFLICT
├── INVALID_EDGE_ADDRESS
├── MISSING_GRAPH_SEMANTICS
└── UNSUPPORTED_SEMANTIC_VERSION
```

Reserved:

```text
AMBIGUOUS_NODE_REFERENCE
```

but not currently reachable under the Core ID-twin invariant.

And persistence errors live separately:

```text
PersistenceConformanceError
├── REFERENCE_RESOLUTION_FAILURE
├── TYPE_ROUNDTRIP_FAILURE
├── VALUE_ROUNDTRIP_FAILURE
├── GRAPH_SEMANTICS_ROUNDTRIP_FAILURE
└── UNSUPPORTED_PERSISTENCE_VALUE
```

That separation is much cleaner than making Semantic/2 absorb Core serializer defects.

---

# G-ID condition 7 should now be strengthened

Previously:

> Golden corpus passes reference implementation and at least one independent implementation.

I would sharpen it to:

> **Before E3 opens, the identity corpus MUST execute against Python and TypeScript, not merely compare a Python implementation against static expected hashes.**

Why those two?

Because they're already enough to expose a real shipped divergence.

Minimum pre-E3 vectors should include:

```text
positive INT64 id
negative INT64 id
STRING id
int/string twin rejection
negative int/string twin rejection

1 vs 1.0 property collapse
-0.0 normalization
fractional FLOAT64
int64 min
int64 max
out-of-range integer
integral FLOAT64 outside int64
nonfinite FLOAT64

directed vs undirected
undirected mirror collapse
undirected mirror conflict
simple edge ordinal "0"
multiedge ordinal
UTF-8 ordinal ordering

null property elision
```

That's enough to establish the identity foundation before Ext starts building on it.

The larger Core corpus can expand later.

---

# But don't call Python+TS “cross-language proof”

This is where your final Rust/C++/C# point matters.

Before F8 is considered **closed**, I'd require a port matrix rather than assuming two implementations represent the ecosystem:

```text
                Python   TS/JS   Rust   C++   C#
-------------------------------------------------
NodeId +1         ✓       ✓       ?      ?     ?
NodeId -1         BUG     ✓       ?      ?     ?
STRING id         ✓       ✓       ?      ?     ?
twin rejection    ✓       ✓       ?      ?     ?
float rejection   GAP     GAP?     ?      ?     ?
Semantic/2 vals   ...
```

There are two stages:

```text
G-ID
  Python + TypeScript mandatory
  enough to unblock E3

F8 / E11-E12
  all supported Core ports
  upstream-owned corpus
```

That avoids delaying Ext unnecessarily while still being precise about what has actually been proven.

If Rust has a third behavior, that doesn't invalidate the Semantic/2 model; it tells us there is another Core conformance defect.

---

## G-ID now reads better as nine conditions

I'd update it to:

1. 4-tuple `EdgeAddress/2` frozen.
2. Ordinal opaque STRING + UTF-8 ordering frozen.
3. `directed` and `multigraph` mandatory semantic inputs.
4. Scalar Semantic/2 domain and numeric normalization frozen independently of ISONCS.
5. Undirected mirror reconstruction/dedup/conflict semantics frozen.
6. Semantic digest separated from artifact digest; writer identity required for artifact receipts.
7. **Pre-E3 golden corpus passes Python + TypeScript, including signed integer NodeIds.**
8. Reachable out-of-domain Semantic/2 failures named and covered.
9. **Semantic identity conformance and persistence conformance explicitly separated; Core persistence claims require round-trip Semantic/2 invariance.**

And the ID-twin fact becomes an E0/Core invariant rather than another Semantic/2 branch.

That last addition is probably the most important thing S7 surfaced:

> **Semantic/2 defines what a graph means. Core persistence conformance defines whether a particular implementation can preserve that meaning through its wire format.**

Those are related contracts, but they are not the same contract.

Yes. I would accept **S1–S6**. They tighten Semantic/2 in exactly the places where the current Core representation can otherwise make identity unstable.

The important conceptual correction from S1 is:

> **Semantic/2 normalizes the semantic domain that survives an ISONGraph round-trip—not every Python/JS value the in-memory API happens to accept.**

That should become normative.

### Semantic/2 value domain, revised

For v1 of the normal form:

```text
SemanticValue/2 ::=
      NULL
    | BOOL
    | INT64
    | FLOAT64
    | STRING
    | REF
```

`LIST` and `MAP` tags can be **reserved**, but MUST NOT be emitted.

An in-memory property such as:

```python
tags=["a", "b"]
```

is therefore outside the Semantic/2 domain and should fail identity construction rather than acquire one identity before serialization and another afterward.

The structural property bag of a node/edge is still map-shaped, of course:

```text
properties:
    name  -> STRING
    count -> INT64
    score -> FLOAT64
```

but **MAP is not itself a legal property value**.

Null-elision operates at that property-bag level:

```text
{ a: INT64(1), b: NULL }
```

canonicalizes its property set as:

```text
{ a: INT64(1) }
```

It is not relying on a nested MAP value.

---

## Numeric rule

I agree with S4. The corrected normalization is:

```text
BOOL?
    → BOOL

integer?
    → if int64: INT64
    → otherwise: VALUE_OUT_OF_DOMAIN

binary64?
    → non-finite: VALUE_OUT_OF_DOMAIN
    → ±0.0: INT64(0)

    → mathematically integral:
          if int64: INT64
          otherwise: VALUE_OUT_OF_DOMAIN

    → otherwise:
          FLOAT64 exact IEEE-754 binary64 bits
```

So:

```text
1
1.0
```

both become:

```text
INT64(1)
```

and:

```text
0
0.0
-0.0
```

become:

```text
INT64(0)
```

while both:

```text
integer 10**20
```

and an integral binary64 representation outside int64 are rejected.

That makes the boundary a property of the **semantic value**, not the source language type.

---

## S3: NaN/Infinity needs two treatments

You are right that Semantic/2 cannot repair Core after Core has destroyed type information.

Before persistence:

```text
float('nan')
```

is:

```text
FLOAT non-finite
→ VALUE_OUT_OF_DOMAIN
```

After the current lossy Core round-trip:

```text
"nan"
```

is simply:

```text
STRING("nan")
```

Semantic/2 cannot legitimately guess:

> maybe this string used to be a float.

So the normative position should be:

```text
Semantic/2 operates on the typed graph presented to it.
It never reconstructs lost types heuristically.
```

And independently:

> **Core non-finite-float round-trip is an upstream defect.**

For Ext, the practical guard is stronger: reject non-finite floats **before they enter an identity-bearing graph**.

That gives E0 a useful compatibility classification:

```text
Core-legal
but
Semantic/2-out-of-domain
```

rather than pretending Core's accepted domain and the semantic-identity domain are identical.

---

# S2: undirected normalization needs logical-edge reconstruction

Agreed.

For:

```text
directed = false
```

raw storage:

```text
A R B {w:1}
B R A {w:1}
```

must normalize to **one logical edge**.

The algorithm should be:

```text
canonical endpoints =
    min(NodeRef(A), NodeRef(B)),
    max(NodeRef(A), NodeRef(B))

logical address =
    (
      min_endpoint,
      relation,
      max_endpoint,
      ordinal
    )
```

Then group raw edge records by that canonical address.

For each group:

```text
1 record
    → accept as one logical edge

2 mirror records
+ identical normalized semantic properties
    → collapse to one logical edge

2 mirror records
+ differing semantic properties
    → REJECT

>2 records for one canonical address
    → REJECT unless a future encoding profile explicitly defines it
```

For a multigraph, `ordinal` separates logical parallel edges before mirror-pair collapse.

So:

```text
(A,R,B,"0")
(B,R,A,"0")
```

collapse together,

while:

```text
(A,R,B,"1")
(B,R,A,"1")
```

form another logical edge.

I would name the disagreement error:

```text
UNDIRECTED_EDGE_CONFLICT
```

because silently choosing one of:

```text
A→B {w:1}
B→A {w:2}
```

would make identity dependent on iteration order—the exact thing Semantic/2 is supposed to eliminate.

---

# S5: typed Node IDs need explicit treatment

Yes.

At minimum, assuming the current Core identifier contract is integer-or-string with bool excluded:

```text
NodeId/2 ::=
      INT64
    | STRING
```

Therefore:

```text
id = 1
```

and:

```text
id = "1"
```

are different identities.

They MUST NOT normalize via:

```text
str(id)
```

The canonical NodeRef is logically:

```text
NodeRef/2 {
    node_type: STRING
    node_id: NodeId/2
}
```

Edge reference text is not itself the semantic identity.

This:

```text
:p:1
```

must first resolve against the typed node table and only then enter `EdgeAddress/2`.

That exposes one additional stress case worth making explicit:

```text
nodes.p:
    INT64(1)
    STRING("1")
```

If the serialized edge-reference syntax cannot distinguish which one:

```text
:p:1
```

means, the graph is ambiguous for round-trip identity.

Semantic/2 should not guess.

I would add:

```text
AMBIGUOUS_NODE_REFERENCE
```

and put a golden vector around:

```text
int 1
vs
string "1"
```

both as standalone node identity and as edge endpoint resolution.

That may uncover another Core-level format constraint.

---

# S6: give failure a formal identity

Agreed.

I would put the general taxonomy at the Semantic/2 boundary:

```text
SemanticIdentityError
├── VALUE_OUT_OF_DOMAIN
├── AMBIGUOUS_NODE_REFERENCE
├── UNDIRECTED_EDGE_CONFLICT
├── INVALID_EDGE_ADDRESS
├── MISSING_GRAPH_SEMANTICS
└── UNSUPPORTED_SEMANTIC_VERSION
```

`VALUE_OUT_OF_DOMAIN` can carry a reason:

```text
NONFINITE_FLOAT
INTEGER_OUT_OF_INT64
INTEGRAL_FLOAT_OUT_OF_INT64
CONTAINER_PROPERTY
INVALID_UNICODE_SCALAR
...
```

This distinction is useful:

```text
error code = stable machine contract
reason     = specific diagnostic
```

Then Core being willing to store `10**20` doesn't imply Ext/Semantic/2 must manufacture identity for it.

Instead:

```text
Core graph: legal
Semantic/2 graph: identity unavailable
reason: VALUE_OUT_OF_DOMAIN / INTEGER_OUT_OF_INT64
```

That should indeed appear in E0 compatibility results, not first surface during E10/E11.

---

## Semantic/2 should now have three layers

I would structure the spec explicitly as:

```text
1. Value Normalization
   scalar domain
   numeric collapse
   null elision
   Unicode
   typed IDs / REFs

2. Logical Graph Normalization
   directed
   multigraph
   typed NodeRefs
   4-tuple EdgeAddress
   ordinal ordering
   undirected mirror collapse

3. Digest Encoding
   binary tags
   lengths
   record ordering
   semantic metadata
   SHA-256
```

That separation will make the vectors much easier to diagnose.

A parity failure then says whether we disagreed about:

```text
VALUE
GRAPH STRUCTURE
ENCODING
```

instead of just "digest mismatch."

---

## G-ID now has eight conditions

I would update the gate to:

1. `EdgeAddress/2 = (source, relation, target, ordinal)` frozen.
2. Ordinal is opaque string with exact UTF-8 byte ordering.
3. `directed` and `multigraph` are mandatory semantic inputs, never inferred.
4. **Semantic/2 scalar value domain and numeric normal form frozen independently of ISONCS.**
5. Undirected mirror-edge collapse/conflict semantics frozen.
6. Semantic digest separated from exact artifact digest; Core writer metadata mandatory for artifact receipt.
7. Golden identity corpus passes the reference implementation; full cross-language core corpus remains upstream-owned.
8. **Out-of-domain and ambiguous-Core-representation behavior is named, deterministic, and present in E0 compatibility invariants.**

And I would make **G-ID a hard prerequisite for E3**, as you suggested earlier.

The single sentence I would put at the top of the final Semantic/2 document is now even sharper:

> **Semantic/2 assigns identity only to the explicitly defined, round-trip-stable semantic subset of ISONGraph. Core acceptance of a value or representation does not imply that Semantic/2 can assign it an identity.**

That captures S1, S3, S4, S5, and S6 in one law.

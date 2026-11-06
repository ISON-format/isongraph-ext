Yes. At this point I would **freeze the remaining value model before E3**. Your warning about ISONCS is exactly right: **Semantic/2 must be self-contained and must not inherit canonicalization behavior from ISON/ISONCS by reference.**

Otherwise we fix F5 only to recreate the same failure one layer lower:

```text
ISONCS 1.x changes
        ↓
same graph
        ↓
different Semantic/2 identity
```

That cannot be allowed.

## I would lock `Semantic/2` like this

| Question                             | Semantic/2 decision           |
| ------------------------------------ | ----------------------------- |
| `1` vs `1.0`                         | **Same semantic value**       |
| `-0.0` vs `0`                        | **Same semantic value**       |
| Boolean `true` vs integer `1`        | **Different**                 |
| Integer domain                       | **signed int64**              |
| Integer outside int64                | **Reject**                    |
| NaN / ±Infinity                      | **Reject**                    |
| Object/map `null` member             | **Elide**                     |
| `null` inside a list                 | **Preserve**                  |
| Empty object/list                    | **Preserve**                  |
| List ordering                        | **Significant**               |
| Object key ordering                  | sort exact UTF-8 bytes        |
| NFC normalization                    | **None**                      |
| Lone Unicode surrogate               | **Reject**                    |
| Node/type/relation/ordinal strings   | exact Unicode scalar sequence |
| Ordinal ordering                     | exact UTF-8 lexicographic     |
| Simple-edge ordinal                  | `"0"`                         |
| Semantic digest dependence on writer | **None**                      |

The potentially surprising decision there is **no NFC normalization**. I think that's the safer contract.

Semantic identity should mean:

> same graph values,

not:

> values that a Unicode normalization algorithm considers canonically equivalent.

Automatic NFC would introduce another hidden dependency:

```text
Semantic/2
   ↓
Unicode normalization implementation/version
```

and can alter opaque IDs, code fragments, hashes, filenames, identifiers, etc.

So these two strings remain distinct:

```text
"\u00E9"
"e\u0301"
```

If an application wants normalized natural-language text, it normalizes **before binding the value into the graph**, under an explicit producer/domain policy.

That keeps Semantic/2 stable.

---

## Numeric normal form

This is where Python/JavaScript parity needs a precise rule.

Given number `v`:

```text
boolean?
   ↓
BOOL                 # checked before integer

integer?
   ↓
signed int64?
   ├── yes → INT64
   └── no  → REJECT

float64?
   ↓
finite?
   ├── no → REJECT
   │
   ↓
mathematically integral
and inside int64?
   ├── yes → INT64
   └── no  → FLOAT64 exact IEEE-754 bits
```

Therefore:

```text
1
1.0
1.000000
```

all normalize to:

```text
INT64(1)
```

and:

```text
-0.0
+0.0
0
```

all normalize to:

```text
INT64(0)
```

But:

```text
1.5
```

becomes a `FLOAT64` encoded using its exact IEEE-754 binary64 bits, not whatever decimal spelling Python or JavaScript happens to print.

That eliminates `repr()` / `toString()` from graph identity entirely.

---

## The JavaScript int64 trap

This needs a binding rule.

JavaScript `Number` cannot reliably carry every int64. Therefore the JS binding should reject:

```text
Number.isInteger(v)
&& !Number.isSafeInteger(v)
```

for untyped numeric input.

An integer larger than JS safe integer must arrive as:

```text
BigInt
```

or through an ISON integer parser that preserves the integer token exactly.

So:

```text
9223372036854775807n
```

can become:

```text
INT64_MAX
```

but blindly converting it to JS `Number` before Semantic/2 is a binding violation.

That's exactly the kind of error E11 should catch.

---

# Null semantics

I agree that null elision is effectively forced by the existing behavior.

Make it narrow and explicit:

```text
{
  "a": 1,
  "b": null
}
```

normalizes as:

```text
{
  "a": 1
}
```

But:

```text
[1, null, 2]
```

stays:

```text
[1, null, 2]
```

because list position is semantic.

Recursively:

```text
{
  "x": {
    "a": 1,
    "b": null
  }
}
```

becomes:

```text
{
  "x": {
    "a": 1
  }
}
```

An empty resulting object remains `{}`. It is not itself eliminated.

---

# Semantic/2 should not serialize through ISONCS at all

I would make its normal form binary and explicitly tagged.

Conceptually:

```text
NULL       00

FALSE      01
TRUE       02

INT64      03 + 8-byte signed BE

FLOAT64    04 + 8-byte IEEE754 BE

STRING     05 + length + UTF8

LIST       06 + count + normalized elements...

MAP        07 + count
               + UTF8-byte-sorted key/value pairs

REF        08 + type + id
```

That's illustrative tagging—the exact byte constants can be frozen in the spec.

Then:

```text
Semantic/2
```

depends on exactly one document:

> **The Semantic/2 specification.**

Not Python representation.

Not JavaScript stringification.

Not ISONCS.

Not `.isong` serialization.

ISON/ISONCS remain interchange/core concerns.

---

# F4 also fits cleanly into this

Semantic/2's graph header must require:

```text
directed: bool
multigraph: bool
```

No defaults.

For now:

```text
if meta.graph contains them:
    use core values
    receipt.source = "core-meta"
else:
    require explicit Ext binding
    receipt.source = "binding"
```

Never infer directedness from edge structure.

That allows G-ID to close before the six-port Core release.

Then Core can later make:

```text
meta.graph.directed
meta.graph.multigraph
```

universally available, at which point the binding fallback becomes compatibility behavior.

For undirected graphs, Semantic/2 should also canonicalize endpoint orientation:

```text
min(NodeRef(A), NodeRef(B))
max(NodeRef(A), NodeRef(B))
```

before constructing the edge address.

Otherwise:

```text
A — B
```

and:

```text
B — A
```

could digest differently despite being the same undirected edge.

Directed graphs preserve source/target exactly.

---

# Canonical edge address

With F7 and F6:

```text
EdgeAddress/2 =
(
    source_ref,
    relation_type,
    target_ref,
    ordinal
)
```

Simple graph API:

```text
(A, KNOWS, B)
```

normalizes to:

```text
(A, KNOWS, B, "0")
```

Multigraph:

```text
(A, KNOWS, B, "0")
(A, KNOWS, B, "1")
(A, KNOWS, B, "retry")
```

And ordinal ordering is deliberately:

```text
UTF8 byte order
```

so:

```text
"10" < "2"
```

Numeric ordinal semantics belong to the producer, which can zero-pad them.

---

# Then G-ID becomes completely crisp

Before E3 opens, I'd require these seven things:

1. 4-tuple EdgeAddress frozen.
2. Ordinal string/UTF-8 ordering frozen.
3. `directed` and `multigraph` mandatory Semantic/2 inputs with no defaults.
4. Semantic/2 value normal form frozen independently of ISONCS.
5. Semantic digest and artifact SHA-256 formally separated.
6. Core-writer identity required in artifact receipts, with no default.
7. Initial identity/value vector corpus passes Python and at least one independent implementation/parser before E11 expands it upstream.

F8's full cross-language corpus can still be upstream-owned, but **G-ID needs a small normative golden corpus immediately**. Otherwise E3 is implementing against prose.

The most important principle to write at the top of Semantic/2 should probably be:

> **Semantic/2 normalizes graph meaning, not graph serialization. Its identity rules are versioned and complete within this specification; no serializer, writer, Unicode normalizer, or language-native representation participates implicitly.**

That closes the exact class of identity drift you're pointing at.

"""Shared sample payload for the igpv tests. Digests are placeholders: wire/shape tests never touch bytes."""
from isongraph_ext.igpv.payload import ProvenancePayload
from isongraph_ext.igpv.records import Artifact, Attribution, Derivation, EdgeAddress, GraphObject, Locator, NodeRef, Producer

# Placeholders contain letters: an all-digit 64-char string is numeric-looking and the canonical writer would quote it.
SHA_T, SHA_D, SHA_G, SHA_P = "a0" * 32, "b1" * 32, "c2" * 32, "d3" * 32


def payload(**overrides) -> ProvenancePayload:
    base = dict(
        target_artifact_sha256=SHA_T, target_serialization_profile="ison-v1",
        artifacts=(Artifact("src0", SHA_D, "document", 100, media_type="text/plain"),
                   Artifact("g0", SHA_G, "isongraph", 50, serialization_profile="ison-v1")),
        producers=(Producer("x0", "extractor", "ext", "1.0.0"),
                   Producer("t0", "transformation", "isongraph-ext", "0.2.0", spec="IGDAG/1", policy_sha256=SHA_P)),
        objects=(GraphObject("G", "graph"), GraphObject("n1", "node", node=NodeRef("p", 1)),
                 GraphObject("n2", "node", node=NodeRef("p", "s1")),
                 GraphObject("e1", "edge", edge=EdgeAddress(NodeRef("p", 1), "knows", NodeRef("p", "s1"))),
                 GraphObject("o7", "node", graph="g0", node=NodeRef("p", 7)),
                 GraphObject("o8", "node", graph="g0", node=NodeRef("p", 8))),
        attributions=(Attribution("a0", "n1", "src0", "x0", Locator("bytes/1", 10, 20)),
                      Attribution("a1", "n2", "src0", "x0"),
                      Attribution("a2", "e1", "src0", "x0", Locator("lines/1", 2, 3)),
                      Attribution("a3", "G", "src0", "x0")),
        derivations=(Derivation("d0", "n1", "o7", "t0", "collapse"), Derivation("d1", "n1", "o8", "t0", "collapse")),
    )
    base.update(overrides)
    return ProvenancePayload(**base)


# Spec-literal oracle (18 §1 as clarified): blocks by kind.name; fields by name; rows by every column in that field
# order with nulls last (the canonical writer's rule); the "0" ordinal quoted; letters-containing hex bare.
REFERENCE_TEXT = (
    "meta.igpv\n"
    "provenance_spec target_artifact_sha256 target_semantic_digest target_semantic_digest_algorithm target_serialization_profile\n"
    f"IGPV/1 {SHA_T} null null ison-v1\n"
    "\n"
    "table.artifacts\n"
    "artifact_id artifact_sha256 kind media_type revision serialization_profile size uri\n"
    f"g0 {SHA_G} isongraph null null ison-v1 50 null\n"
    f"src0 {SHA_D} document text/plain null null 100 null\n"
    "\n"
    "table.attributions\n"
    "artifact_id attribution_id locator_end locator_start locator_text locator_type object_id producer_id\n"
    "src0 a0 20 10 null bytes/1 n1 x0\n"
    "src0 a1 null null null null n2 x0\n"
    "src0 a2 3 2 null lines/1 e1 x0\n"
    "src0 a3 null null null null G x0\n"
    "\n"
    "table.derivations\n"
    "derivation_id derived_object_id kind origin_object_id producer_id\n"
    "d0 n1 collapse o7 t0\n"
    "d1 n1 collapse o8 t0\n"
    "\n"
    "table.objects\n"
    "graph kind node_id node_type object_id ordinal relation source_id source_type target_id target_type\n"
    "g0 node 7 p o7 null null null null null null\n"
    "g0 node 8 p o8 null null null null null null\n"
    "null edge null null e1 \"0\" knows 1 p s1 p\n"
    "null graph null null G null null null null null null\n"
    "null node 1 p n1 null null null null null null\n"
    "null node s1 p n2 null null null null null null\n"
    "\n"
    "table.producers\n"
    "implementation kind policy_sha256 producer_id spec version\n"
    "ext extractor null x0 null 1.0.0\n"
    f"isongraph-ext transformation {SHA_P} t0 IGDAG/1 0.2.0"
)

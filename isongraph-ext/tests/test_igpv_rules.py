import pytest
from igpv_helpers import SHA_D, SHA_G, SHA_T, payload

from isongraph_ext.igpv.errors import IGPVError
from isongraph_ext.igpv.payload import check_references
from isongraph_ext.igpv.records import Artifact, Attribution, Derivation, EdgeAddress, GraphObject, Locator, NodeRef, Producer


def _p1(field, **kw):
    with pytest.raises(IGPVError) as info:
        payload(**kw).check()
    assert (info.value.code, info.value.step, info.value.field) == ("MALFORMED_PROVENANCE", "P1", field), info.value


def _p3(code, field, **kw):
    p = payload(**kw)
    p.check()
    with pytest.raises(IGPVError) as info:
        check_references(p)
    assert (info.value.code, info.value.step, info.value.field) == (code, "P3", field), info.value


def test_sample_payload_passes_both():
    p = payload()
    p.check()
    check_references(p)


def test_duplicate_keys_and_digests():
    a = payload().artifacts
    _p1("table.artifacts.src0.artifact_id", artifacts=a + (Artifact("src0", "9" * 64, "document", 1),))
    _p1("table.artifacts.src1.artifact_sha256", artifacts=a + (Artifact("src1", SHA_D, "document", 1),))
    _p1("table.producers.x0.producer_id", producers=payload().producers + (Producer("x0", "extractor", "e", "1"),))
    _p1("table.objects.n9.node_id", objects=payload().objects + (GraphObject("n9", "node", node=NodeRef("p", 1)),))
    _p1("table.attributions.a9.attribution_id", attributions=payload().attributions + (Attribution("a9", "n2", "src0", "x0"),))
    _p1("table.derivations.d9.origin_object_id", derivations=payload().derivations + (Derivation("d9", "n1", "o7", "t0", "collapse"),))


def test_twins_in_one_graph_rejected_but_allowed_across_graphs_and_types():
    objs = payload().objects
    _p1("table.objects.n9.node_id", objects=objs + (GraphObject("n9", "node", node=NodeRef("p", "1")),))          # twin of n1 via object row
    _p1("table.objects.e9.target_id", objects=objs + (GraphObject("e9", "edge", edge=EdgeAddress(NodeRef("p", "s1"), "r", NodeRef("p", "1"))),))  # twin via endpoint
    payload(objects=objs + (GraphObject("n9", "node", node=NodeRef("q", "1")),), attributions=payload().attributions + (Attribution("a9", "n9", "src0", "x0"),)).check()


def test_twin_inside_origin_graph_also_rejected():
    objs = payload().objects + (GraphObject("o9", "node", graph="g0", node=NodeRef("p", "7")),)
    _p1("table.objects.o9.node_id", objects=objs, derivations=payload().derivations + (Derivation("d9", "n1", "o9", "t0", "collapse"),))


def test_reachability():
    _p1("table.artifacts.src9.artifact_id", artifacts=payload().artifacts + (Artifact("src9", "9" * 64, "document", 1),))
    _p1("table.producers.p9.producer_id", producers=payload().producers + (Producer("p9", "extractor", "e", "1"),))
    _p1("table.objects.n9.object_id", objects=payload().objects + (GraphObject("n9", "node", node=NodeRef("p", 9)),))
    # an origin-graph artifact reached only through objects.graph of a derivation's origin is reachable
    p = payload(attributions=tuple(a for a in payload().attributions))
    p.check()
    # but an isongraph artifact whose only objects are unreferenced is not (artifacts are checked before objects)
    _p1("table.artifacts.g0.artifact_id", derivations=())


def test_locator_shape_uses_artifact_size():
    _p1("table.attributions.a0.locator_end", attributions=(Attribution("a0", "n1", "src0", "x0", Locator("bytes/1", 0, 101)),) + payload().attributions[1:])


def test_unresolved_references():
    # Every fixture keeps the original rows (so P1 reachability holds) and ADDS the dangling reference, or re-points a
    # row whose target stays referenced elsewhere: the first failure must be P3, never P1.
    _p3("UNRESOLVED_REFERENCE", "table.attributions.a9.object_id", attributions=payload().attributions + (Attribution("a9", "nX", "src0", "x0"),))
    _p3("UNRESOLVED_REFERENCE", "table.attributions.a0.producer_id", attributions=(Attribution("a0", "n1", "src0", "pX", Locator("bytes/1", 10, 20)),) + payload().attributions[1:])
    _p3("UNRESOLVED_REFERENCE", "table.attributions.a0.artifact_id", attributions=(Attribution("a0", "n1", "srcX", "x0"),) + payload().attributions[1:])
    _p3("UNRESOLVED_REFERENCE", "table.derivations.d0.producer_id", derivations=(Derivation("d0", "n1", "o7", "tX", "collapse"), payload().derivations[1]))
    arts = (Artifact("src0", SHA_D, "document", 100, media_type="text/plain"), Artifact("g0", SHA_G, "document", 50))
    _p3("UNRESOLVED_REFERENCE", "table.objects.o7.graph", artifacts=arts)


def test_invalid_derivations():
    objs = payload().objects
    d0, d1 = payload().derivations            # n1 <- o7, n1 <- o8 (collapse): keeping both keeps o7/o8 reachable at P1
    _p3("INVALID_DERIVATION", "table.derivations.d9.origin_object_id", derivations=(d0, d1, Derivation("d9", "n1", "n2", "t0", "collapse")))
    _p3("INVALID_DERIVATION", "table.derivations.d0.derived_object_id", derivations=(Derivation("d0", "o7", "o8", "t0", "collapse"),),
        attributions=payload().attributions + (Attribution("a9", "o8", "src0", "x0"),))
    same = (Artifact("src0", SHA_D, "document", 100), Artifact("g0", SHA_T, "isongraph", 50, serialization_profile="ison-v1"))
    _p3("INVALID_DERIVATION", "table.derivations.d0.origin_object_id", artifacts=same)
    _p3("INVALID_DERIVATION", "table.derivations.d0.origin_object_id", derivations=(Derivation("d0", "e1", "o7", "t0", "rewrite"), d1))
    _p3("INVALID_DERIVATION", "table.derivations.d0.kind", derivations=(Derivation("d0", "n1", "o7", "t0", "identity"), Derivation("d1", "n1", "o8", "t0", "identity")))
    _p3("INVALID_DERIVATION", "table.derivations.d0.kind", derivations=(Derivation("d0", "n2", "o7", "t0", "identity"), d1))   # single row, address differs
    # identity with equal address passes (o7/o8 stay reachable through n2's collapse rows)
    ok = payload(objects=objs + (GraphObject("o1", "node", graph="g0", node=NodeRef("p", 1)),),
                 derivations=(Derivation("d0", "n1", "o1", "t0", "identity"), Derivation("d1", "n2", "o7", "t0", "collapse"), Derivation("d2", "n2", "o8", "t0", "collapse")))
    ok.check()
    check_references(ok)

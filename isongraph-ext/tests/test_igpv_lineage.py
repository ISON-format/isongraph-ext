import pytest

from isongraph_ext.igpv.errors import IGPVError
from isongraph_ext.igpv.lineage import Lineage
from isongraph_ext.igpv.payload import ProvenancePayload
from isongraph_ext.igpv.records import Artifact, Attribution, Derivation, GraphObject, Limits, NodeRef, Producer

A, Bs, C, Dd = "a" * 64, "b" * 64, "c" * 64, "d" * 64
TR = Producer("t", "transformation", "isongraph-ext", "0.2.0", spec="IGP/1")
EX = Producer("x", "extractor", "ext", "1.0.0")


def chain(target: str, origins: dict[str, list[tuple[str, int, str]]], own: tuple[int, ...] = (1,), attributed: tuple[int, ...] = ()) -> ProvenancePayload:
    """Payload for `target` whose node p:1 derives from origins {graph_sha: [(kind, node_id, producer_id)]}; `own` lists target node ids that exist."""
    arts = [Artifact(f"g{i}", sha, "isongraph", 10, serialization_profile="ison-v1") for i, sha in enumerate(origins)]
    arts.append(Artifact("doc", Dd, "document", 10))
    objs = [GraphObject(f"n{i}", "node", node=NodeRef("p", i)) for i in own]
    ders, ats = [], [Attribution(f"at{i}", f"n{i}", "doc", "x") for i in attributed]
    k = 0
    for i, (sha, rows) in enumerate(origins.items()):
        for kind, nid, prod in rows:
            objs.append(GraphObject(f"o{k}", "node", graph=f"g{i}", node=NodeRef("p", nid)))
            ders.append(Derivation(f"d{k}", "n1", f"o{k}", prod, kind))
            k += 1
    if not ders and not ats:
        ats.append(Attribution("at1", "n1", "doc", "x"))
    used = {d.producer_id for d in ders} | {a.producer_id for a in ats}
    prods = tuple(p for p in (TR, EX) if p.producer_id in used)
    arts = [a for a in arts if a.artifact_id == "doc" and ats or a.artifact_id != "doc"]
    return ProvenancePayload(target, "ison-v1", tuple(arts), prods, tuple(objs), tuple(ats), tuple(ders))


def test_two_hop_chain_with_three_origins_in_canonical_order():
    pa = chain(A, {Bs: [("collapse", 1, "t"), ("collapse", 2, "t")]})       # A.p1 <- B.p1, B.p2
    pb = chain(Bs, {C: [("identity", 1, "t")]}, own=(1, 2), attributed=(2,))  # B.p1 <- C.p1 ; B.p2 attributed only
    steps = Lineage([pb, pa]).origins_of(A, NodeRef("p", 1))
    assert [(s.depth, s.graph_sha256, s.obj, s.kind, s.terminal) for s in steps] == [
        (1, Bs, NodeRef("p", 1), "collapse", None),
        (2, C, NodeRef("p", 1), "identity", None),
        (2, C, NodeRef("p", 1), None, "payload_unavailable"),
        (1, Bs, NodeRef("p", 2), "collapse", None),
        (1, Bs, NodeRef("p", 2), None, "no_derivation_record"),
    ]
    assert sum(1 for s in steps if s.kind) == 3
    assert steps[0].producer == TR


def test_root_terminals():
    pa = chain(A, {})
    assert Lineage([pa]).origins_of(A, NodeRef("p", 1)) == (Lineage([pa]).origins_of(A, NodeRef("p", 1))[0],)
    assert Lineage([pa]).origins_of(A, NodeRef("p", 1))[0].terminal == "no_derivation_record"
    assert Lineage([pa]).origins_of(Bs, NodeRef("p", 1))[0].terminal == "payload_unavailable"
    assert Lineage([pa]).origins_of(A, NodeRef("p", 9))[0].terminal == "no_derivation_record"   # unknown object: no record, no guess


def test_cycle_is_object_level():
    pa = chain(A, {Bs: [("rewrite", 1, "t")]})
    pb = chain(Bs, {A: [("rewrite", 1, "t")]})
    with pytest.raises(IGPVError) as info:
        Lineage([pa, pb]).origins_of(A, NodeRef("p", 1))
    assert (info.value.code, info.value.step) == ("DERIVATION_CYCLE", "L")
    pb2 = chain(Bs, {A: [("rewrite", 2, "t")]})          # B.p1 <- A.p2: revisits graph A via another object, no cycle
    steps = Lineage([pa, pb2]).origins_of(A, NodeRef("p", 1))
    assert [s.terminal for s in steps] == [None, None, "no_derivation_record"] and steps[1].obj == NodeRef("p", 2)


def test_ambiguous_target_and_budgets():
    pa = chain(A, {Bs: [("identity", 1, "t")]})
    with pytest.raises(IGPVError) as info:
        Lineage([pa, chain(A, {})])
    assert info.value.code == "LINEAGE_AMBIGUOUS"
    pb = chain(Bs, {C: [("identity", 1, "t")]})
    with pytest.raises(IGPVError) as info:
        Lineage([pa, pb], limits=Limits(max_lineage_depth=1)).origins_of(A, NodeRef("p", 1))
    assert (info.value.code, info.value.field) == ("LINEAGE_BUDGET_EXCEEDED", "max_lineage_depth")
    with pytest.raises(IGPVError) as info:
        Lineage([pa, pb], limits=Limits(max_lineage_visits=2)).origins_of(A, NodeRef("p", 1))
    assert (info.value.code, info.value.field) == ("LINEAGE_BUDGET_EXCEEDED", "max_lineage_visits")


def test_attributions_of_and_determinism():
    pb = chain(Bs, {C: [("identity", 1, "t")]}, own=(1, 2), attributed=(2,))
    assert [a.attribution_id for a in Lineage([pb]).attributions_of(Bs, NodeRef("p", 2))] == ["at2"]
    assert Lineage([pb]).attributions_of(Bs, NodeRef("p", 7)) == () and Lineage([pb]).attributions_of(A, None) == ()
    pa = chain(A, {Bs: [("collapse", 2, "t"), ("collapse", 1, "t")]})
    pa_rev = ProvenancePayload(A, "ison-v1", pa.artifacts, pa.producers, tuple(reversed(pa.objects)), pa.attributions, tuple(reversed(pa.derivations)))
    assert Lineage([pa, pb]).origins_of(A, NodeRef("p", 1)) == Lineage([pb, pa_rev]).origins_of(A, NodeRef("p", 1))

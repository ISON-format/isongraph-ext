import dataclasses
import hashlib

import pytest
from igp_helpers import INSTITUTIONAL, SUPPLY, graph_bytes, pol
from ison_graph import ISONGraph

from isongraph_ext import igpv
from isongraph_ext.igp import IGP_IMPLEMENTATION_VERSION, IGPError, Limits, project, verify_projection
from isongraph_ext.igpv import NodeRef

sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
KW = dict(serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")

CONTEXT = pol(("decision", "D-4"), mandatory=[("meeting", "2026-03-12")], node_types=("decision", "evidence", "meeting"),
              relations=("supports", "decided_at"), direction="both", depth=2, max_nodes=50)
IMPACT = pol(("supplier", "S-ACME"), node_types=("supplier", "facility", "component"), relations=("supplies", "produces"), direction="out", depth=3)


def nodes_of(result: bytes):
    return {(n.type, n.id) for n in ISONGraph.from_ison(result.decode("utf-8")).nodes()}


def test_institutional_context_scenario():
    r = project(INSTITUTIONAL, CONTEXT)
    assert nodes_of(r.result_bytes) == {("decision", "D-4"), ("decision", "D-9"), ("evidence", "FR-19"), ("evidence", "CM-3"), ("meeting", "2026-03-12")}
    assert dict(r.stats)["result_edges"] == 4 and not r.stats["truncated"]


def test_supply_chain_impact_scenario():
    r = project(SUPPLY, IMPACT)
    assert nodes_of(r.result_bytes) == {("supplier", "S-ACME"), ("facility", "F-LYON"), ("component", "C-HOUSING"), ("component", "C-SEAL")}


def test_result_is_an_ordinary_graph_and_properties_are_carried_exactly():
    src = graph_bytes([("p", 1, {"label": "café ☃", "n": 3, "x": 1.5, "ok": True, "gone": None}), ("p", "s")],
                      [("r", ("p", 1), ("p", "s"), {"w": 2})])
    r = project(src, pol(("p", 1), depth=1))
    assert r.result_bytes == src                                            # whole graph selected -> byte-identical to the Core writer's output
    g = ISONGraph.from_ison(r.result_bytes.decode("utf-8"))
    assert g.get_node("p", 1).properties["label"] == "café ☃" and g.directed


def test_deterministic_and_source_untouched():
    a, b = project(INSTITUTIONAL, CONTEXT), project(INSTITUTIONAL, CONTEXT.to_ison())
    assert a.result_bytes == b.result_bytes and a.payload.to_ison() == b.payload.to_ison()
    assert a.policy_sha256 == CONTEXT.digest


def test_lineage_is_identity_only_names_the_policy_and_version_and_has_no_graph_object():
    r = project(INSTITUTIONAL, CONTEXT)
    p = r.payload
    assert {d.kind for d in p.derivations} == {"identity"} and not [o for o in p.objects if o.kind == "graph"] and not p.attributions
    (prod,) = p.producers
    assert (prod.kind, prod.spec, prod.version, prod.policy_sha256) == ("transformation", "IGP/1", IGP_IMPLEMENTATION_VERSION, CONTEXT.digest)
    assert len(p.derivations) == 5 + 4 and len(p.objects) == 2 * (5 + 4)


def test_lineage_verifies_end_to_end_through_igpv_and_resolves_back_to_the_source():
    r = project(INSTITUTIONAL, CONTEXT)
    sources = {sha(INSTITUTIONAL): INSTITUTIONAL}
    b = igpv.bind(r.result_bytes, r.payload, sources=sources, **KW)
    _res, prov, dec = igpv.verify_and_admit(r.payload, b, r.result_bytes, sources=sources)
    assert dec.admitted and prov.origin_resolution == {"src": "verified"} and prov.object_resolution == "full"
    steps = igpv.Lineage([r.payload]).origins_of(sha(r.result_bytes), NodeRef("decision", "D-4"))
    assert [(s.depth, s.kind, s.graph_sha256) for s in steps[:1]] == [(1, "identity", sha(INSTITUTIONAL))]


def test_verify_projection_accepts_the_recomputation_and_returns_it():
    r = project(INSTITUTIONAL, CONTEXT)
    v = verify_projection(INSTITUTIONAL, CONTEXT.to_ison().encode("utf-8"), r.result_bytes, r.payload.to_ison())
    assert v.result_bytes == r.result_bytes


def test_verify_projection_rejections():
    r = project(INSTITUTIONAL, CONTEXT)

    def bad(code, result=None, payload=None, source=INSTITUTIONAL, policy=CONTEXT):
        with pytest.raises(IGPError) as info:
            verify_projection(source, policy, r.result_bytes if result is None else result, r.payload if payload is None else payload)
        assert (info.value.code, info.value.step) == (code, "Q4"), info.value

    bad("RESULT_MISMATCH", result=r.result_bytes + b"\n")
    bad("RESULT_MISMATCH", policy=dataclasses.replace(CONTEXT, depth=1))
    bad("LINEAGE_MISMATCH", payload=r.payload.to_ison() + "\n")                              # unparseable (non-canonical) payload
    short = dataclasses.replace(r.payload, derivations=tuple(d for d in r.payload.derivations if d.derivation_id != "dn0"),
                                objects=tuple(o for o in r.payload.objects if o.object_id not in ("n0", "o0")))
    short.check()                                                                            # a well-formed payload that is missing one element
    bad("LINEAGE_MISMATCH", payload=short)
    prod = dataclasses.replace(r.payload.producers[0], version="0.9.0")
    bad("IMPLEMENTATION_VERSION_MISMATCH", payload=dataclasses.replace(r.payload, producers=(prod,)))


def test_first_failure_wins_policy_before_source():
    with pytest.raises(IGPError) as info:
        project(b"not a graph", b"not a policy")
    assert (info.value.code, info.value.step) == ("POLICY_MALFORMED", "Q0")
    with pytest.raises(IGPError) as info:
        project(b"not a graph", pol(("p", 1)))
    assert (info.value.code, info.value.step) == ("SOURCE_UNSUPPORTED", "Q1")


def test_lineage_limits_rows_and_bytes():
    with pytest.raises(IGPError) as info:
        project(INSTITUTIONAL, CONTEXT, limits=Limits(lineage=igpv.Limits(max_rows_per_table=17)))              # needs 18 object rows
    assert (info.value.code, info.value.field, info.value.step) == ("PROJECTION_LIMIT_EXCEEDED", "max_rows_per_table", "Q3")
    with pytest.raises(IGPError) as info:
        project(INSTITUTIONAL, CONTEXT, limits=Limits(lineage=igpv.Limits(max_payload_bytes=200)))
    assert (info.value.code, info.value.field, info.value.step) == ("PROJECTION_LIMIT_EXCEEDED", "max_payload_bytes", "Q3")
    project(INSTITUTIONAL, CONTEXT, limits=Limits(lineage=igpv.Limits(max_rows_per_table=18)))                  # exactly at the ceiling is fine



def test_whole_graph_projection_uses_self_attribution_and_is_admitted_by_igpv():
    # IGPV/1 forbids a derivation from a graph to itself (18 section 3): a byte-identical projection is lineage by self-attribution (18 section 1.1).
    src = graph_bytes([("n", "a"), ("n", "b")], [("r", ("n", "a"), ("n", "b"))])
    r = project(src, pol(("n", "a"), depth=3, direction="both"))
    p = r.payload
    assert r.result_bytes == src and p.target_artifact_sha256 == p.artifacts[0].artifact_sha256 == sha(src)
    assert not p.derivations and [o.kind for o in p.objects] == ["graph"] and len(p.attributions) == 1
    (prod,) = p.producers
    assert (prod.version, prod.policy_sha256) == (IGP_IMPLEMENTATION_VERSION, pol(("n", "a"), depth=3, direction="both").digest)
    sources = {sha(src): src}
    b = igpv.bind(r.result_bytes, p, sources=sources, **KW)
    _res, _prov, dec = igpv.verify_and_admit(p, b, r.result_bytes, sources=sources)
    assert dec.admitted
    verify_projection(src, pol(("n", "a"), depth=3, direction="both"), r.result_bytes, p)
    assert [s.terminal for s in igpv.Lineage([p]).origins_of(sha(src), NodeRef("n", "a"))] == ["no_derivation_record"]


def test_verify_projection_reports_the_earliest_failing_step_first():
    good = project(INSTITUTIONAL, CONTEXT)
    garbage = b"garbage payload"
    for source, policy, step, code in ((INSTITUTIONAL, b"not a policy", "Q0", "POLICY_MALFORMED"), (b"not a graph", CONTEXT, "Q1", "SOURCE_UNSUPPORTED"),
                                       (INSTITUTIONAL, pol(("decision", "nope")), "Q2", "ANCHOR_NOT_FOUND"), (INSTITUTIONAL, CONTEXT, "Q4", "LINEAGE_MISMATCH")):
        with pytest.raises(IGPError) as info:
            verify_projection(source, policy, good.result_bytes + b"tamper", garbage)
        assert (info.value.step, info.value.code) == (step, code), info.value


def test_in_memory_policy_obeys_the_policy_byte_budget():
    for policy in (CONTEXT, CONTEXT.to_ison(), CONTEXT.to_ison().encode("utf-8")):
        with pytest.raises(IGPError) as info:
            project(INSTITUTIONAL, policy, limits=Limits(max_policy_bytes=10))
        assert (info.value.code, info.value.field, info.value.step) == ("PROJECTION_LIMIT_EXCEEDED", "max_policy_bytes", "Q0"), info.value

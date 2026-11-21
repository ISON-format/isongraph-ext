# isongraph-ext/tests/test_igdc_derive.py
# isongraph-ext/tests/test_igdc_derive.py
import pytest
from conftest import RETIRED, all_baselines
from igdm_helpers import bound, real_payload, target_graph

from isongraph_ext.igdc.derive import consume, derive
from isongraph_ext.igdc.errors import IGDCError
from isongraph_ext.igdc.verify import verify_hints
from isongraph_ext.igdm.errors import IGDMError
from isongraph_ext.igdm.records import NodeHints
from isongraph_ext.igpv.records import NodeRef


def test_consume_maps_ids_by_type_and_keeps_row_counts():
    t = target_graph()                      # nodes order:1 (int), order:"s1" (string); edge knows 1 -> s1
    p = real_payload(t)
    h = consume(p.to_ison(), bound(p, t), t)
    assert {r["node_id"] for r in h.nodes} == {"i:1", "s:s1"}
    assert {(r["source_id"], r["target_id"]) for r in h.edges} == {("i:1", "s:s1")}
    assert (len(h.nodes), len(h.edges), len(h.groups), len(h.members)) == (len(p.nodes), len(p.edges), len(p.groups), len(p.members))
    assert h.meta["target_directed"] == "true" and h.meta["target_multigraph"] == "false"
    verify_hints(h.to_ison())               # the derived document passes C0-C3


def test_derive_never_adds_verdict_fields():
    t = target_graph(); p = real_payload(t)
    h = consume(p.to_ison(), bound(p, t), t)
    assert not {"verdict", "admitted", "admission", "receipt", "verified"} & set(h.meta)


def test_x_roles_split_into_sibling_columns():
    t = target_graph()
    p = real_payload(t, nodes=(NodeHints(NodeRef("order", 1), role="x-betterify-risk"), NodeHints(NodeRef("order", "s1"), role="warning")),
                     edges=(), groups=(), members=())
    h = consume(p.to_ison(), bound(p, t), t)
    rows = {r["node_id"]: r for r in h.nodes}
    assert (rows["i:1"]["role"], rows["i:1"]["role_x"]) == (None, "x-betterify-risk")
    assert (rows["s:s1"]["role"], rows["s:s1"]["role_x"]) == ("warning", None)


def test_payload_digest_is_of_the_exact_bytes():
    from hashlib import sha256
    t = target_graph(); p = real_payload(t); raw = p.to_ison().encode()
    assert consume(raw, bound(p, t), t).meta["igdm_payload_sha256"] == sha256(raw).hexdigest()


def test_derivation_is_deterministic():
    t = target_graph(); p = real_payload(t); b = bound(p, t)
    assert consume(p.to_ison(), b, t).to_ison() == consume(p.to_ison(), b, t).to_ison()


def test_target_mismatch_propagates_unwrapped():
    t = target_graph(); p = real_payload(t, target_artifact_sha256="c0" * 32)
    with pytest.raises(IGDMError) as e:
        consume(p.to_ison(), bound(real_payload(t), t), t)
    assert e.value.code in ("PAYLOAD_DIGEST_MISMATCH", "TARGET_BINDING_MISMATCH")


def test_limited_resolution_refused():
    # a binding on a retired baseline whose Core runtime is not installed verifies as `limited` (recipe: tests/test_igdm_verify.py)
    import dataclasses
    B = all_baselines()
    t = target_graph(); p = real_payload(t)
    retired = dataclasses.replace(bound(p, t), core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256)
    with pytest.raises(IGDCError) as e:
        consume(p.to_ison(), retired, t, baselines=B)
    assert (e.value.code, e.value.step) == ("RESOLUTION_REQUIRED", "P0")


def test_c4_detects_a_valid_but_wrong_document():
    from isongraph_ext.igdc.verify import verify_derivation
    t = target_graph(); p = real_payload(t); b = bound(p, t)
    good = consume(p.to_ison(), b, t).to_ison()
    verify_derivation(good, p.to_ison().encode(), b, t)
    bad = good.replace("Order #1", "Order #2")
    with pytest.raises(IGDCError) as e:
        verify_derivation(bad, p.to_ison().encode(), b, t)
    assert (e.value.code, e.value.step) == ("DERIVATION_MISMATCH", "C4")


def test_the_derived_document_must_fit_the_hint_budget_p1():
    from isongraph_ext.igdm.records import Limits
    t = target_graph(); p = real_payload(t); b = bound(p, t); n = len(p.to_ison().encode())
    derived = len(consume(p.to_ison(), b, t).to_ison().encode())
    assert derived > n                                        # tagged ids and the _x siblings make the hint document larger than its payload
    with pytest.raises(IGDCError) as e:                       # the payload fits its budget exactly; its derivation does not: refused, never truncated
        consume(p.to_ison(), b, t, limits=Limits(max_payload_bytes=n))
    assert (e.value.code, e.value.field, e.value.step) == ("DATAMATICS_LIMIT_EXCEEDED", "max_payload_bytes", "P1")
    consume(p.to_ison(), b, t, limits=Limits(max_payload_bytes=derived))


def test_directedness_and_multigraph_facts_come_from_the_verified_target():
    from ison_graph import ISONGraph
    g = ISONGraph(directed=False)
    g.add_node("n", 1); g.add_node("n", "a"); g.add_edge("r", ("n", 1), ("n", "a"))
    t = g.to_ison().encode()
    p = real_payload(t, nodes=(NodeHints(NodeRef("n", 1), role="info"),), edges=(), groups=(), members=())
    assert consume(p.to_ison(), bound(p, t), t).meta["target_directed"] == "false"

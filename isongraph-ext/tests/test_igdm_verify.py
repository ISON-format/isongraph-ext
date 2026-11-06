import dataclasses

import pytest
from conftest import RETIRED, all_baselines
from igdm_helpers import bound, real_payload, sha, target_graph

from isongraph_ext.igdm.bind import bind, verify_and_admit
from isongraph_ext.igdm.errors import IGDMError
from isongraph_ext.igdm.records import EdgeHints, Group, Limits, Member, NodeHints
from isongraph_ext.igdm.verify import DatamaticsVerification, verify
from isongraph_ext.igpv.records import EdgeAddress, NodeRef
from isongraph_ext.igx.admit import AdmissionPolicy
from isongraph_ext.igx.binding import Capability
from isongraph_ext.igx.errors import IGXError

T = target_graph()
B = all_baselines()
N, S = NodeRef("order", 1), NodeRef("order", "s1")


def _ok(p=None, **kw):
    p = p or real_payload(T)
    return verify(p, bound(p, T), T, baselines=B, **kw)


def _fails(code, step, field=None, p=None, b=None, target=T, **kw):
    p = p or real_payload(T)
    b = b or bound(p, T)
    with pytest.raises(IGDMError) as info:
        verify(p, b, target, baselines=B, **kw)
    assert (info.value.code, info.value.step) == (code, step), info.value
    if field:
        assert info.value.field == field, info.value
    return info.value


def test_verify_ok():
    igx, dm = _ok()
    assert isinstance(dm, DatamaticsVerification) and igx.semantic_verification == "full"
    assert dm.object_resolution == "full" and dm.unrecognized_roles == () and dm.steps_passed == ("D0", "D1", "D2", "D3", "D4")
    assert dm.counts == {"nodes": 2, "edges": 1, "groups": 2, "members": 3} and dm.target_artifact_sha256 == sha(T)
    assert dm.payload_sha256 == real_payload(T).digest
    assert verify(real_payload(T).to_ison().encode("utf-8"), bound(real_payload(T), T), T, baselines=B)[1] == dm


def test_x_roles_reported():
    p = real_payload(T, nodes=(NodeHints(N, role="x-betterify-risk"), NodeHints(S, role="warning")))
    assert _ok(p)[1].unrecognized_roles == ("nodes.role:x-betterify-risk",)


def test_d0_rules():
    from isongraph_ext.igx.bind import bind as igx_bind
    p = real_payload(T)
    no_row = igx_bind(T, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")
    _fails("DATAMATICS_NOT_BOUND", "D0", "table.capabilities.igdm", p=p, b=no_row)
    excl = igx_bind(T, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact", capabilities=(Capability("igdm", "=2.0.0", "OPTIONAL", p.digest),))
    _fails("DATAMATICS_VERSION_UNSUPPORTED", "D0", p=p, b=excl)
    other = real_payload(T, nodes=(NodeHints(N, role="warning"), real_payload(T).nodes[1]))
    _fails("PAYLOAD_DIGEST_MISMATCH", "D0", "table.capabilities.igdm.payload_sha256", p=other, b=bound(p, T))
    with pytest.raises(IGXError):
        verify(p, dataclasses.replace(bound(p, T), core_vector_corpus_digest="c" * 64), T, baselines=B)


def test_preflight_and_budgets():
    p = real_payload(T)
    bad = dataclasses.replace(bound(p, T), core_vector_corpus_digest="c" * 64)
    _fails("DATAMATICS_LIMIT_EXCEEDED", "D1", "max_graph_bytes", p=p, b=bad, limits=Limits(max_graph_bytes=10))
    _fails("DATAMATICS_LIMIT_EXCEEDED", "D1", "max_payload_bytes", p=p, limits=Limits(max_payload_bytes=1))
    _fails("DATAMATICS_LIMIT_EXCEEDED", "D1", "max_rows_per_table", p=p, limits=Limits(max_rows_per_table=2))
    malformed = real_payload(T, target_artifact_sha256="XY" * 32)
    _fails("DATAMATICS_LIMIT_EXCEEDED", "D1", "max_graph_bytes", p=malformed, b=bound(real_payload(T), T), limits=Limits(max_graph_bytes=10))
    _fails("MALFORMED_DATAMATICS", "D1", "meta.igdm.target_artifact_sha256", p=malformed, b=bound(real_payload(T), T))


def test_d2_d3_d4():
    p = real_payload(T)
    other = T + b"\n"
    _fails("TARGET_BINDING_MISMATCH", "D2", "meta.igdm.target_artifact_sha256", p=p, b=dataclasses.replace(bound(p, T), artifact_sha256=sha(other)), target=other)
    p3 = real_payload(T, target_serialization_profile="isonl-v1")
    _fails("TARGET_BINDING_MISMATCH", "D2", "meta.igdm.target_serialization_profile", p=p3, b=bound(p3, T))
    _fails("UNRESOLVED_REFERENCE", "D3", "table.members.ghost/order:1.group_id", p=real_payload(T, members=real_payload(T).members + (Member("ghost", N),)))
    _fails("UNRESOLVED_OBJECT", "D4", "table.nodes.order:9.node_id", p=real_payload(T, nodes=real_payload(T).nodes + (NodeHints(NodeRef("order", 9), role="info"),)))
    _fails("UNRESOLVED_OBJECT", "D4", "table.edges.order:s1-knows-order:1#0.relation", p=real_payload(T, edges=(EdgeHints(EdgeAddress(S, "knows", N), role="info"),)))


def test_unresolved_member_names_member():
    # Review Focus 5: the failure names the member row, not a node row.
    p = real_payload(T, members=real_payload(T).members + (Member("region", NodeRef("order", 77)),))
    _fails("UNRESOLVED_OBJECT", "D4", "table.members.region/order:77.node_id", p=p)


def test_limited_mode_and_admission():
    p = real_payload(T)
    retired = dataclasses.replace(bound(p, T), core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256)
    igx, dm, decision = verify_and_admit(p, retired, T, baselines=B)
    assert igx.semantic_verification == "limited" and dm.object_resolution == "skipped" and (decision.admitted, decision.code) == (False, "STALE_BINDING")
    assert verify_and_admit(p, retired, T, baselines=B, policy=AdmissionPolicy(allow_retired_baselines=True))[2].admitted
    _igx, _dm, d = verify_and_admit(p, bound(p, T), T, baselines=B)
    assert d.admitted and d.receipt_posture == "OK"


def test_igpv_and_igdm_verify_independently_against_one_binding():
    # 19 §4.1: both payloads verify against the same graph and binding, each on its own.
    from isongraph_ext.igpv.payload import ProvenancePayload
    from isongraph_ext.igpv.records import Artifact, Attribution, GraphObject, Producer
    from isongraph_ext.igpv.verify import verify as igpv_verify
    from isongraph_ext.igx.bind import bind as igx_bind
    dm = real_payload(T)
    pv = ProvenancePayload(sha(T), "ison-v1", (Artifact("src0", "b1" * 32, "document", 10),), (Producer("x0", "extractor", "ext", "1.0.0"),),
                           (GraphObject("G", "graph"),), (Attribution("a0", "G", "src0", "x0"),), ())
    b = igx_bind(T, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact",
                 capabilities=(Capability("igpv", "^1", "REQUIRED", pv.digest), Capability("igdm", "^1", "REQUIRED", dm.digest)))
    assert igpv_verify(pv, b, T, baselines=B)[1].steps_passed[-1] == "P5"
    assert verify(dm, b, T, baselines=B)[1].steps_passed[-1] == "D4"


def test_bind():
    p = real_payload(T)
    b = bind(T, p, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")
    assert [c for c in b.capabilities if c.extension == "igdm"] == [Capability("igdm", "^1", "REQUIRED", p.digest)]
    with pytest.raises(IGDMError) as info:
        bind(T, p, capabilities=(Capability("igdm", "^1", "REQUIRED", p.digest),), serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")
    assert info.value.code == "MALFORMED_DATAMATICS"
    with pytest.raises(IGDMError) as info:
        bind(T + b"\n", p, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")
    assert (info.value.code, info.value.step) == ("TARGET_BINDING_MISMATCH", "D2")

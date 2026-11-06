import dataclasses

import pytest
from conftest import RETIRED, all_baselines
from igpv_helpers import bound, doc_bytes, origin_graph, real_payload, target_graph

from isongraph_ext.igpv.bind import bind, verify_and_admit
from isongraph_ext.igpv.errors import IGPVError
from isongraph_ext.igpv.records import Attribution, Locator
from isongraph_ext.igx.admit import AdmissionPolicy
from isongraph_ext.igx.binding import Capability
from isongraph_ext.igx.errors import IGXError

T, O, D = target_graph(), origin_graph(), doc_bytes()
B = all_baselines()
KW = dict(serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")


def test_bind_appends_the_igpv_row_and_returns_a_verifiable_binding():
    p = real_payload(T, O, D)
    b = bind(T, p, **KW)
    row = [c for c in b.capabilities if c.extension == "igpv"]
    assert row == [Capability("igpv", "^1", "REQUIRED", p.digest)]
    b2 = bind(T, p, requirement="OPTIONAL", capabilities=(Capability("x-other", "^2", "OPTIONAL", None),), **KW)
    assert [c.extension for c in b2.capabilities] == ["x-other", "igpv"] and b2.capabilities[1].requirement == "OPTIONAL"
    result, prov, decision = verify_and_admit(p, b, T, baselines=B)
    assert decision.admitted and decision.receipt_posture == "OK" and prov.object_resolution == "full"


def test_bind_refuses_wrong_target_or_profile_or_duplicate_row():
    p = real_payload(T, O, D)
    with pytest.raises(IGPVError) as info:
        bind(O, p, **KW)
    assert (info.value.code, info.value.step) == ("TARGET_BINDING_MISMATCH", "P2")
    with pytest.raises(IGPVError) as info:
        bind(T, p, capabilities=(Capability("igpv", "^1", "REQUIRED", p.digest),), **KW)
    assert (info.value.code, info.value.field) == ("MALFORMED_PROVENANCE", "table.capabilities.igpv")
    with pytest.raises(IGPVError) as info:
        bind(T, p, requirement="MAYBE", **KW)
    assert info.value.code == "MALFORMED_PROVENANCE"
    with pytest.raises(IGXError):      # IGX refuses before any provenance step: unknown producer port
        bind(T, p, serialization_profile="ison-v1", producer_port="cobol", identity_claim="artifact")


def test_verify_and_admit_returns_the_bindings_decision_without_raising():
    p = real_payload(T, O, D)
    b = bound(p, T)
    retired = dataclasses.replace(b, core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256)
    result, prov, decision = verify_and_admit(p, retired, T, baselines=B)
    assert result.semantic_verification == "limited" and prov.object_resolution == "skipped"
    assert (decision.admitted, decision.code, decision.step) == (False, "STALE_BINDING", "A1")
    _r, _p, d2 = verify_and_admit(p, retired, T, baselines=B, policy=AdmissionPolicy(allow_retired_baselines=True))
    assert d2.admitted


def test_verification_failure_raises_before_admission():
    p = real_payload(T, O, D)
    # a different but valid payload (every row still reachable), bound against p's binding -> P0 digest mismatch
    other = real_payload(T, O, D, attributions=real_payload(T, O, D).attributions[:3] + (Attribution("a3", "G", "src0", "x0", Locator("bytes/1", 0, 1)),))
    with pytest.raises(IGPVError) as info:
        verify_and_admit(other, bound(p, T), T, baselines=B)
    assert info.value.code == "PAYLOAD_DIGEST_MISMATCH"

# isongraph-ext/tests/test_igar_issue.py
import dataclasses

import pytest
from conftest import RETIRED, all_baselines
from igdm_helpers import bound, real_payload, sha, target_graph

from isongraph_ext.igar.issue import issue
from isongraph_ext.igar.profile import Profile
from isongraph_ext.igar.receipt import Receipt, passed
from isongraph_ext.igdm.records import Limits
from isongraph_ext.igx.admit import AdmissionPolicy

T = target_graph()


def prof(**over) -> Profile:
    """A profile that differs from the default only where the test says so (the single statement of effective configuration)."""
    return dataclasses.replace(Profile.default(), **over)


def run(p=None, binding=None, payload=None, target=T, **kw):
    p = p or real_payload(T)
    b = (binding or bound(p, T)).to_ison().encode() if not isinstance(binding, bytes) else binding
    return issue(b, payload if payload is not None else p.to_ison().encode(), target, verifier_version="test", **kw)


def test_verified_and_admitted_receipt_records_the_profile_it_ran_under():
    r = run()
    r.check_consistency()
    assert passed(r) and r.result["admission"] == "admitted" and r.result["consumption"] == "absent"
    assert (r.verifier["semantic_verification"], r.verifier["object_resolution"]) == ("full", "full")
    assert r.verifier["verifier_version"] == "test" and r.verifier["runtime_ison_graph"] == "1.4.1" and r.verifier["runtime_ison_py"] == "1.2.0"
    assert r.subject["target_artifact_sha256"] == sha(T)
    assert r.verifier["profile_sha256"] == Profile.default().digest


def test_receipt_bytes_are_deterministic_and_round_trip():
    a, b = run().to_ison(), run().to_ison()
    assert a == b and Receipt.from_ison(a).to_ison() == a


def test_default_verifier_version_is_the_package_version():
    import isongraph_ext
    r = issue(bound(real_payload(T), T).to_ison().encode(), real_payload(T).to_ison().encode(), T)
    assert r.verifier["verifier_version"] == isongraph_ext.__version__


def test_a_different_configuration_gives_a_different_profile_digest_and_so_a_different_receipt():
    base = run()
    tight = run(profile=prof(limits=Limits(max_group_depth=3)))
    assert tight.verifier["profile_sha256"] != base.verifier["profile_sha256"] and tight.to_ison() != base.to_ison()
    lax = run(profile=prof(policy=AdmissionPolicy(allow_retired_baselines=True)))
    assert lax.verifier["profile_sha256"] != base.verifier["profile_sha256"]


def test_target_mismatch_is_a_receipt_not_an_exception():
    p = real_payload(T, target_artifact_sha256="c0" * 32)
    r = run(p=p)
    r.check_consistency()
    assert (r.failure["check"], r.failure["code"]) == ("D2", "TARGET_BINDING_MISMATCH") and r.result["admission"] == "not_evaluated" and not passed(r)


def test_malformed_binding_still_receipted_with_its_profile():
    junk = b"this is not ison"
    r = issue(junk, real_payload(T).to_ison().encode(), T, verifier_version="test")
    r.check_consistency()
    assert (r.failure["check"], r.result["binding_schema"], r.verifier["core_commit"]) == ("V1", "invalid", None)
    assert r.subject["binding_sha256"] == sha(junk) and r.verifier["profile_sha256"] == Profile.default().digest


def test_payload_shape_fault_is_D0_or_D1():
    r = run(p=real_payload(T), payload=b"not a datamatics payload")
    r.check_consistency()
    assert r.failure["check"] in ("D0", "D1")


def test_oversize_payload_preflight_is_D1_limit_under_the_profile_limits():
    r = run(profile=prof(limits=Limits(max_payload_bytes=10)))
    r.check_consistency()
    assert (r.failure["check"], r.failure["code"], r.result["payload_schema"]) == ("D1", "DATAMATICS_LIMIT_EXCEEDED", "invalid")


def test_unknown_baseline_is_V2():
    p = real_payload(T)
    b = dataclasses.replace(bound(p, T), core_commit="4" * 40)
    r = run(p=p, binding=b)
    r.check_consistency()
    assert (r.failure["check"], r.failure["code"]) == ("V2", "CORE_BASELINE_UNSUPPORTED")


def test_limited_run_is_never_reported_full_and_admission_is_denied_stale():
    B = all_baselines()
    p = real_payload(T)
    retired = dataclasses.replace(bound(p, T), core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256)
    r = run(p=p, binding=retired, profile=prof(baselines=B))
    r.check_consistency()
    assert (r.verifier["semantic_verification"], r.verifier["object_resolution"]) == ("limited", "skipped")
    assert (r.result["admission"], r.admission["code"], r.admission["step"], r.admission["receipt_posture"]) == ("denied", "STALE_BINDING", "A1", "INADMISSIBLE")


def test_unrecognized_roles_reported():
    from isongraph_ext.igdm.records import NodeHints
    from isongraph_ext.igpv.records import NodeRef
    p = real_payload(T, nodes=(NodeHints(NodeRef("order", 1), role="x-betterify-risk"),), edges=(), groups=(), members=())
    assert run(p=p).unrecognized == ("nodes.role:x-betterify-risk",)


def test_issue_accepts_bytes_only():
    with pytest.raises(TypeError):
        issue("text", b"", b"")


def test_issue_takes_no_loose_configuration_arguments():
    with pytest.raises(TypeError):
        issue(b"", b"", b"", limits=Limits())                      # the profile is the single statement of the effective configuration


def test_igdc_digest_recorded_when_requested_and_failure_recorded_when_not_derivable():
    B = all_baselines()
    p = real_payload(T)
    ok = run(p=p, igdc=True)
    ok.check_consistency()
    assert ok.result["consumption"] == "derived" and ok.subject["igdc_sha256"] is not None
    retired = dataclasses.replace(bound(p, T), core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256)
    lim = run(p=p, binding=retired, igdc=True, profile=prof(baselines=B, policy=AdmissionPolicy(allow_retired_baselines=True)))
    lim.check_consistency()
    assert (lim.result["consumption"], lim.consumption["code"], lim.consumption["step"]) == ("failed", "RESOLUTION_REQUIRED", "P0")


@pytest.mark.parametrize("bad", [0, b"", {}, "x", [], False, Profile.default().to_ison()])
def test_a_non_profile_profile_is_a_type_error_and_never_silently_defaulted(bad):
    p = real_payload(T)
    with pytest.raises(TypeError, match="profile must be Profile or None"):
        issue(bound(p, T).to_ison().encode(), p.to_ison().encode(), T, profile=bad)           # falsy values used to fall back to the default profile


def test_an_explicit_none_profile_is_the_default_profile_and_a_bytearray_input_is_accepted():
    p = real_payload(T)
    b, pl = bound(p, T).to_ison().encode(), p.to_ison().encode()
    assert issue(b, pl, T, profile=None, verifier_version="t").to_ison() == issue(bytearray(b), bytearray(pl), bytearray(T), verifier_version="t").to_ison()
    with pytest.raises(TypeError, match="bytes or bytearray"):
        issue("text", pl, T)

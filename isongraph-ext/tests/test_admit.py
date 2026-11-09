import pytest
from conftest import LOSSY, RECEIPT_SHA, RETIRED, all_baselines, graph_bytes, make_binding

from isongraph_ext.igx.admit import DEFAULT_POLICY, AdmissionPolicy, AdmissionResult, admit, verify_and_admit
from isongraph_ext.igx.binding import Consumer
from isongraph_ext.igx.digest import sha256_hex
from isongraph_ext.igx.errors import IGXError
from isongraph_ext.igx.verify import verify

B = all_baselines()
SRC = graph_bytes("ids/positive-int.ison")


def _admit(binding, source=SRC, policy=DEFAULT_POLICY):
    return admit(binding, verify(binding, source, baselines=B), policy=policy, baselines=B)


def _ts(**kw):
    return make_binding(producer_port="ts", core_writer_implementation="isongraph-ts", source_canonical="unverified",
                        producer_core_posture="KNOWN_DEFECT", core_conformance_receipt=RECEIPT_SHA["ts"], **kw)


def test_admitted_producer_bound():
    r = _admit(make_binding())
    assert r == AdmissionResult(True, None, None, "OK", ())


def test_admitted_artifact_and_none():
    assert _admit(make_binding(identity_claim="artifact")).admitted
    assert _admit(make_binding(identity_claim="none")).admitted
    assert _admit(_ts(identity_claim="artifact")).admitted          # KNOWN_DEFECT producer may still claim bytes


def test_a1_stale_binding_and_policy_override():
    b = make_binding(core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256, identity_claim="artifact")
    r = _admit(b)
    assert (r.admitted, r.code, r.step, r.receipt_posture) == (False, "STALE_BINDING", "A1", "INADMISSIBLE")
    assert "BASELINE_RETIRED" in r.reasons
    assert _admit(b, policy=AdmissionPolicy(allow_retired_baselines=True)).admitted


def test_a2_known_defect_producer_bound_denied():
    r = _admit(_ts())
    assert (r.admitted, r.code, r.step) == (False, "IDENTITY_CLAIM_INADMISSIBLE", "A2")
    assert "CORE_BLOCKING_DIVERGENCE" in r.reasons and r.receipt_posture == "INADMISSIBLE"


def test_a2_ineligible_source_denied_but_artifact_ok():
    src = graph_bytes("values/int-beyond-int64.ison")
    b = make_binding(artifact_sha256=sha256_hex(src), source_semantic_eligibility="ineligible", source_semantic_reason="INTEGER_OUT_OF_INT64")
    r = _admit(b, src)
    assert (r.admitted, r.code) == (False, "IDENTITY_CLAIM_INADMISSIBLE") and "SOURCE_NOT_ELIGIBLE:INTEGER_OUT_OF_INT64" in r.reasons
    assert _admit(make_binding(artifact_sha256=sha256_hex(src), identity_claim="artifact",
                               source_semantic_eligibility="ineligible", source_semantic_reason="INTEGER_OUT_OF_INT64"), src).admitted


def test_a2_multigraph_source_denied():
    src = graph_bytes("structure/multigraph-document.ison")
    b = make_binding(artifact_sha256=sha256_hex(src), source_semantic_eligibility="ineligible", source_semantic_reason="MULTIGRAPH_DOCUMENT")
    assert "SOURCE_NOT_ELIGIBLE:MULTIGRAPH_DOCUMENT" in _admit(b, src).reasons


def test_a2_cross_port_reserved():
    r = _admit(make_binding(identity_claim="cross_port", consumer=Consumer("ts", "1.4.1", "KNOWN_DEFECT", RECEIPT_SHA["ts"])))
    assert (r.admitted, r.code) == (False, "IDENTITY_CLAIM_INADMISSIBLE") and "SEMANTIC2_NOT_FROZEN" in r.reasons
    r2 = _admit(make_binding(identity_claim="cross_port"))
    assert {"SEMANTIC2_NOT_FROZEN", "CONSUMER_REQUIRED"} <= set(r2.reasons)


def test_a2_lossy_producer_bound_reserved_and_policy_field_ignored():
    b = make_binding(core_commit=LOSSY, producer_core_posture="LOSSY_KNOWN", core_conformance_receipt=B[LOSSY].receipts["python"].sha256)
    r = _admit(b)
    assert (r.admitted, r.code) == (False, "IDENTITY_CLAIM_INADMISSIBLE") and "LOSSY_PRODUCER_BOUND_RESERVED" in r.reasons
    r2 = _admit(b, policy=AdmissionPolicy(accept_lossy_domains=frozenset({"binary64-inexact-int"})))
    assert not r2.admitted and {"LOSSY_PRODUCER_BOUND_RESERVED", "POLICY_FIELD_RESERVED"} <= set(r2.reasons)


def test_a2_partial_producer_denied():
    b = make_binding(producer_port="rust", core_writer_implementation="isongraph-rs", source_canonical="unverified",
                     producer_core_posture="PARTIAL", core_conformance_receipt=RECEIPT_SHA["rust"])
    assert "PRODUCER_POSTURE_PARTIAL" in _admit(b).reasons


def test_a3_consumer_known_defect_reported():
    r = _admit(make_binding(consumer=Consumer("ts", "1.4.1", "KNOWN_DEFECT", RECEIPT_SHA["ts"])))
    assert r.admitted and r.receipt_posture == "CORE_BLOCKING_DIVERGENCE" and "CONSUMER_POSTURE_KNOWN_DEFECT" in r.reasons


def test_a3_consumer_full_is_ok():
    r = _admit(make_binding(consumer=Consumer("python", "1.4.1", "FULL", RECEIPT_SHA["python"])))
    assert r.receipt_posture == "OK"


def test_a0_result_for_another_binding_is_refused():
    eligible = make_binding()
    other_src = graph_bytes("values/int-beyond-int64.ison")
    other = make_binding(artifact_sha256=sha256_hex(other_src), source_semantic_eligibility="ineligible", source_semantic_reason="INTEGER_OUT_OF_INT64")
    good_result = verify(eligible, SRC, baselines=B)
    with pytest.raises(IGXError) as info:
        admit(other, good_result, baselines=B)           # eligible evidence smuggled onto an ineligible binding
    assert (info.value.code, info.value.step) == ("VERIFICATION_RESULT_MISMATCH", "A0")


def test_verify_and_admit_is_the_safe_path():
    r, d = verify_and_admit(make_binding(), SRC, baselines=B)
    assert r.binding_digest == make_binding().digest and d.admitted


def test_a2_limited_verification_denies_producer_bound_but_not_artifact():
    pb = make_binding(core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256)
    r = _admit(pb, policy=AdmissionPolicy(allow_retired_baselines=True))
    assert (r.admitted, r.code, r.step) == (False, "IDENTITY_CLAIM_INADMISSIBLE", "A2") and "SEMANTIC_REVERIFICATION_UNAVAILABLE" in r.reasons
    art = make_binding(core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256, identity_claim="artifact")
    assert _admit(art, policy=AdmissionPolicy(allow_retired_baselines=True)).admitted


def test_a3_lossy_known_consumer_is_reported_as_core_lossy():
    rc = B[LOSSY].receipts["python"].sha256
    r = _admit(make_binding(core_commit=LOSSY, producer_core_posture="LOSSY_KNOWN", core_conformance_receipt=rc,
                            identity_claim="artifact", consumer=Consumer("python", "1.4.1", "LOSSY_KNOWN", rc)))
    assert r.admitted and r.receipt_posture == "CORE_LOSSY" and "CONSUMER_POSTURE_LOSSY_KNOWN" in r.reasons


def test_a2_unclassified_source_is_named_in_a_producer_bound_denial():
    junk = b"not ison :::"
    kw = dict(artifact_sha256=sha256_hex(junk), source_semantic_eligibility="unclassified", source_semantic_reason=None)
    r = _admit(_ts(**kw), junk)
    assert not r.admitted and "SOURCE_UNCLASSIFIED" in r.reasons
    assert _admit(_ts(identity_claim="artifact", **kw), junk).admitted

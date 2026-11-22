# isongraph-ext/tests/test_igar_trust.py
"""Policy qualification (R4), delivery pins (R5) and authorize_hints (rev 2 finding F1): a policy match alone is never trusted admission."""
import dataclasses

import pytest
from igar_helpers import CORE, H, rejected_d2, verified
from igdm_helpers import bound, real_payload, sha, target_graph

from isongraph_ext.igar.errors import IGARError
from isongraph_ext.igar.issue import issue
from isongraph_ext.igar.profile import Profile
from isongraph_ext.igar.trust import DeliveryPins, TrustedAdmission, TrustPolicy, authorize_hints, qualify_policy
from isongraph_ext.igdc.derive import consume
from isongraph_ext.igdm.records import Limits

PROFILE_D = H("d")
OK = TrustPolicy(verifiers=frozenset({("isongraph-ext", "0.4.1")}), core_commits=frozenset({CORE}), profiles=frozenset({PROFILE_D}))


def why(r, policy, step="R4", code_="RECEIPT_POLICY_UNSATISFIED"):
    with pytest.raises(IGARError) as e:
        qualify_policy(r, policy)
    assert (e.value.code, e.value.step) == (code_, step)
    return e.value.field


def mut(r, block, **kv):
    return dataclasses.replace(r, **{block: {**getattr(r, block), **kv}})


# ---- qualify_policy (R4): a statement about the receipt's CLAIMS only --------------------------------------------------------
def test_matching_policy_qualifies_a_passed_receipt_and_claims_nothing_else():
    assert qualify_policy(verified(), OK) is None                          # None: it asserts no trust, no provenance, no byte match


def test_empty_policy_accepts_nothing():
    assert why(verified(), TrustPolicy(frozenset(), frozenset(), frozenset())) == "verifier"


def test_rejected_receipt_never_qualifies_under_any_policy():
    permissive = TrustPolicy(OK.verifiers, OK.core_commits, OK.profiles, require_admission=False, require_full_resolution=False)
    assert why(rejected_d2(), permissive) == "verification"


def test_dimensions_report_the_first_unsatisfied_field_in_the_documented_order():
    assert why(mut(verified(), "verifier", verifier_version="9.9"), OK) == "verifier"
    assert why(mut(verified(), "verifier", profile_sha256=H("e")), OK) == "profile"
    assert why(mut(verified(), "verifier", core_commit="f" * 40), OK) == "core_commit"
    assert why(verified(), dataclasses.replace(OK, runtime=frozenset({("1.0", "1.0")}))) == "runtime"
    denied = mut(mut(verified(), "result", admission="denied"), "admission", code="STALE_BINDING", step="A1", receipt_posture="INADMISSIBLE")
    assert why(denied, OK) == "admission"
    qualify_policy(denied, dataclasses.replace(OK, require_admission=False))


def test_limited_receipt_fails_full_resolution_policy():
    lim = mut(verified(), "verifier", semantic_verification="limited", object_resolution="skipped")
    assert why(lim, OK) == "resolution"
    qualify_policy(lim, dataclasses.replace(OK, require_full_resolution=False))


def test_a_policy_cannot_be_built_without_naming_profiles():
    with pytest.raises(TypeError):
        TrustPolicy(OK.verifiers, OK.core_commits)                         # type: ignore[call-arg]


# ---- DeliveryPins ---------------------------------------------------------------------------------------------------------------
def test_pins_are_validated_and_read_only_for_named_files():
    assert DeliveryPins.of(H("a")).receipts == frozenset({H("a")})
    with pytest.raises(IGARError) as e:
        DeliveryPins.of("xyz")
    assert e.value.code == "MALFORMED_PINS"
    sums = f"{H('a')}  graph.igar.ison\n{H('b')}  graph.ison\n"
    assert DeliveryPins.from_sha256sums(sums, names=frozenset({"graph.igar.ison"})).receipts == frozenset({H("a")})
    for bad, names in ((sums, frozenset({"missing.ison"})), ("not a line\n", frozenset()), (sums + f"{H('c')}  graph.ison\n", frozenset({"graph.ison"}))):
        with pytest.raises(IGARError) as e:
            DeliveryPins.from_sha256sums(bad, names=names)
        assert e.value.code == "MALFORMED_PINS"


# ---- authorize_hints: pinned AND bound AND policy-fit AND passed, all for the hints actually held ------------------------------
T = target_graph()
P = real_payload(T)
B = bound(P, T)
BIND, PAY = B.to_ison().encode(), P.to_ison().encode()
HINTS = consume(PAY, B, T).to_ison().encode()
RD = issue(BIND, PAY, T, igdc=True, verifier_version="test")
RAW = RD.to_ison().encode()
POLICY = TrustPolicy(frozenset({("isongraph-ext", "test")}), frozenset({RD.verifier["core_commit"]}), frozenset({Profile.default().digest}))
PINS = DeliveryPins.of(sha(RAW))


def auth(**over):
    kw = dict(receipt=RAW, pins=PINS, target=T, binding=BIND, payload=PAY, igdc=HINTS, policy=POLICY)
    kw.update(over)
    return authorize_hints(**kw)


def refused(**over):
    with pytest.raises(IGARError) as e:
        auth(**over)
    return e.value.code, e.value.step


def test_a_pinned_bound_policy_fit_receipt_authorizes_exactly_these_hints():
    a = auth()
    assert isinstance(a, TrustedAdmission)
    assert (a.receipt_sha256, a.igdc_sha256, a.target_artifact_sha256) == (sha(RAW), sha(HINTS), sha(T))
    assert (a.verifier, a.verifier_version, a.profile_sha256) == ("isongraph-ext", "test", Profile.default().digest)


def test_the_finding_f1_scenario_a_policy_match_without_provenance_is_not_trusted():
    # an attacker writes a perfectly consistent, policy-satisfying receipt for the REAL bytes and nobody pinned it
    forged = issue(BIND, PAY, T, igdc=True, verifier_version="test")                        # same bytes as RAW here; the point is the PIN
    qualify_policy(forged, POLICY)                                                           # policy match: fine ...
    assert refused(pins=DeliveryPins.of(H("a"))) == ("RECEIPT_NOT_PINNED", "R5")             # ... and still not authorized
    assert refused(pins=DeliveryPins(frozenset())) == ("RECEIPT_NOT_PINNED", "R5")


def test_nothing_unpinned_is_ever_parsed():
    assert refused(receipt=b"\xff\xfe not a receipt", pins=PINS) == ("RECEIPT_NOT_PINNED", "R5")


def test_oversize_receipt_is_refused_before_hashing_or_parsing():
    assert refused(limits=Limits(max_payload_bytes=10)) == ("RECEIPT_LIMIT_EXCEEDED", "R0")


@pytest.mark.parametrize("missing", ["receipt", "pins", "target", "binding", "payload", "igdc", "policy"])
def test_every_input_is_required(missing):
    kw = dict(receipt=RAW, pins=PINS, target=T, binding=BIND, payload=PAY, igdc=HINTS, policy=POLICY)
    del kw[missing]
    with pytest.raises(TypeError):
        authorize_hints(**kw)


@pytest.mark.parametrize("name", ["target", "binding", "payload", "igdc", "receipt"])
def test_none_is_a_type_error_not_a_skipped_check(name):
    with pytest.raises(TypeError):
        auth(**{name: None})


def test_subject_bytes_must_be_the_ones_held():
    assert refused(target=T + b" ") == ("RECEIPT_SUBJECT_MISMATCH", "R3")
    assert refused(binding=BIND + b" ") == ("RECEIPT_SUBJECT_MISMATCH", "R3")
    assert refused(payload=PAY + b" ") == ("RECEIPT_SUBJECT_MISMATCH", "R3")
    assert refused(igdc=HINTS + b" ") == ("RECEIPT_SUBJECT_MISMATCH", "R3")


def test_a_receipt_that_names_no_hint_document_cannot_authorize_one():
    plain = issue(BIND, PAY, T, verifier_version="test").to_ison().encode()
    assert refused(receipt=plain, pins=DeliveryPins.of(sha(plain))) == ("RECEIPT_SUBJECT_MISMATCH", "R3")


def test_a_pinned_rejection_receipt_is_delivered_evidence_of_rejection_and_never_authorizes():
    bad = issue(BIND, real_payload(T, target_artifact_sha256="c0" * 32).to_ison().encode(), T, verifier_version="test").to_ison().encode()
    pins = DeliveryPins.of(sha(bad))
    from isongraph_ext.igar.check import inspect_receipt
    assert inspect_receipt(bad).failure["check"] == "D0"                    # well-formed, consistent ... and pinned ...
    with pytest.raises(IGARError) as e:
        authorize_hints(receipt=bad, pins=pins, target=T, binding=BIND, payload=real_payload(T, target_artifact_sha256="c0" * 32).to_ison().encode(),
                        igdc=HINTS, policy=POLICY)
    assert (e.value.code, e.value.step) == ("RECEIPT_SUBJECT_MISMATCH", "R3")   # ... and refused: it names no hint document (R3 precedes R4)


def test_pinned_rejection_receipt_fails_policy_with_the_verification_dimension():
    p2 = real_payload(T, target_artifact_sha256="c0" * 32).to_ison().encode()
    rej = issue(BIND, p2, T, verifier_version="test")
    assert why(rej, POLICY) == "verification"


def test_policy_failures_surface_through_authorize():
    other = dataclasses.replace(POLICY, verifiers=frozenset({("isongraph-ext", "other")}))
    assert refused(policy=other) == ("RECEIPT_POLICY_UNSATISFIED", "R4")
    assert refused(policy=dataclasses.replace(POLICY, profiles=frozenset())) == ("RECEIPT_POLICY_UNSATISFIED", "R4")


def test_trusted_admission_cannot_be_constructed_directly():
    with pytest.raises(TypeError):
        TrustedAdmission(*(["x"] * 9))                                      # type: ignore[arg-type]


def test_policy_file_round_trip():
    text = (f'meta.policy\npolicy_spec require_admission require_full_resolution\nIGAR-POLICY/1 "true" "false"\n\n'
            f'table.core_commits\ncore_commit\n{CORE}\n\ntable.profiles\nprofile_sha256\n{PROFILE_D}\n\n'
            f'table.runtime\nruntime_ison_graph runtime_ison_py\n1.4.1 1.2.0\n\ntable.verifiers\nverifier verifier_version\nisongraph-ext 0.4.1')
    p = TrustPolicy.from_ison(text)
    assert p == dataclasses.replace(OK, runtime=frozenset({("1.4.1", "1.2.0")}), require_full_resolution=False)


def codes(fn, *a, **k):
    with pytest.raises(IGARError) as e:
        fn(*a, **k)
    return e.value.code, e.value.step


def test_policy_file_uses_the_strict_reader():
    ok = ('meta.policy\npolicy_spec require_admission require_full_resolution\nIGAR-POLICY/1 "true" "true"\n\n'
          'table.core_commits\ncore_commit\n\ntable.profiles\nprofile_sha256\n\ntable.runtime\nruntime_ison_graph runtime_ison_py\n\n'
          'table.verifiers\nverifier verifier_version')
    p = TrustPolicy.from_ison(ok)
    assert p.verifiers == frozenset() and p.core_commits == frozenset() and p.profiles == frozenset()      # empty tables accept nothing
    assert codes(TrustPolicy.from_ison, ok + "\n---\nx") == ("MALFORMED_POLICY", "R4")
    assert codes(TrustPolicy.from_ison, ok.replace("IGAR-POLICY/1", "IGAR-POLICY/9")) == ("MALFORMED_POLICY", "R4")
    assert codes(TrustPolicy.from_ison, ok.replace("policy_spec require_admission", "policy_spec policy_spec", 1)) == ("MALFORMED_POLICY", "R4")

# isongraph-ext/tests/test_igar_trust.py
"""Policy qualification (R4), delivery pins (R5) and authorize_hints (rev 2 finding F1): a policy match alone is never trusted admission."""
import copy
import dataclasses
import pickle

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
    # a repeated column is caught by the canonical-form layer (the canonical writer sorts and never repeats columns), before the shape layer
    with pytest.raises(IGARError) as e:
        TrustPolicy.from_ison(ok.replace("policy_spec require_admission", "policy_spec policy_spec", 1))
    assert e.value.field == "canonical_form"


# ---- fix round 1: single-use mint, no serialization, typed inputs, strict pins reader ---------------------------------------------
def test_trusted_admission_cannot_be_minted_by_replace_or_copied():
    a = auth()
    with pytest.raises(TypeError):
        dataclasses.replace(a, igdc_sha256="0" * 64)
    with pytest.raises(TypeError):
        dataclasses.replace(a)
    assert copy.copy(a) is a and copy.deepcopy(a) is a
    assert (a.receipt_sha256, a.igdc_sha256) == (sha(RAW), sha(HINTS))     # untouched and still usable


@pytest.mark.parametrize("protocol", range(6))
def test_trusted_admission_has_no_serialization(protocol):
    a = auth()
    with pytest.raises(TypeError):
        pickle.dumps(a, protocol=protocol)
    with pytest.raises(TypeError):
        a.__reduce__()


@pytest.mark.parametrize("name", ["pins", "policy", "limits"])
def test_pins_policy_limits_none_is_a_type_error(name):
    with pytest.raises(TypeError):
        auth(**{name: None})


def test_duck_typed_pins_policy_limits_are_refused():
    class AnyPins:
        receipts = type("All", (), {"__contains__": lambda s, x: True})()
    with pytest.raises(TypeError):
        auth(pins=AnyPins())
    with pytest.raises(TypeError):
        auth(pins=frozenset({sha(RAW)}))
    with pytest.raises(TypeError):
        auth(policy=type("P", (), {})())
    with pytest.raises(TypeError):
        auth(limits=object())
    with pytest.raises(TypeError):
        qualify_policy(verified(), None)                                   # type: ignore[arg-type]
    with pytest.raises(TypeError):
        TrustPolicy.from_ison("", limits=None)                             # type: ignore[arg-type]
    with pytest.raises(TypeError):
        DeliveryPins.from_sha256sums("", names=frozenset(), limits=None)   # type: ignore[arg-type]


def test_policy_and_pins_do_not_alias_a_mutable_collection():
    vs, cs, ps, rt = {("isongraph-ext", "test")}, {RD.verifier["core_commit"]}, {Profile.default().digest}, {("1", "2")}
    pol = TrustPolicy(vs, cs, ps, rt)
    vs.clear(), cs.clear(), ps.clear(), rt.clear()
    assert all(isinstance(x, frozenset) and x for x in (pol.verifiers, pol.core_commits, pol.profiles, pol.runtime))
    assert authorize_hints(receipt=RAW, pins=PINS, target=T, binding=BIND, payload=PAY, igdc=HINTS, policy=dataclasses.replace(pol, runtime=frozenset()))
    s = {sha(RAW)}
    dp = DeliveryPins(s)
    s.add("NOT HEX")
    assert dp.receipts == frozenset({sha(RAW)}) and isinstance(dp.receipts, frozenset)
    assert DeliveryPins([sha(RAW)]).receipts == frozenset({sha(RAW)})


def test_policy_and_pins_refuse_bare_strings_and_bad_elements():
    for bad in ("junk" + CORE + "junk", CORE, b"x" * 40, 5, None):
        with pytest.raises(TypeError):
            TrustPolicy(OK.verifiers, bad, OK.profiles)                     # type: ignore[arg-type]
    with pytest.raises(TypeError):
        TrustPolicy(OK.verifiers, OK.core_commits, PROFILE_D)               # type: ignore[arg-type]
    with pytest.raises(TypeError):
        DeliveryPins("a" * 64)                                              # type: ignore[arg-type]
    with pytest.raises(TypeError):
        DeliveryPins(None)                                                  # type: ignore[arg-type]
    for kw in (dict(core_commits=frozenset({CORE.upper()})), dict(core_commits=frozenset({"abc"})), dict(core_commits=frozenset({5})),
               dict(profiles=frozenset({"A" * 64})), dict(profiles=frozenset({"a" * 63})),
               dict(verifiers=frozenset({"ab"})), dict(verifiers=frozenset({("a",)})), dict(verifiers=frozenset({("a", "")})), dict(verifiers=frozenset({("a", 1)})),
               dict(runtime=frozenset({("1", "")})), dict(runtime=frozenset({("1", "2", "3")}))):
        with pytest.raises(IGARError) as e:
            dataclasses.replace(OK, **kw)
        assert (e.value.code, e.value.step) == ("MALFORMED_POLICY", "R4")
    for flag in ("require_admission", "require_full_resolution"):
        with pytest.raises(TypeError):
            dataclasses.replace(OK, **{flag: "false"})
    with pytest.raises(IGARError) as e:
        DeliveryPins(frozenset({5}))                                        # type: ignore[arg-type]
    assert e.value.code == "MALFORMED_PINS"


def test_policy_file_hex_failures_name_the_table():
    base = ('meta.policy\npolicy_spec require_admission require_full_resolution\nIGAR-POLICY/1 "true" "true"\n\n'
            'table.core_commits\ncore_commit\n{c}\n\ntable.profiles\nprofile_sha256\n{p}\n\ntable.runtime\nruntime_ison_graph runtime_ison_py\n\n'
            'table.verifiers\nverifier verifier_version')
    with pytest.raises(IGARError) as e:
        TrustPolicy.from_ison(base.format(c="a" * 39, p=PROFILE_D))
    assert (e.value.code, e.value.field) == ("MALFORMED_POLICY", "table.core_commits")
    with pytest.raises(IGARError) as e:
        TrustPolicy.from_ison(base.format(c=CORE, p="g" * 64))
    assert (e.value.code, e.value.field) == ("MALFORMED_POLICY", "table.profiles")


def test_qualify_policy_details_quote_receipt_derived_strings():
    r = mut(verified(), "verifier", verifier="x\nforged", verifier_version="1\ty")
    with pytest.raises(IGARError) as e:
        qualify_policy(r, OK)
    assert "\n" not in e.value.detail and "\t" not in e.value.detail and "'x\\nforged'" in e.value.detail


@pytest.mark.parametrize("sep", ["\u2028", "\u2029", "\x85", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e"])
def test_sha256sums_splits_only_on_newline(sep):
    forged = f"{H('a')}  x{sep}{H('b')}  graph.igar.ison\n"
    for names in (frozenset({"graph.igar.ison"}), frozenset()):            # the line itself is malformed, whether or not it is asked for
        with pytest.raises(IGARError) as e:
            DeliveryPins.from_sha256sums(forged, names=names)
        assert (e.value.code, e.value.field) == ("MALFORMED_PINS", "sha256sums")
        assert "not a sha256sum line" in e.value.detail
    with pytest.raises(IGARError) as e:
        DeliveryPins.from_sha256sums(f"{H('a')}  r{sep}\n", names=frozenset({"r"}))
    assert e.value.code == "MALFORMED_PINS"


def test_sha256sums_crlf_and_final_newline_handling_is_unchanged():
    assert DeliveryPins.from_sha256sums(f"{H('a')}  r\r\n{H('b')}  s\r\n", names=frozenset({"r"})).receipts == frozenset({H("a")})
    assert DeliveryPins.from_sha256sums(f"{H('a')}  r", names=frozenset({"r"})).receipts == frozenset({H("a")})
    assert DeliveryPins.from_sha256sums("", names=frozenset()).receipts == frozenset()
    with pytest.raises(IGARError) as e:
        DeliveryPins.from_sha256sums(f"{H('a')}  r\n\n", names=frozenset({"r"}))
    assert e.value.code == "MALFORMED_PINS"


def test_sha256sums_refuses_every_repeated_name():
    for second in (H("a"), H("b")):                                        # identical and conflicting
        with pytest.raises(IGARError) as e:
            DeliveryPins.from_sha256sums(f"{H('a')}  r\n{second}  r\n", names=frozenset({"r"}))
        assert (e.value.code, e.value.step) == ("MALFORMED_PINS", "R5")


def test_sha256sums_non_utf8_and_budget():
    with pytest.raises(IGARError) as e:
        DeliveryPins.from_sha256sums(b"\xff\xfe", names=frozenset({"r"}))
    assert (e.value.code, e.value.step) == ("MALFORMED_PINS", "R5")
    good = f"{H('a')}  r\n".encode()
    assert DeliveryPins.from_sha256sums(good, names=frozenset({"r"})).receipts == frozenset({H("a")})
    with pytest.raises(IGARError) as e:
        DeliveryPins.from_sha256sums(good, names=frozenset({"r"}), limits=Limits(max_payload_bytes=10))
    assert (e.value.code, e.value.step) == ("RECEIPT_LIMIT_EXCEEDED", "R5")
    with pytest.raises(IGARError) as e:
        DeliveryPins.from_sha256sums(b"\xff" * 100, names=frozenset(), limits=Limits(max_payload_bytes=10))   # budget before decoding
    assert e.value.code == "RECEIPT_LIMIT_EXCEEDED"
    with pytest.raises(TypeError):
        DeliveryPins.from_sha256sums(good, names="r")                       # type: ignore[arg-type]

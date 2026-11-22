# isongraph-ext/tests/test_igar_check.py
"""inspect (R0-R2), subject (R3) and recompute (R6): none of them says a receipt is trusted."""
import dataclasses

import pytest
from igar_helpers import verified
from igdm_helpers import bound, real_payload, sha, target_graph

from isongraph_ext.igar.check import check_subject, inspect_receipt, recompute
from isongraph_ext.igar.errors import IGARError
from isongraph_ext.igar.issue import issue
from isongraph_ext.igar.profile import Profile
from isongraph_ext.igdc.derive import consume
from isongraph_ext.igdm.records import Limits

T = target_graph()
P = real_payload(T)
B = bound(P, T)
BIND, PAY = B.to_ison().encode(), P.to_ison().encode()
HINTS = consume(PAY, B, T).to_ison().encode()
R = issue(BIND, PAY, T, verifier_version="test")
RD = issue(BIND, PAY, T, igdc=True, verifier_version="test")
PROFILE = Profile.default().to_ison().encode()


def code(fn, *a, **k):
    with pytest.raises(IGARError) as e:
        fn(*a, **k)
    return e.value.code, e.value.step


# ---- inspect -------------------------------------------------------------------------------------------------------------
def test_inspect_needs_nothing_but_the_receipt():
    assert inspect_receipt(R.to_ison()) == R and inspect_receipt(R.to_ison().encode()) == R


def test_inspect_applies_the_byte_budget_first():
    assert code(inspect_receipt, b"\xff" * 64, limits=Limits(max_payload_bytes=10)) == ("RECEIPT_LIMIT_EXCEEDED", "R0")


def test_inspect_runs_consistency_after_shape():
    bad = dataclasses.replace(R, result={**R.result, "verification": "rejected"})
    assert code(inspect_receipt, bad.to_ison()) == ("INCONSISTENT_RECEIPT", "R2")


# ---- subject (R3): every input is required; nothing can be silently skipped -------------------------------------------------
def test_subject_matches_exactly_the_bytes_held():
    check_subject(R, target=T, binding=BIND, payload=PAY, igdc=None)
    check_subject(RD, target=T, binding=BIND, payload=PAY, igdc=HINTS)


@pytest.mark.parametrize("missing", ["target", "binding", "payload", "igdc"])
def test_an_omitted_input_is_a_type_error_never_a_skipped_check(missing):
    kw = dict(target=T, binding=BIND, payload=PAY, igdc=None)
    del kw[missing]
    with pytest.raises(TypeError):
        check_subject(R, **kw)


@pytest.mark.parametrize("name", ["target", "binding", "payload"])
def test_none_is_not_accepted_for_the_three_required_inputs(name):
    kw = dict(target=T, binding=BIND, payload=PAY, igdc=None)
    kw[name] = None
    with pytest.raises(TypeError):
        check_subject(R, **kw)


def test_each_byte_string_must_match():
    for name, bad in (("target", T + b" "), ("binding", BIND + b" "), ("payload", PAY + b" ")):
        kw = dict(target=T, binding=BIND, payload=PAY, igdc=None)
        kw[name] = bad
        assert code(check_subject, R, **kw) == ("RECEIPT_SUBJECT_MISMATCH", "R3")


def test_igdc_is_checked_in_both_directions():
    assert code(check_subject, R, target=T, binding=BIND, payload=PAY, igdc=HINTS) == ("RECEIPT_SUBJECT_MISMATCH", "R3")      # receipt names none
    assert code(check_subject, RD, target=T, binding=BIND, payload=PAY, igdc=None) == ("RECEIPT_SUBJECT_MISMATCH", "R3")      # receipt names one, none held
    assert code(check_subject, RD, target=T, binding=BIND, payload=PAY, igdc=HINTS + b" ") == ("RECEIPT_SUBJECT_MISMATCH", "R3")


def test_a_hand_built_receipt_with_empty_subject_digests_matches_nothing():
    empty = dataclasses.replace(verified(), subject={"binding_sha256": sha(b""), "igdc_sha256": None, "igdm_payload_sha256": sha(b""), "target_artifact_sha256": sha(b"")})
    assert code(check_subject, empty, target=T, binding=BIND, payload=PAY, igdc=None) == ("RECEIPT_SUBJECT_MISMATCH", "R3")


# ---- recompute (R6): never under defaults the receipt did not name -----------------------------------------------------------
def test_recompute_accepts_the_real_receipt_under_its_named_profile():
    recompute(R.to_ison(), BIND, PAY, T, profile=PROFILE, verifier_version="test")
    recompute(RD.to_ison(), BIND, PAY, T, profile=PROFILE, verifier_version="test")


def test_recompute_without_the_profile_is_unavailable_not_invalid():
    assert code(recompute, R.to_ison(), BIND, PAY, T, profile=None, verifier_version="test") == ("RECOMPUTE_UNAVAILABLE", "R6")


def test_recompute_with_a_different_profile_is_unavailable_not_a_verdict_on_the_receipt():
    tight = dataclasses.replace(Profile.default(), limits=Limits(max_group_depth=3)).to_ison().encode()
    assert code(recompute, R.to_ison(), BIND, PAY, T, profile=tight, verifier_version="test") == ("RECOMPUTE_UNAVAILABLE", "R6")


def test_historical_receipt_under_a_non_default_profile_recomputes_when_its_profile_is_supplied():
    prof = dataclasses.replace(Profile.default(), limits=Limits(max_group_depth=3))
    old = issue(BIND, PAY, T, profile=prof, verifier_version="test")                 # issued under settings that are NOT today's defaults
    recompute(old.to_ison(), BIND, PAY, T, profile=prof.to_ison().encode(), verifier_version="test")
    assert code(recompute, old.to_ison(), BIND, PAY, T, profile=PROFILE, verifier_version="test") == ("RECOMPUTE_UNAVAILABLE", "R6")


def test_recompute_other_verifier_version_or_runtime_is_unavailable():
    assert code(recompute, R.to_ison(), BIND, PAY, T, profile=PROFILE, verifier_version="other") == ("RECOMPUTE_UNAVAILABLE", "R6")
    wrong_rt = dataclasses.replace(R, verifier={**R.verifier, "runtime_ison_graph": "0.0.1"})
    assert code(recompute, wrong_rt.to_ison(), BIND, PAY, T, profile=PROFILE, verifier_version="test") == ("RECOMPUTE_UNAVAILABLE", "R6")


def test_recompute_malformed_profile():
    assert code(recompute, R.to_ison(), BIND, PAY, T, profile=b"junk", verifier_version="test")[0] == "RECOMPUTE_UNAVAILABLE"      # digest differs first
    bad = Profile.default().to_ison() + "\n---\nx"
    forged = dataclasses.replace(R, verifier={**R.verifier, "profile_sha256": sha(bad.encode())})
    assert code(recompute, forged.to_ison(), BIND, PAY, T, profile=bad.encode(), verifier_version="test") == ("MALFORMED_PROFILE", "R6")


def test_recompute_rejects_a_flipped_verdict_only_after_every_precondition_holds():
    forged = dataclasses.replace(R, result={**R.result, "admission": "denied"}, admission={"code": "STALE_BINDING", "step": "A1", "receipt_posture": "INADMISSIBLE"},
                                 reasons=("BASELINE_RETIRED",))
    forged.check_consistency()                                       # canonical, well-formed AND consistent ...
    assert code(recompute, forged.to_ison(), BIND, PAY, T, profile=PROFILE, verifier_version="test") == ("RECEIPT_RECOMPUTE_MISMATCH", "R6")   # ... but not computed


def test_recompute_other_inputs_mismatch():
    other = real_payload(T, target_artifact_sha256="c0" * 32).to_ison().encode()
    assert code(recompute, R.to_ison(), BIND, other, T, profile=PROFILE, verifier_version="test")[0] == "RECEIPT_RECOMPUTE_MISMATCH"


# ---- recompute: preconditions and the hint-derived path, field by field -------------------------------------------------------------
def field_of(fn, *a, **k):
    with pytest.raises(IGARError) as e:
        fn(*a, **k)
    return e.value.code, e.value.step, e.value.field


def test_recompute_mismatch_on_a_hint_derived_receipt_with_another_igdc_digest():
    forged = dataclasses.replace(RD, subject={**RD.subject, "igdc_sha256": "ab" * 32})
    forged.check_consistency()                                       # still a well-formed, consistent derived receipt ...
    assert code(recompute, forged.to_ison(), BIND, PAY, T, profile=PROFILE, verifier_version="test") == ("RECEIPT_RECOMPUTE_MISMATCH", "R6")   # ... that is not what is computed


@pytest.mark.parametrize("name", ["runtime_ison_py", "runtime_ison_graph"])
def test_recompute_with_a_different_runtime_names_the_runtime_field(name):
    other = dataclasses.replace(R, verifier={**R.verifier, name: "0.0.1"})
    assert field_of(recompute, other.to_ison(), BIND, PAY, T, profile=PROFILE, verifier_version="test") == ("RECOMPUTE_UNAVAILABLE", "R6", f"meta.verifier.{name}")


def test_recompute_with_both_version_and_profile_different_reports_the_profile_first():
    tight = dataclasses.replace(Profile.default(), limits=Limits(max_group_depth=3)).to_ison().encode()
    assert field_of(recompute, R.to_ison(), BIND, PAY, T, profile=tight, verifier_version="other") == ("RECOMPUTE_UNAVAILABLE", "R6", "meta.verifier.profile_sha256")
    assert field_of(recompute, R.to_ison(), BIND, PAY, T, profile=PROFILE, verifier_version="other")[2] == "meta.verifier.verifier_version"     # the version alone


# ---- check_subject: every input is type-checked before any comparison --------------------------------------------------------------
@pytest.mark.parametrize("name", ["target", "binding", "payload", "igdc"])
@pytest.mark.parametrize("bad", ["text", 0, [b"x"], object()])
def test_a_wrong_typed_input_is_a_type_error_even_when_the_inputs_also_mismatch(name, bad):
    kw = dict(target=T + b" ", binding=BIND + b" ", payload=PAY + b" ", igdc=None)           # target (checked first) already mismatches
    kw[name] = bad
    with pytest.raises(TypeError):
        check_subject(R, **kw)
    kw = dict(target=T, binding=BIND, payload=PAY, igdc=HINTS)                                 # and: igdc supplied to a receipt that names none
    kw[name] = bad
    with pytest.raises(TypeError):
        check_subject(R, **kw)


def test_a_non_bytes_igdc_on_a_receipt_naming_none_is_a_type_error_not_a_mismatch():
    with pytest.raises(TypeError):
        check_subject(R, target=T, binding=BIND, payload=PAY, igdc="not bytes")
    check_subject(R, target=T, binding=BIND, payload=PAY, igdc=None)                           # None stays the documented "no hint document held"


def test_binding_none_with_a_wrong_target_is_a_type_error_not_a_mismatch():
    with pytest.raises(TypeError):
        check_subject(R, target=T + b" ", binding=None, payload=PAY, igdc=None)


@pytest.mark.parametrize("bad", [None, "receipt", R.to_ison(), R.to_ison().encode(), {"subject": R.subject}])
def test_a_non_receipt_is_a_type_error(bad):
    with pytest.raises(TypeError):
        check_subject(bad, target=T, binding=BIND, payload=PAY, igdc=None)


def test_a_receipt_subclass_is_refused_exactly():
    class Sub(type(R)):
        pass
    with pytest.raises(TypeError):
        check_subject(Sub(**{f.name: getattr(R, f.name) for f in dataclasses.fields(R)}), target=T, binding=BIND, payload=PAY, igdc=None)


def test_bytearray_inputs_are_still_accepted():
    check_subject(R, target=bytearray(T), binding=bytearray(BIND), payload=bytearray(PAY), igdc=None)
    check_subject(RD, target=T, binding=BIND, payload=PAY, igdc=bytearray(HINTS))


# ---- recompute: the profile is READ only after the version and runtime preconditions --------------------------------------------------
def test_an_unreadable_profile_whose_digest_matches_is_unavailable_when_the_verifier_version_differs():
    bad = Profile.default().to_ison() + "\n---\nx"                                             # today's reader refuses this text
    with pytest.raises(IGARError):
        Profile.from_ison(bad)
    named = dataclasses.replace(R, verifier={**R.verifier, "profile_sha256": sha(bad.encode())})
    named.check_consistency()
    assert field_of(recompute, named.to_ison(), BIND, PAY, T, profile=bad.encode(), verifier_version="other") == (
        "RECOMPUTE_UNAVAILABLE", "R6", "meta.verifier.verifier_version")
    other_rt = dataclasses.replace(named, verifier={**named.verifier, "runtime_ison_py": "0.0.1"})
    assert field_of(recompute, other_rt.to_ison(), BIND, PAY, T, profile=bad.encode(), verifier_version="test") == (
        "RECOMPUTE_UNAVAILABLE", "R6", "meta.verifier.runtime_ison_py")
    assert field_of(recompute, named.to_ison(), BIND, PAY, T, profile=bad.encode(), verifier_version="test")[:2] == ("MALFORMED_PROFILE", "R6")   # all else equal: unreadable

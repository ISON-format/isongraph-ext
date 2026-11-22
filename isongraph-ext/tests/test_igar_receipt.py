# isongraph-ext/tests/test_igar_receipt.py
# isongraph-ext/tests/test_igar_receipt.py
import dataclasses

import pytest
from igar_helpers import CORE, H, rejected_d2, verified
from ison_parser import Block, dumps_canonical, loads

from isongraph_ext.igar.errors import IGARError
from isongraph_ext.igar.receipt import FIELDS, STATUS, Receipt, passed


def codes(fn, *a):
    with pytest.raises(IGARError) as e:
        fn(*a)
    return e.value.code, e.value.step


def test_round_trip_is_byte_stable_and_digest_is_external():
    r = verified(reasons=(), unrecognized=("nodes.role:x-a",))
    t = r.to_ison()
    assert Receipt.from_ison(t) == r and Receipt.from_ison(t.encode()).to_ison() == t
    assert r.digest == __import__("hashlib").sha256(t.encode()).hexdigest()
    assert "receipt_sha256" not in t and not t.endswith("\n")


def test_valid_receipts_pass_consistency():
    for r in (verified(), rejected_d2()):
        Receipt.from_ison(r.to_ison()).check_consistency()
    assert passed(verified()) and not passed(rejected_d2())


def test_status_table_covers_every_check():
    from isongraph_ext.igar.receipt import CHECKS
    assert set(STATUS) == set(CHECKS) | {None}


@pytest.mark.parametrize("check,expected", [("V1", ("invalid", "not_evaluated", "not_evaluated")), ("V4", ("valid", "not_evaluated", "rejected")),
                                            ("D0", ("valid", "not_evaluated", "rejected")), ("D1", ("valid", "invalid", "not_evaluated")),
                                            ("D3", ("valid", "valid", "rejected"))])
def test_status_table(check, expected):
    assert STATUS[check] == expected


# ---- R0 ----
def test_noncanonical_wins_over_shape():
    t = verified().to_ison().replace("IGDC/1", "IGDC/9")           # a shape fault ...
    t = t.replace("\n\n", "\n\n\n", 1)                              # ... and a canonical-form fault
    assert codes(Receipt.from_ison, t) == ("MALFORMED_RECEIPT", "R0")


def test_cr_and_bad_utf8_rejected():
    assert codes(Receipt.from_ison, verified().to_ison().replace("\n", "\r\n")) == ("MALFORMED_RECEIPT", "R0")
    assert codes(Receipt.from_ison, b"\xff\xfe") == ("MALFORMED_RECEIPT", "R0")


# ---- R1 ----
def _doc(r: Receipt):
    return r.to_document()


def test_unexpected_missing_duplicate_blocks_rejected():
    d = _doc(verified()); d.blocks.append(Block("table", "extra", ["a"], []))
    assert codes(Receipt.from_ison, dumps_canonical(d)) == ("MALFORMED_RECEIPT", "R1")
    d = _doc(verified()); d.blocks.pop()
    assert codes(Receipt.from_ison, dumps_canonical(d)) == ("MALFORMED_RECEIPT", "R1")
    d = _doc(verified()); d.blocks.append(d.blocks[0])
    assert codes(Receipt.from_ison, dumps_canonical(d)) == ("MALFORMED_RECEIPT", "R1")


def test_embedded_digest_field_rejected():
    d = _doc(verified())
    igar = next(b for b in d.blocks if b.name == "igar")
    igar.fields.append("receipt_sha256"); igar.rows[0]["receipt_sha256"] = H("d")
    assert codes(Receipt.from_ison, dumps_canonical(d)) == ("MALFORMED_RECEIPT", "R1")


@pytest.mark.parametrize("path,value", [
    (("subject", "target_artifact_sha256"), "xyz"), (("subject", "binding_sha256"), None), (("verifier", "igdm_spec"), "IGDM/2"),
    (("verifier", "verifier"), "other"), (("verifier", "core_commit"), "abc"), (("verifier", "profile_sha256"), None), (("verifier", "profile_sha256"), "zz"), (("result", "verification"), "maybe"),
    (("result", "consumption"), "not_requested"), (("failure", "check"), "V9"), (("admission", "step"), "A3"),
    (("admission", "receipt_posture"), "FINE"), (("igar", "receipt_spec"), "IGAR/2"),
])
def test_shape_faults_rejected(path, value):
    d = _doc(verified())
    block = next(b for b in d.blocks if b.name == path[0])
    block.rows[0][path[1]] = value
    assert codes(Receipt.from_ison, dumps_canonical(d)) == ("MALFORMED_RECEIPT", "R1")


# ---- R2 ----
def _with(r, block, **kv):
    return dataclasses.replace(r, **{block: {**getattr(r, block), **kv}})


@pytest.mark.parametrize("make", [
    lambda: _with(verified(), "failure", check="D2", code="X", field="f"),                                # verified but a failure is set
    lambda: _with(rejected_d2(), "failure", check=None, code=None, field=None),                            # rejected but no failure
    lambda: _with(rejected_d2(), "result", verification="verified"),                                        # status contradicts the check
    lambda: _with(rejected_d2(), "result", admission="admitted"),                                           # admitted without verification
    lambda: _with(rejected_d2(), "admission", receipt_posture="OK"),                                        # admission fields without admission
    lambda: _with(verified(), "failure", check=None, code="X"),                                             # code without check
    lambda: _with(verified(), "result", consumption="derived"),                                             # derived but no igdc digest
    lambda: _with(verified(), "verifier", semantic_verification=None),                                      # verified but flags missing
    lambda: _with(rejected_d2(), "verifier", semantic_verification="full"),                                 # flags on a rejected run
    lambda: _with(verified(), "admission", code="STALE_BINDING", step="A2"),                                # code/step pair wrong
    lambda: _with(verified(), "admission", code="STALE_BINDING", step="A1"),                                # denied but result says admitted
    lambda: dataclasses.replace(rejected_d2(), reasons=("X",)),                                             # reasons without admission
    lambda: _with(verified(), "verifier", core_commit=None),                                                # null core_commit only legal for V1
])
def test_inconsistent_receipts_rejected(make):
    r = make()
    assert codes(r.check_consistency) == ("INCONSISTENT_RECEIPT", "R2")


def test_status_contradicting_failure_rejected():
    r = _with(verified(), "failure", check="D2", code="TARGET_BINDING_MISMATCH", field="meta.igdm.target_artifact_sha256")
    Receipt.from_ison(r.to_ison())                                  # shape is perfect ...
    assert codes(r.check_consistency)[0] == "INCONSISTENT_RECEIPT"  # ... the contradiction is what R2 is for


def test_denied_and_derived_receipts_are_consistent():
    denied = _with(_with(verified(), "result", admission="denied"), "admission", code="STALE_BINDING", step="A1", receipt_posture="INADMISSIBLE")
    denied = dataclasses.replace(denied, reasons=("BASELINE_RETIRED",)); denied.check_consistency()
    derived = _with(_with(verified(), "result", consumption="derived"), "subject", igdc_sha256=H("e")); derived.check_consistency()
    failed = _with(_with(verified(), "result", consumption="failed"), "consumption", code="RESOLUTION_REQUIRED", step="P0", field="object_resolution")
    failed.check_consistency()
    v1 = _with(_with(rejected_d2(), "failure", check="V1", code="MALFORMED_BINDING", field="document"), "result",
               binding_schema="invalid", payload_schema="not_evaluated", verification="not_evaluated")
    v1 = _with(v1, "verifier", core_commit=None); v1.check_consistency()

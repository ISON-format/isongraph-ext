# isongraph-ext/tests/igar_helpers.py
# isongraph-ext/tests/igar_helpers.py
"""Hand-built receipts for the igar tests: no production issue() involved."""
from isongraph_ext.igar.receipt import Receipt

H = lambda c: c * 64  # noqa: E731  64 hex digits; letters keep the writer from quoting all-digit strings
CORE = "ce9d3b78afd79cbdffdd67546bcb5278dc38be70"


def verified(**over) -> Receipt:
    d = dict(
        subject={"binding_sha256": H("a"), "igdc_sha256": None, "igdm_payload_sha256": H("b"), "target_artifact_sha256": H("c")},
        verifier={"verifier": "isongraph-ext", "verifier_version": "0.5.0", "igx_spec": "IGX/1", "igdm_spec": "IGDM/1", "igdc_spec": "IGDC/1", "profile_sha256": H("d"),
                  "core_commit": CORE, "runtime_ison_graph": "1.4.1", "runtime_ison_py": "1.2.0", "semantic_verification": "full", "object_resolution": "full"},
        result={"binding_schema": "valid", "payload_schema": "valid", "verification": "verified", "admission": "admitted", "consumption": "absent"},
        failure={"check": None, "code": None, "field": None},
        admission={"code": None, "step": None, "receipt_posture": "OK"},
        consumption={"code": None, "step": None, "field": None},
    )
    d.update(over)
    return Receipt(**d)


def rejected_d2(**over) -> Receipt:
    return verified(
        verifier={**verified().verifier, "semantic_verification": None, "object_resolution": None},
        result={"binding_schema": "valid", "payload_schema": "valid", "verification": "rejected", "admission": "not_evaluated", "consumption": "absent"},
        failure={"check": "D2", "code": "TARGET_BINDING_MISMATCH", "field": "meta.igdm.target_artifact_sha256"},
        admission={"code": None, "step": None, "receipt_posture": None}, **over)

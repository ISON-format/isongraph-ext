# isongraph-ext/src/isongraph_ext/igar/issue.py
"""Issue a receipt (25 §5): wraps the existing verification path; a rejection IS the content, never an exception.

Python reference only: IGAR/1 receipts are issued by this package. A receipt from any other producer is unqualified (25 §8).
"""
from __future__ import annotations

from importlib import metadata

from .. import __version__
from ..igdc.derive import consume
from ..igdc.errors import IGDCError
from ..igdm.errors import IGDMError
from ..igdm.verify import verify as igdm_verify
from ..igx.admit import admit
from ..igx.binding import ExtensionBinding
from ..igx.digest import sha256_hex
from ..igx.errors import IGXError
from .profile import Profile
from .receipt import STATUS, Receipt


def issue(binding: bytes, payload: bytes, target: bytes, *, igdc: bool = False, profile: Profile | None = None,
          verifier_version: str | None = None) -> Receipt:
    """Verify under `profile` (default: `Profile.default()`) and record the outcome AND the profile's digest.

    There are deliberately no separate limits/baselines/registry/policy arguments: the profile is the single statement of the
    effective configuration, so a receipt can never describe a run that used different settings than it names.
    """
    for name, v in (("binding", binding), ("payload", payload), ("target", target)):
        if not isinstance(v, (bytes, bytearray)):
            raise TypeError(f"{name} must be bytes (the verifier hashes exactly what it is given), got {type(v).__name__}")
    binding, payload, target = bytes(binding), bytes(payload), bytes(target)
    profile = profile or Profile.default()
    parsed = result = dm = adm = None
    failure: tuple[str, str, str] | None = None
    try:
        parsed = ExtensionBinding.from_ison(binding)                           # IGX/1 V1 (parse)
        result, dm = igdm_verify(payload, parsed, target, limits=profile.limits, baselines=profile.baselines, registry=profile.registry)
        adm = admit(parsed, result, policy=profile.policy, baselines=profile.baselines)
    except (IGXError, IGDMError) as e:
        failure = (e.step, e.code, e.field)
    chk = failure[0] if failure else None
    if chk not in STATUS:
        raise RuntimeError(f"verification reported an unknown step {chk!r}; IGAR/1 §2.2 must be extended by a new spec version")
    binding_schema, payload_schema, verification = STATUS[chk]
    ok = failure is None
    consumption, igdc_digest, c_code = "absent", None, (None, None, None)
    if igdc and ok:
        try:
            igdc_digest = consume(payload, parsed, target, limits=profile.limits, baselines=profile.baselines, registry=profile.registry).digest
            consumption = "derived"
        except IGDCError as e:
            consumption, c_code = "failed", (e.code, e.step, e.field)
    return Receipt(
        subject={"binding_sha256": sha256_hex(binding), "igdc_sha256": igdc_digest, "igdm_payload_sha256": sha256_hex(payload),
                 "target_artifact_sha256": sha256_hex(target)},
        verifier={"verifier": "isongraph-ext", "verifier_version": verifier_version or __version__, "igx_spec": "IGX/1", "igdm_spec": "IGDM/1",
                  "igdc_spec": "IGDC/1", "profile_sha256": profile.digest, "core_commit": parsed.core_commit if parsed else None,
                  "runtime_ison_graph": metadata.version("ison-graph"), "runtime_ison_py": metadata.version("ison-py"),
                  "semantic_verification": result.semantic_verification if ok else None, "object_resolution": dm.object_resolution if ok else None},
        result={"binding_schema": binding_schema, "payload_schema": payload_schema, "verification": verification,
                "admission": ("admitted" if adm.admitted else "denied") if ok else "not_evaluated", "consumption": consumption},
        failure={"check": chk, "code": failure[1] if failure else None, "field": failure[2] if failure else None},
        admission={"code": adm.code if ok else None, "step": adm.step if ok else None, "receipt_posture": adm.receipt_posture if ok else None},
        consumption={"code": c_code[0], "step": c_code[1], "field": c_code[2]},
        reasons=tuple(adm.reasons) if ok else (), unrecognized=tuple(dm.unrecognized_roles) if ok else ())

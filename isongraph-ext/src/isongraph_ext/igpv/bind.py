"""Producer path and trustworthy consumer path (18 §5.2): never return a binding whose provenance would not verify."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..igx.admit import DEFAULT_POLICY, AdmissionPolicy, AdmissionResult, admit
from ..igx.baselines import BASELINES, DEFAULT_BASELINE, Baseline
from ..igx.bind import bind as igx_bind
from ..igx.binding import Capability, Consumer, ExtensionBinding
from ..igx.digest import sha256_hex
from ..igx.registry import DEFAULT_REGISTRY, CapabilityRegistry
from ..igx.source import as_bytes
from ..igx.verify import VerificationResult
from . import records as R
from .errors import IGPVError
from .payload import ProvenancePayload
from .verify import ProvenanceVerification, verify


def bind(target: str | bytes, payload: ProvenancePayload, *, requirement: str = "REQUIRED", serialization_profile: str,
         producer_port: str, identity_claim: str, capabilities: Sequence[Capability] = (), consumer: Consumer | None = None,
         baseline: Baseline = DEFAULT_BASELINE, registry: CapabilityRegistry = DEFAULT_REGISTRY,
         policy: AdmissionPolicy = DEFAULT_POLICY, sources: Mapping[str, bytes] | None = None,
         limits: R.Limits = R.DEFAULT_LIMITS) -> ExtensionBinding:
    if requirement not in ("REQUIRED", "OPTIONAL"):
        raise IGPVError("MALFORMED_PROVENANCE", "table.capabilities.igpv.requirement", "REQUIRED or OPTIONAL", "P1")
    if any(c.extension == R.CAPABILITY for c in capabilities):
        raise IGPVError("MALFORMED_PROVENANCE", "table.capabilities.igpv", "bind() adds the igpv row itself; do not pass one", "P1")
    payload.check()
    data = as_bytes(target)
    actual = sha256_hex(data)
    if payload.target_artifact_sha256 != actual:
        raise IGPVError("TARGET_BINDING_MISMATCH", "meta.igpv.target_artifact_sha256", f"target bytes hash to {actual}", "P2")
    if payload.target_serialization_profile != serialization_profile:
        raise IGPVError("TARGET_BINDING_MISMATCH", "meta.igpv.target_serialization_profile",
                        f"{payload.target_serialization_profile} != {serialization_profile}", "P2")
    caps = tuple(capabilities) + (Capability(R.CAPABILITY, R.CAPABILITY_RANGE, requirement, payload.digest),)
    binding = igx_bind(data, serialization_profile=serialization_profile, producer_port=producer_port, identity_claim=identity_claim,
                       capabilities=caps, consumer=consumer, baseline=baseline, registry=registry, policy=policy)
    baselines = {**BASELINES, baseline.core_commit: baseline}
    verify(payload, binding, data, sources=sources, limits=limits, baselines=baselines, registry=registry)
    return binding


def verify_and_admit(payload: str | bytes | ProvenancePayload, binding: ExtensionBinding, target: str | bytes, *,
                     sources: Mapping[str, bytes] | None = None, limits: R.Limits = R.DEFAULT_LIMITS,
                     baselines: Mapping[str, Baseline] = BASELINES, registry: CapabilityRegistry = DEFAULT_REGISTRY,
                     policy: AdmissionPolicy = DEFAULT_POLICY) -> tuple[VerificationResult, ProvenanceVerification, AdmissionResult]:
    result, prov = verify(payload, binding, target, sources=sources, limits=limits, baselines=baselines, registry=registry)
    decision = admit(binding, result, policy=policy, baselines=baselines)       # 18 §4.2: the binding's decision, unchanged
    return result, prov, decision

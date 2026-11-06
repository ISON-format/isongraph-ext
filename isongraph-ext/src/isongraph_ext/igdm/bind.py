"""Producer path and trustworthy consumer path (19 §4), mirroring igpv.bind."""

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
from .errors import IGDMError
from .payload import DatamaticsPayload
from .verify import DatamaticsVerification, verify


def bind(target: str | bytes, payload: DatamaticsPayload, *, requirement: str = "REQUIRED", serialization_profile: str,
         producer_port: str, identity_claim: str, capabilities: Sequence[Capability] = (), consumer: Consumer | None = None,
         baseline: Baseline = DEFAULT_BASELINE, registry: CapabilityRegistry = DEFAULT_REGISTRY,
         policy: AdmissionPolicy = DEFAULT_POLICY, limits: R.Limits = R.DEFAULT_LIMITS) -> ExtensionBinding:
    if requirement not in ("REQUIRED", "OPTIONAL"):
        raise IGDMError("MALFORMED_DATAMATICS", "table.capabilities.igdm.requirement", "REQUIRED or OPTIONAL", "D1")
    if any(c.extension == R.CAPABILITY for c in capabilities):
        raise IGDMError("MALFORMED_DATAMATICS", "table.capabilities.igdm", "bind() adds the igdm row itself; do not pass one", "D1")
    payload.check()
    data = as_bytes(target)
    actual = sha256_hex(data)
    if payload.target_artifact_sha256 != actual:
        raise IGDMError("TARGET_BINDING_MISMATCH", "meta.igdm.target_artifact_sha256", f"target bytes hash to {actual}", "D2")
    if payload.target_serialization_profile != serialization_profile:
        raise IGDMError("TARGET_BINDING_MISMATCH", "meta.igdm.target_serialization_profile",
                        f"{payload.target_serialization_profile} != {serialization_profile}", "D2")
    caps = tuple(capabilities) + (Capability(R.CAPABILITY, R.CAPABILITY_RANGE, requirement, payload.digest),)
    binding = igx_bind(data, serialization_profile=serialization_profile, producer_port=producer_port, identity_claim=identity_claim,
                       capabilities=caps, consumer=consumer, baseline=baseline, registry=registry, policy=policy)
    verify(payload, binding, data, limits=limits, baselines={**BASELINES, baseline.core_commit: baseline}, registry=registry)
    return binding


def verify_and_admit(payload: str | bytes | DatamaticsPayload, binding: ExtensionBinding, target: str | bytes, *,
                     limits: R.Limits = R.DEFAULT_LIMITS, baselines: Mapping[str, Baseline] = BASELINES,
                     registry: CapabilityRegistry = DEFAULT_REGISTRY, policy: AdmissionPolicy = DEFAULT_POLICY
                     ) -> tuple[VerificationResult, DatamaticsVerification, AdmissionResult]:
    result, dm = verify(payload, binding, target, limits=limits, baselines=baselines, registry=registry)
    return result, dm, admit(binding, result, policy=policy, baselines=baselines)

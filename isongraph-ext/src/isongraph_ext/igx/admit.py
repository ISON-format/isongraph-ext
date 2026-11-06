"""Operational admission, A1-A3 (17 §4.2). Policy denials are results, never exceptions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .baselines import BASELINES, Baseline
from .binding import ExtensionBinding
from .errors import IGXError
from .verify import EMPTY_REGISTRY, CapabilityRegistry, VerificationResult, resolve_baseline, verify


@dataclass(frozen=True)
class AdmissionPolicy:
    accept_lossy_domains: frozenset[str] = frozenset()   # RESERVED in E1 (17 §3): reported, never applied
    allow_retired_baselines: bool = False


DEFAULT_POLICY = AdmissionPolicy()


@dataclass(frozen=True)
class AdmissionResult:
    admitted: bool
    code: str | None
    step: str | None
    receipt_posture: str
    reasons: tuple[str, ...]


def _deny(code: str, step: str, reasons: list[str]) -> AdmissionResult:
    return AdmissionResult(False, code, step, "INADMISSIBLE", tuple(reasons))


def admit(binding: ExtensionBinding, result: VerificationResult, *, policy: AdmissionPolicy = DEFAULT_POLICY,
          baselines: Mapping[str, Baseline] = BASELINES) -> AdmissionResult:
    """Decide on a binding given the VerificationResult verify() produced FOR THIS BINDING.

    A result for another binding is not a policy question: it raises. A hand-built VerificationResult is not
    evidence; callers who need a trustworthy decision use verify_and_admit().
    """
    if result.binding_digest != binding.digest:
        raise IGXError("VERIFICATION_RESULT_MISMATCH", "result.binding_digest",
                       f"result is for {result.binding_digest}, binding is {binding.digest}", "A0")
    base = resolve_baseline(binding, baselines)
    reasons: list[str] = []
    if policy.accept_lossy_domains:
        reasons.append("POLICY_FIELD_RESERVED")

    # A1 currency
    if base.retired and not policy.allow_retired_baselines:
        return _deny("STALE_BINDING", "A1", reasons + ["BASELINE_RETIRED"])

    # A2 claim
    claim, posture = binding.identity_claim, binding.producer_core_posture
    if claim == "cross_port":
        denial = ["SEMANTIC2_NOT_FROZEN"] + (["CONSUMER_REQUIRED"] if binding.consumer is None else [])
        return _deny("IDENTITY_CLAIM_INADMISSIBLE", "A2", reasons + denial)
    if claim == "producer_bound":
        denial = []
        if result.semantic_verification != "full":
            denial.append("SEMANTIC_REVERIFICATION_UNAVAILABLE")   # stored eligibility was not re-derived: a claim, not evidence
        if posture == "LOSSY_KNOWN":
            denial.append("LOSSY_PRODUCER_BOUND_RESERVED")
        elif posture == "KNOWN_DEFECT":
            denial.append("CORE_BLOCKING_DIVERGENCE")
        elif posture != "FULL":
            denial.append(f"PRODUCER_POSTURE_{posture}")
        if result.source_semantic_eligibility == "ineligible":
            denial.append(f"SOURCE_NOT_ELIGIBLE:{result.source_semantic_reason}")
        elif result.source_semantic_eligibility == "unclassified":
            denial.append("SOURCE_UNCLASSIFIED")
        if denial:
            return _deny("IDENTITY_CLAIM_INADMISSIBLE", "A2", reasons + denial)

    # A3 consumer (reporting only)
    receipt_posture = "OK"
    if binding.consumer is not None:
        cp = binding.consumer.posture
        if cp in ("KNOWN_DEFECT", "PARTIAL", "INCONCLUSIVE", "NONCONFORMANT"):
            receipt_posture = "CORE_BLOCKING_DIVERGENCE"
            reasons.append(f"CONSUMER_POSTURE_{cp}")
        elif cp == "LOSSY_KNOWN":
            receipt_posture = "CORE_LOSSY"
            reasons.append("CONSUMER_POSTURE_LOSSY_KNOWN")
    return AdmissionResult(True, None, None, receipt_posture, tuple(reasons))


def verify_and_admit(binding: ExtensionBinding, source: str | bytes, *, baselines: Mapping[str, Baseline] = BASELINES,
                     registry: CapabilityRegistry = EMPTY_REGISTRY, policy: AdmissionPolicy = DEFAULT_POLICY
                     ) -> tuple[VerificationResult, AdmissionResult]:
    """The trustworthy entry point: the result handed to admit() is the one verify() just produced for this binding and these bytes."""
    result = verify(binding, source, baselines=baselines, registry=registry)
    return result, admit(binding, result, policy=policy, baselines=baselines)

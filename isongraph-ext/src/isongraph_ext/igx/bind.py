"""Producer path (17 §3 bind): derive, build, verify, admit - never return what you would not admit."""

from __future__ import annotations

from collections.abc import Sequence

from .admit import DEFAULT_POLICY, AdmissionPolicy, admit
from .baselines import BASELINES, DEFAULT_BASELINE, Baseline
from .binding import IDENTITY_CLAIMS, PORTS, PROFILES, WRITER_OF_PORT, Capability, Consumer, ExtensionBinding
from .digest import sha256_hex
from .errors import IGXError
from .source import as_bytes, classify_eligibility, derive_canonical
from .verify import EMPTY_REGISTRY, CapabilityRegistry, _runtime_mismatch, verify


def bind(source: str | bytes, *, serialization_profile: str, producer_port: str, identity_claim: str,
         capabilities: Sequence[Capability] = (), consumer: Consumer | None = None, baseline: Baseline = DEFAULT_BASELINE,
         registry: CapabilityRegistry = EMPTY_REGISTRY, policy: AdmissionPolicy = DEFAULT_POLICY) -> ExtensionBinding:
    data = as_bytes(source)
    # Argument shape is V1 territory - the same enum rule check_shape() applies to a parsed binding (17 §4 V1).
    if producer_port not in PORTS:
        raise IGXError("MALFORMED_BINDING", "meta.core_baseline.producer_port", f"not one of {PORTS}", "V1")
    if identity_claim not in IDENTITY_CLAIMS:
        raise IGXError("MALFORMED_BINDING", "meta.igx.identity_claim", f"not one of {IDENTITY_CLAIMS}", "V1")
    if serialization_profile not in PROFILES:
        raise IGXError("MALFORMED_BINDING", "meta.source.serialization_profile", f"not one of {PROFILES}", "V1")
    receipt = baseline.receipts.get(producer_port)
    if receipt is None:
        raise IGXError("RECEIPT_REFERENCE_INVALID", "meta.core_baseline.producer_port",
                       f"baseline {baseline.core_commit} has no receipt for {producer_port!r}", "V3")
    mismatch = _runtime_mismatch(baseline)
    if mismatch is not None:
        # Producing needs the pinned implementation to derive canonicality/eligibility; only verifying tolerates its absence.
        raise IGXError("CORE_RUNTIME_MISMATCH", mismatch[0], mismatch[1], "V0")
    canonical = derive_canonical(data, serialization_profile, producer_port)
    if canonical == "false":
        raise IGXError("SOURCE_WRITER_MISMATCH", "meta.source.source_canonical",
                       "the Python writer does not reproduce these bytes under this profile", "V4")
    eligibility, reason = classify_eligibility(data, serialization_profile)
    binding = ExtensionBinding(
        identity_claim=identity_claim, artifact_sha256=sha256_hex(data), serialization_profile=serialization_profile,
        source_canonical=canonical, source_semantic_eligibility=eligibility, source_semantic_reason=reason,
        core_writer_implementation=WRITER_OF_PORT[producer_port], core_writer_version=receipt.port_version,
        semantic_digest=None, semantic_digest_algorithm=None,
        core_format=baseline.core_format, core_version=baseline.core_version, core_commit=baseline.core_commit,
        core_semantic_spec=baseline.core_semantic_spec, core_vector_corpus_version=baseline.corpus_version,
        core_vector_corpus_commit=baseline.corpus_commit, core_vector_corpus_digest=baseline.corpus_digest,
        producer_port=producer_port, producer_port_version=receipt.port_version, producer_core_posture=receipt.posture,
        core_conformance_receipt=receipt.sha256, capabilities=tuple(capabilities), consumer=consumer,
    )
    baselines = {**BASELINES, baseline.core_commit: baseline}
    result = verify(binding, data, baselines=baselines, registry=registry)
    decision = admit(binding, result, policy=policy, baselines=baselines)
    if not decision.admitted:
        field = "meta.core_baseline.core_commit" if decision.code == "STALE_BINDING" else "meta.igx.identity_claim"
        raise IGXError(decision.code or "IDENTITY_CLAIM_INADMISSIBLE", field, "; ".join(decision.reasons), decision.step or "A2")
    return binding

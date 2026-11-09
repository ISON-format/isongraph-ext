"""Historical verification, V0-V5 (17 §4). Raises IGXError at the first failing step; returns only on full success."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .baselines import BASELINES, Baseline, Receipt, installed_core_runtime
from .binding import Capability, ExtensionBinding, check_shape
from .digest import sha256_hex
from .errors import IGXError
from .source import as_bytes, classify_eligibility, derive_canonical, load_source
from .registry import DEFAULT_REGISTRY, EMPTY_REGISTRY, CapabilityRegistry  # noqa: F401  (re-exported)
from .versions import parse_range, parse_version, range_admits


@dataclass(frozen=True)
class VerificationResult:
    binding_digest: str
    semantic_verification: str                 # "full" | "limited" (17 §4 V0)
    source_canonical: str | None               # derived in full mode; None in limited mode
    source_semantic_eligibility: str | None
    source_semantic_reason: str | None
    unrecognized_optional: tuple[Capability, ...]
    steps_passed: tuple[str, ...]


def resolve_baseline(binding: ExtensionBinding, baselines: Mapping[str, Baseline]) -> Baseline:
    try:
        return baselines[binding.core_commit]
    except KeyError:
        raise IGXError("CORE_BASELINE_UNSUPPORTED", "meta.core_baseline.core_commit",
                       f"unknown Core baseline {binding.core_commit}", "V2") from None


def _runtime_mismatch(baseline: Baseline) -> tuple[str, str] | None:
    """(field, detail) of the first difference between the installed Core and the baseline's recorded runtime, or None."""
    dist, hashes, writer = installed_core_runtime(baseline.core_runtime)
    if dist != baseline.core_runtime_dist:
        return ("ison-graph", f"installed {dist} != baseline {baseline.core_runtime_dist}")
    for module, expected in baseline.core_runtime.items():
        if hashes.get(module) != expected:
            return (module, f"installed {hashes.get(module)} != baseline {expected}")
    if writer != baseline.canonical_writer_dist:
        return ("ison-py", f"installed {writer} != baseline {baseline.canonical_writer_dist}")
    return None


def _v0(baseline: Baseline) -> str:
    """Returns the semantic verification mode. A retired baseline whose runtime is gone is 'limited', never an error."""
    mismatch = _runtime_mismatch(baseline)
    if mismatch is None:
        return "full"
    if baseline.retired:
        return "limited"
    raise IGXError("CORE_RUNTIME_MISMATCH", mismatch[0], mismatch[1], "V0")


def _v2(b: ExtensionBinding, base: Baseline) -> None:
    for field, mine, theirs in (("core_format", b.core_format, base.core_format), ("core_version", b.core_version, base.core_version),
                                ("core_semantic_spec", b.core_semantic_spec, base.core_semantic_spec)):
        if mine != theirs:
            raise IGXError("CORE_BASELINE_UNSUPPORTED", f"meta.core_baseline.{field}", f"{mine!r} != baseline {theirs!r}", "V2")
    for field, mine, theirs in (("core_vector_corpus_version", b.core_vector_corpus_version, base.corpus_version),
                                ("core_vector_corpus_commit", b.core_vector_corpus_commit, base.corpus_commit),
                                ("core_vector_corpus_digest", b.core_vector_corpus_digest, base.corpus_digest)):
        if mine != theirs:
            raise IGXError("CORPUS_DIGEST_MISMATCH", f"meta.core_baseline.{field}", f"{mine!r} != baseline {theirs!r}", "V2")


def _receipt_check(base: Baseline, port: str, version: str, posture: str, digest: str, prefix: str,
                   names: tuple[str, str, str, str]) -> Receipt:
    f_port, f_version, f_posture, f_digest = names
    receipt = base.receipts.get(port)
    if receipt is None:
        raise IGXError("RECEIPT_REFERENCE_INVALID", f"{prefix}.{f_port}", f"baseline has no receipt for {port}", "V3")
    if digest != receipt.sha256:
        raise IGXError("RECEIPT_REFERENCE_INVALID", f"{prefix}.{f_digest}", f"{digest} is not the {port} receipt {receipt.sha256}", "V3")
    if version != receipt.port_version:
        raise IGXError("RECEIPT_REFERENCE_INVALID", f"{prefix}.{f_version}", f"{version!r} != receipt {receipt.port_version!r}", "V3")
    if posture != receipt.posture:
        raise IGXError("RECEIPT_REFERENCE_INVALID", f"{prefix}.{f_posture}", f"{posture} != receipt {receipt.posture}", "V3")
    for name, mine, theirs in (("core_commit", receipt.core_commit, base.core_commit), ("core_format", receipt.core_format, base.core_format),
                               ("core_version", receipt.core_version, base.core_version), ("corpus_version", receipt.corpus_version, base.corpus_version),
                               ("corpus_commit", receipt.corpus_commit, base.corpus_commit), ("corpus_digest", receipt.corpus_digest, base.corpus_digest),
                               ("semantic_spec", receipt.semantic_spec, base.core_semantic_spec)):
        if mine != theirs:
            raise IGXError("RECEIPT_REFERENCE_INVALID", f"receipt.{name}", f"{port} receipt says {mine!r}, baseline {theirs!r}", "V3")
    return receipt


def _v3(b: ExtensionBinding, base: Baseline) -> None:
    _receipt_check(base, b.producer_port, b.producer_port_version, b.producer_core_posture, b.core_conformance_receipt, "meta.core_baseline",
                   ("producer_port", "producer_port_version", "producer_core_posture", "core_conformance_receipt"))
    if b.consumer is not None:
        c = b.consumer
        _receipt_check(base, c.port, c.port_version, c.posture, c.receipt_sha256, "meta.consumer",
                       ("consumer_port", "consumer_port_version", "consumer_core_posture", "consumer_conformance_receipt"))


def _v4(b: ExtensionBinding, source: bytes, mode: str) -> tuple[str | None, str | None, str | None]:
    actual = sha256_hex(source)
    if actual != b.artifact_sha256:
        raise IGXError("SOURCE_BINDING_MISMATCH", "meta.source.artifact_sha256", f"supplied bytes hash to {actual}", "V4")
    if mode == "limited":
        return None, None, None            # re-derivation needs the pinned runtime, which this install is not (17 §4 V0)
    loaded = load_source(source, b.serialization_profile)       # parse the artifact once for both questions below
    canonical = derive_canonical(source, b.serialization_profile, b.producer_port, loaded=loaded)
    if canonical != b.source_canonical:
        raise IGXError("SOURCE_WRITER_MISMATCH", "meta.source.source_canonical", f"derived {canonical!r}, stored {b.source_canonical!r}", "V4")
    eligibility, reason = classify_eligibility(source, b.serialization_profile, loaded=loaded)
    if (eligibility, reason) != (b.source_semantic_eligibility, b.source_semantic_reason):
        raise IGXError("SOURCE_ELIGIBILITY_MISMATCH", "meta.source.source_semantic_eligibility",
                       f"derived ({eligibility}, {reason}), stored ({b.source_semantic_eligibility}, {b.source_semantic_reason})", "V4")
    return canonical, eligibility, reason


def _v5(b: ExtensionBinding, registry: CapabilityRegistry) -> tuple[Capability, ...]:
    unrecognized: list[Capability] = []
    for cap in b.capabilities:
        registered = registry.get(cap.extension)
        admitted = registered is not None and range_admits(parse_range(cap.version_range), parse_version(registered))
        if cap.requirement == "REQUIRED" and not admitted:
            why = "not in registry" if registered is None else f"range {cap.version_range} excludes registered {registered}"
            raise IGXError("UNSUPPORTED_CAPABILITY", f"table.capabilities.{cap.extension}", why, "V5")
        if cap.requirement == "OPTIONAL" and not admitted:
            unrecognized.append(cap)
    return tuple(unrecognized)


def verify(binding: ExtensionBinding, source: str | bytes, *, baselines: Mapping[str, Baseline] = BASELINES,
           registry: CapabilityRegistry = DEFAULT_REGISTRY) -> VerificationResult:
    base = resolve_baseline(binding, baselines)      # unknown commit -> V2 (no baseline to run V0 against)
    mode = _v0(base)
    check_shape(binding)                              # V1 on programmatic bindings; from_ison already ran it on parsed ones
    _v2(binding, base)
    _v3(binding, base)
    canonical, eligibility, reason = _v4(binding, as_bytes(source), mode)
    unrecognized = _v5(binding, registry)
    return VerificationResult(binding_digest=binding.digest, semantic_verification=mode, source_canonical=canonical,
                              source_semantic_eligibility=eligibility, source_semantic_reason=reason,
                              unrecognized_optional=unrecognized, steps_passed=("V0", "V1", "V2", "V3", "V4", "V5"))

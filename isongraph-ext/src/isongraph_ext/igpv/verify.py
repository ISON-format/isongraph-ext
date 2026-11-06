"""IGPV/1 verification (18 §4.1): preflight, then P0–P5. Runs igx.verify() itself; never accepts a caller-supplied result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..igx.baselines import BASELINES, Baseline
from ..igx.binding import ExtensionBinding
from ..igx.digest import sha256_hex
from ..igx.registry import DEFAULT_REGISTRY, CapabilityRegistry
from ..igx.source import as_bytes
from ..igx.verify import VerificationResult
from ..igx.verify import verify as igx_verify
from ..igx.versions import parse_range, parse_version, range_admits
from . import records as R
from .errors import IGPVError
from .locators import line_count, locator_posture
from .payload import ProvenancePayload, check_references
from .resolve import load_graph, resolve_object

STEPS = ("P0", "P1", "P2", "P3", "P4", "P5")


@dataclass(frozen=True)
class ProvenanceVerification:
    payload_sha256: str
    binding_digest: str
    target_artifact_sha256: str
    object_resolution: str                  # "full" | "skipped"
    origin_resolution: Mapping[str, str]    # origin artifact_id -> "verified" | "unverified"
    locators: Mapping[str, str]             # attribution_id -> "VERIFIED" | "UNVERIFIED" (rows with a locator)
    counts: Mapping[str, int]
    steps_passed: tuple[str, ...]


def _limit(name: str, detail: str) -> IGPVError:
    return IGPVError("PROVENANCE_LIMIT_EXCEEDED", name, detail, "P1")


def _payload_bytes(payload: str | bytes | ProvenancePayload) -> bytes:
    if isinstance(payload, ProvenancePayload):
        return payload.to_ison().encode("utf-8")
    if isinstance(payload, str):
        try:
            return payload.encode("utf-8")
        except UnicodeEncodeError as e:
            raise IGPVError("MALFORMED_PROVENANCE", "document", f"text is not UTF-8-encodable: {e}", "P1") from None
    return payload


def _preflight(target: bytes, sources: Mapping[str, bytes], limits: R.Limits) -> None:
    """Byte budgets on lengths only (18 §4.1 preflight): target and the aggregate of supplied sources, before anything is
    parsed or serialized. The per-graph bound on origin graphs is applied once P1 has identified which sources are graphs."""
    if len(target) > limits.max_graph_bytes:
        raise _limit("max_graph_bytes", f"target {len(target)} > {limits.max_graph_bytes}")
    total = sum(len(data) for data in sources.values())
    if total > limits.max_sources_bytes:
        raise _limit("max_sources_bytes", f"supplied sources total {total} > {limits.max_sources_bytes}")


def _graph_budget(p: ProvenancePayload, supplied: Mapping[str, bytes], limits: R.Limits) -> None:
    """P1 (after parsing): every supplied origin graph must fit max_graph_bytes before any Core loader sees it."""
    for a in p.artifacts:
        if a.kind == "isongraph" and a.artifact_sha256 in supplied and len(supplied[a.artifact_sha256]) > limits.max_graph_bytes:
            raise _limit("max_graph_bytes", f"origin graph {a.artifact_id} {len(supplied[a.artifact_sha256])} > {limits.max_graph_bytes}")


def _p0(binding: ExtensionBinding, payload_bytes: bytes, target: bytes, baselines, registry) -> VerificationResult:
    result = igx_verify(binding, target, baselines=baselines, registry=registry)
    row = next((c for c in binding.capabilities if c.extension == R.CAPABILITY), None)
    if row is None or row.payload_sha256 is None:
        raise IGPVError("PROVENANCE_NOT_BOUND", "table.capabilities.igpv", "the binding declares no igpv payload digest", "P0")
    if not range_admits(parse_range(row.version_range), parse_version(R.CAPABILITY_VERSION)):
        raise IGPVError("PROVENANCE_VERSION_UNSUPPORTED", "table.capabilities.igpv.version_range",
                        f"{row.version_range} excludes IGPV/1 ({R.CAPABILITY_VERSION})", "P0")
    actual = sha256_hex(payload_bytes)
    if actual != row.payload_sha256:
        raise IGPVError("PAYLOAD_DIGEST_MISMATCH", "table.capabilities.igpv.payload_sha256", f"payload bytes hash to {actual}", "P0")
    return result


def _supplied(sources: Mapping[str, bytes]) -> dict[str, bytes]:
    """Only lowercase 64-hex keys count as supplied artifacts; anything else is ignored (never matched loosely)."""
    return {k: v for k, v in sources.items() if R.is_str(k) and R.HEX64.fullmatch(k) is not None and isinstance(v, bytes)}


def _check_supplied(artifact: R.Artifact, data: bytes, step: str) -> None:
    w = f"table.artifacts.{artifact.artifact_id}"
    actual = sha256_hex(data)
    if actual != artifact.artifact_sha256:
        raise IGPVError("SOURCE_ARTIFACT_MISMATCH", f"{w}.artifact_sha256", f"supplied bytes hash to {actual}", step)
    if len(data) != artifact.size:
        raise IGPVError("SOURCE_ARTIFACT_MISMATCH", f"{w}.size", f"supplied bytes are {len(data)} bytes, declared {artifact.size}", step)


def _sorted_ids(items, key):
    return sorted(items, key=lambda x: key(x).encode("utf-8", "surrogatepass"))


def verify(payload: str | bytes | ProvenancePayload, binding: ExtensionBinding, target: str | bytes, *,
           sources: Mapping[str, bytes] | None = None, limits: R.Limits = R.DEFAULT_LIMITS,
           baselines: Mapping[str, Baseline] = BASELINES, registry: CapabilityRegistry = DEFAULT_REGISTRY,
           ) -> tuple[VerificationResult, ProvenanceVerification]:
    sources = {} if sources is None else sources
    target_bytes = as_bytes(target)
    _preflight(target_bytes, sources, limits)                 # before any parser or serializer touches anything
    payload_bytes = _payload_bytes(payload)                   # an in-memory payload is serialized here: check() runs as part of it,
    if len(payload_bytes) > limits.max_payload_bytes:         # so its shape faults precede the payload-byte budget by necessity
        raise _limit("max_payload_bytes", f"payload {len(payload_bytes)} > {limits.max_payload_bytes}")
    igx_result = _p0(binding, payload_bytes, target_bytes, baselines, registry)                 # P0
    if isinstance(payload, ProvenancePayload):                                                  # P1
        p = payload
        for name in ("artifacts", "producers", "objects", "attributions", "derivations"):
            if len(getattr(p, name)) > limits.max_rows_per_table:
                raise _limit("max_rows_per_table", f"table.{name} has {len(getattr(p, name))} rows > {limits.max_rows_per_table}")
    else:
        p = ProvenancePayload.from_ison(payload_bytes, limits=limits)
    supplied = _supplied(sources)
    _graph_budget(p, supplied, limits)                                                          # P1: origin graphs vs max_graph_bytes
    actual = sha256_hex(target_bytes)                                                           # P2
    if p.target_artifact_sha256 != actual:
        raise IGPVError("TARGET_BINDING_MISMATCH", "meta.igpv.target_artifact_sha256", f"target bytes hash to {actual}", "P2")
    if p.target_artifact_sha256 != binding.artifact_sha256:
        raise IGPVError("TARGET_BINDING_MISMATCH", "meta.igpv.target_artifact_sha256", f"binding names {binding.artifact_sha256}", "P2")
    if p.target_serialization_profile != binding.serialization_profile:
        raise IGPVError("TARGET_BINDING_MISMATCH", "meta.igpv.target_serialization_profile",
                        f"{p.target_serialization_profile} != binding {binding.serialization_profile}", "P2")
    check_references(p)                                                                         # P3
    arts = {a.artifact_id: a for a in p.artifacts}
    origin_ids = sorted({o.graph for o in p.objects if o.graph is not None}, key=lambda s: s.encode("utf-8"))
    origin_resolution: dict[str, str] = {}
    checked: dict[str, bytes] = {}      # artifact_id -> supplied bytes, digest and size verified exactly once

    def supplied_for(a: R.Artifact, step: str) -> bytes | None:
        data = supplied.get(a.artifact_sha256)
        if data is not None and a.artifact_id not in checked:
            _check_supplied(a, data, step)
            checked[a.artifact_id] = data
        return data

    if igx_result.semantic_verification == "full":                                              # P4
        graph = load_graph(target_bytes, binding.serialization_profile, "target")
        for o in _sorted_ids(p.objects, lambda o: o.object_id):
            if o.graph is None:
                resolve_object(graph, o, f"table.objects.{o.object_id}")
        object_resolution = "full"
        for aid in origin_ids:
            a = arts[aid]
            data = supplied_for(a, "P4")
            if data is None:
                origin_resolution[aid] = "unverified"
                continue
            g = load_graph(data, a.serialization_profile, f"table.artifacts.{aid}")
            for o in _sorted_ids(p.objects, lambda o: o.object_id):
                if o.graph == aid:
                    resolve_object(g, o, f"table.objects.{o.object_id}")
            origin_resolution[aid] = "verified"
    else:
        object_resolution = "skipped"
        origin_resolution = {aid: "unverified" for aid in origin_ids}
    # P5: every supplied artifact is digest/size-checked once (locator or not), then postures are per-row lookups
    for a in _sorted_ids(p.artifacts, lambda a: a.artifact_id):
        supplied_for(a, "P5")
    lines: dict[str, int] = {}
    locators: dict[str, str] = {}
    for at in _sorted_ids(p.attributions, lambda a: a.attribution_id):
        if at.locator is None:
            continue
        data = checked.get(at.artifact_id)
        total = None
        if data is not None and at.locator.type == "lines/1":
            total = lines.setdefault(at.artifact_id, line_count(data))
        locators[at.attribution_id] = locator_posture(at.locator, data, f"table.attributions.{at.attribution_id}", line_total=total)
    counts = {name: len(getattr(p, name)) for name in ("artifacts", "producers", "objects", "attributions", "derivations")}
    return igx_result, ProvenanceVerification(
        payload_sha256=sha256_hex(payload_bytes), binding_digest=binding.digest, target_artifact_sha256=p.target_artifact_sha256,
        object_resolution=object_resolution, origin_resolution=origin_resolution, locators=locators, counts=counts, steps_passed=STEPS)

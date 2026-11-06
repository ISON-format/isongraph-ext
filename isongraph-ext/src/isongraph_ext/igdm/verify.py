"""IGDM/1 verification (19 §3.1): preflight, then D0–D4. Runs igx.verify() itself; never accepts a caller-supplied result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..igpv.records import GraphObject
from ..igpv.resolve import load_graph as _igpv_load_graph
from ..igpv.resolve import resolve_object as _igpv_resolve_object
from ..igx.baselines import BASELINES, Baseline
from ..igx.binding import ExtensionBinding
from ..igx.digest import sha256_hex
from ..igx.registry import DEFAULT_REGISTRY, CapabilityRegistry
from ..igx.source import as_bytes
from ..igx.verify import VerificationResult
from ..igx.verify import verify as igx_verify
from ..igx.versions import parse_range, parse_version, range_admits
from . import records as R
from .errors import IGDMError
from .payload import DatamaticsPayload, check_references, edge_key, node_key, unrecognized_roles

STEPS = ("D0", "D1", "D2", "D3", "D4")


@dataclass(frozen=True)
class DatamaticsVerification:
    payload_sha256: str
    binding_digest: str
    target_artifact_sha256: str
    object_resolution: str                 # "full" | "skipped"
    unrecognized_roles: tuple[str, ...]
    counts: Mapping[str, int]
    steps_passed: tuple[str, ...]


def _limit(name: str, detail: str) -> IGDMError:
    return IGDMError("DATAMATICS_LIMIT_EXCEEDED", name, detail, "D1")


def _payload_bytes(payload: str | bytes | DatamaticsPayload) -> bytes:
    if isinstance(payload, DatamaticsPayload):
        return payload.to_ison().encode("utf-8")
    if isinstance(payload, str):
        try:
            return payload.encode("utf-8")
        except UnicodeEncodeError as e:
            raise IGDMError("MALFORMED_DATAMATICS", "document", f"text is not UTF-8-encodable: {e}", "D1") from None
    return payload


def _p4_error(e: Exception, where: str) -> IGDMError:
    """igpv.resolve raises IGPVError with step P4; re-badge it as an IGDMError at D4 with the IGDM row field."""
    col = getattr(e, "field", where).rsplit(".", 1)[-1]
    return IGDMError("UNRESOLVED_OBJECT", f"{where}.{col}", getattr(e, "detail", str(e)), "D4")


def _resolve(graph, obj: GraphObject, where: str) -> None:
    try:
        _igpv_resolve_object(graph, obj, where)
    except Exception as e:
        raise _p4_error(e, where) from None


def verify(payload: str | bytes | DatamaticsPayload, binding: ExtensionBinding, target: str | bytes, *,
           limits: R.Limits = R.DEFAULT_LIMITS, baselines: Mapping[str, Baseline] = BASELINES,
           registry: CapabilityRegistry = DEFAULT_REGISTRY) -> tuple[VerificationResult, DatamaticsVerification]:
    target_bytes = as_bytes(target)
    if len(target_bytes) > limits.max_graph_bytes:                                            # preflight
        raise _limit("max_graph_bytes", f"target {len(target_bytes)} > {limits.max_graph_bytes}")
    payload_bytes = _payload_bytes(payload)
    if len(payload_bytes) > limits.max_payload_bytes:
        raise _limit("max_payload_bytes", f"payload {len(payload_bytes)} > {limits.max_payload_bytes}")
    igx_result = igx_verify(binding, target_bytes, baselines=baselines, registry=registry)   # D0
    row = next((c for c in binding.capabilities if c.extension == R.CAPABILITY), None)
    if row is None or row.payload_sha256 is None:
        raise IGDMError("DATAMATICS_NOT_BOUND", "table.capabilities.igdm", "the binding declares no igdm payload digest", "D0")
    if not range_admits(parse_range(row.version_range), parse_version(R.CAPABILITY_VERSION)):
        raise IGDMError("DATAMATICS_VERSION_UNSUPPORTED", "table.capabilities.igdm.version_range", f"{row.version_range} excludes IGDM/1", "D0")
    actual = sha256_hex(payload_bytes)
    if actual != row.payload_sha256:
        raise IGDMError("PAYLOAD_DIGEST_MISMATCH", "table.capabilities.igdm.payload_sha256", f"payload bytes hash to {actual}", "D0")
    if isinstance(payload, DatamaticsPayload):                                                 # D1
        p = payload
        for name in ("nodes", "edges", "groups", "members"):
            if len(getattr(p, name)) > limits.max_rows_per_table:
                raise _limit("max_rows_per_table", f"table.{name} has {len(getattr(p, name))} rows > {limits.max_rows_per_table}")
    else:
        p = DatamaticsPayload.from_ison(payload_bytes, limits=limits)
    t_actual = sha256_hex(target_bytes)                                                        # D2
    if p.target_artifact_sha256 != t_actual:
        raise IGDMError("TARGET_BINDING_MISMATCH", "meta.igdm.target_artifact_sha256", f"target bytes hash to {t_actual}", "D2")
    if p.target_artifact_sha256 != binding.artifact_sha256:
        raise IGDMError("TARGET_BINDING_MISMATCH", "meta.igdm.target_artifact_sha256", f"binding names {binding.artifact_sha256}", "D2")
    if p.target_serialization_profile != binding.serialization_profile:
        raise IGDMError("TARGET_BINDING_MISMATCH", "meta.igdm.target_serialization_profile",
                        f"{p.target_serialization_profile} != binding {binding.serialization_profile}", "D2")
    check_references(p, limits)                                                                # D3
    if igx_result.semantic_verification == "full":                                            # D4
        try:
            graph = _igpv_load_graph(target_bytes, binding.serialization_profile, "target")
        except Exception as e:
            raise IGDMError("UNRESOLVED_OBJECT", "target", getattr(e, "detail", str(e)), "D4") from None
        for n in p.nodes:
            _resolve(graph, GraphObject("n", "node", node=n.node), f"table.nodes.{node_key(n.node)}")
        for e in p.edges:
            _resolve(graph, GraphObject("e", "edge", edge=e.edge), f"table.edges.{edge_key(e.edge)}")
        for m in p.members:
            _resolve(graph, GraphObject("m", "node", node=m.node), f"table.members.{m.group_id}/{node_key(m.node)}")
        object_resolution = "full"
    else:
        object_resolution = "skipped"
    counts = {name: len(getattr(p, name)) for name in ("nodes", "edges", "groups", "members")}
    return igx_result, DatamaticsVerification(payload_sha256=actual, binding_digest=binding.digest, target_artifact_sha256=p.target_artifact_sha256,
                                              object_resolution=object_resolution, unrecognized_roles=unrecognized_roles(p),
                                              counts=counts, steps_passed=STEPS)

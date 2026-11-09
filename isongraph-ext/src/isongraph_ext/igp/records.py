"""IGP/1 constants, policy record, limits and result (21 §1, §3, §4.3, §5). Construction never validates; Policy.check() does."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..igpv import DEFAULT_LIMITS as IGPV_DEFAULT_LIMITS
from ..igpv import Limits as IGPVLimits
from ..igpv import NodeRef, ProvenancePayload
from ..igpv.resolve import node_ref_key

IGP_SPEC = "IGP/1"
IGP_IMPLEMENTATION_VERSION = "1.0.0"      # bumped only when observable projection semantics change (21 §3.1), never with the package
DIRECTIONS = ("out", "in", "both")
DEPTH_MAX = 1_048_576
META_FIELDS = ("depth", "direction", "max_edges", "max_nodes", "policy_spec")


def utf8(s: str) -> bytes:
    return s.encode("utf-8", "surrogatepass")


@dataclass(frozen=True)
class Limits:
    max_policy_bytes: int = 16 * 1024 * 1024
    max_source_bytes: int = 256 * 1024 * 1024
    max_rows_per_table: int = 1_048_576
    max_depth: int = DEPTH_MAX
    lineage: IGPVLimits = IGPV_DEFAULT_LIMITS


DEFAULT_LIMITS = Limits()


@dataclass(frozen=True)
class Policy:
    anchors: tuple[NodeRef, ...]
    mandatory: tuple[NodeRef, ...] = ()
    node_types: tuple[str, ...] = ()
    relations: tuple[str, ...] = ()
    direction: str = "out"
    depth: int = 1
    max_nodes: int | None = None
    max_edges: int | None = None

    def __post_init__(self) -> None:
        # Held in stable key order so equality does not depend on construction or wire order (as igpv/igdm payloads).
        def norm(rows, key):
            try:
                return tuple(sorted(rows, key=key))
            except Exception:
                return tuple(rows)
        object.__setattr__(self, "anchors", norm(self.anchors, node_ref_key))
        object.__setattr__(self, "mandatory", norm(self.mandatory, node_ref_key))
        object.__setattr__(self, "node_types", norm(self.node_types, utf8))
        object.__setattr__(self, "relations", norm(self.relations, utf8))

    def to_ison(self) -> str:
        from . import policy
        return policy.to_ison(self)

    @property
    def digest(self) -> str:
        from . import policy
        return policy.digest(self)

    @classmethod
    def from_ison(cls, text, *, limits: "Limits" = DEFAULT_LIMITS) -> "Policy":
        from . import policy
        return policy.from_ison(text, limits=limits)


@dataclass(frozen=True)
class Projection:
    result_bytes: bytes
    payload: ProvenancePayload
    policy_sha256: str
    stats: Mapping[str, Any]

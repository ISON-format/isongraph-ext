"""IGPV/1 records, token grammars and limits (18 §1, §2, §4.3, §5.1). Construction never validates; payload.check() does."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PROVENANCE_SPEC = "IGPV/1"
CAPABILITY = "igpv"
CAPABILITY_VERSION = "1.0.0"
CAPABILITY_RANGE = "^1"
PROFILES = ("ison-v1", "isonl-v1")
ARTIFACT_KINDS = ("document", "isongraph")
PRODUCER_KINDS = ("extractor", "transformation")
OBJECT_KINDS = ("graph", "node", "edge")
DERIVATION_KINDS = ("identity", "collapse", "rewrite")
LOCATOR_SPAN_TYPES = ("bytes/1", "lines/1")

KEY_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
HEX64 = re.compile(r"[0-9a-f]{64}")
ORDINAL = re.compile(r"0|[1-9][0-9]*")
MEDIA_TYPE = re.compile(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+")
X_LOCATOR = re.compile(r"x-[a-z0-9-]+/[1-9][0-9]*")
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
_IDENTIFIER_FORBIDDEN = set(':|"\\')


def is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_str(v: Any) -> bool:
    return isinstance(v, str)


def is_identifier(s: Any) -> bool:
    """Core's identifier rule: non-empty, no whitespace, none of : | " \\ (ison_graph._check_identifier)."""
    return is_str(s) and s != "" and not any(c.isspace() or c in _IDENTIFIER_FORBIDDEN for c in s)


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    artifact_sha256: str
    kind: str
    size: int
    media_type: str | None = None
    revision: str | None = None
    uri: str | None = None
    serialization_profile: str | None = None


@dataclass(frozen=True)
class Producer:
    producer_id: str
    kind: str
    implementation: str
    version: str
    spec: str | None = None
    policy_sha256: str | None = None


@dataclass(frozen=True)
class NodeRef:
    node_type: str
    node_id: int | str


@dataclass(frozen=True)
class EdgeAddress:
    source: NodeRef
    relation: str
    target: NodeRef
    ordinal: str = "0"


@dataclass(frozen=True)
class GraphObject:
    object_id: str
    kind: str
    graph: str | None = None          # artifact_id of an origin graph, or None = the target graph
    node: NodeRef | None = None
    edge: EdgeAddress | None = None


@dataclass(frozen=True)
class Locator:
    type: str
    start: int | None = None
    end: int | None = None
    text: str | None = None


@dataclass(frozen=True)
class Attribution:
    attribution_id: str
    object_id: str
    artifact_id: str
    producer_id: str
    locator: Locator | None = None


@dataclass(frozen=True)
class Derivation:
    derivation_id: str
    derived_object_id: str
    origin_object_id: str
    producer_id: str
    kind: str


@dataclass(frozen=True)
class Limits:
    max_payload_bytes: int = 64 * 1024 * 1024
    max_graph_bytes: int = 256 * 1024 * 1024
    max_sources_bytes: int = 1024 * 1024 * 1024
    max_rows_per_table: int = 1_048_576
    max_lineage_depth: int = 64
    max_lineage_visits: int = 1_048_576


DEFAULT_LIMITS = Limits()


@dataclass(frozen=True)
class LineageStep:
    depth: int
    graph_sha256: str
    obj: NodeRef | EdgeAddress | None
    kind: str | None                 # derivation kind that produced this step; None on a terminal
    producer: Producer | None
    terminal: str | None             # "no_derivation_record" | "payload_unavailable" | None

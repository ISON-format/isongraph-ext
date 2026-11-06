"""IGDM/1 vocabularies, records and limits (19 §1, §3.3, §4). Construction never validates; payload.check() does."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..igpv.records import EdgeAddress, NodeRef

DATAMATICS_SPEC = "IGDM/1"
CAPABILITY = "igdm"
CAPABILITY_VERSION = "1.0.0"
CAPABILITY_RANGE = "^1"
PROFILES = ("ison-v1", "isonl-v1")

ROLES = ("neutral", "active", "inactive", "selected", "warning", "negative", "positive", "info", "emphasis-high", "emphasis-low")
SHAPE_ROLES = ("circle", "square", "diamond", "hexagon", "triangle", "pill", "document", "person", "process")
PATTERN_ROLES = ("solid", "dashed", "dotted", "double")
EMPHASIS = ("none", "low", "medium", "high")
VISIBILITY = ("visible", "collapsed", "hidden")
DIRECTION_DISPLAY = ("forward", "backward", "both", "none")
TEMPORAL_STATES = ("introduced", "changed", "removed", "steady")
INTENTS = ("hull", "hierarchy", "collapse", "aggregate")
FAMILIES = ("force", "layered", "radial", "grid", "geographic", "manual")
DIRECTIONS = ("TB", "BT", "LR", "RL")
STABILITY = ("stable", "free")
X_TOKEN = re.compile(r"x-[a-z0-9-]+")
LOD_MAX = 1024
BADGE_MAX = 16

META_FIELDS = ("datamatics_spec", "target_artifact_sha256", "target_serialization_profile")
LAYOUT_FIELDS = ("family", "direction", "stability")
NODE_FIELDS = ("node_type", "node_id", "magnitude", "role", "shape_role", "emphasis", "badge", "ring", "label", "visibility",
               "lod_min", "selectable", "focusable", "expandable", "drilldown", "temporal_state", "temporal_order",
               "layout_rank", "layout_anchor", "a11y_text", "a11y_role")
EDGE_FIELDS = ("source_type", "source_id", "relation", "target_type", "target_id", "ordinal", "role", "pattern_role", "emphasis",
               "direction_display", "label", "visibility", "lod_min", "selectable", "focusable", "temporal_state",
               "temporal_order", "a11y_text")
GROUP_FIELDS = ("group_id", "intent", "parent_group_id", "label", "role", "collapsed", "visibility", "lod_min", "a11y_text")
MEMBER_FIELDS = ("group_id", "node_type", "node_id")
NODE_HINTS = NODE_FIELDS[2:]
EDGE_HINTS = EDGE_FIELDS[6:]
BOOL_COLUMNS = {"selectable", "focusable", "expandable", "drilldown", "layout_anchor", "collapsed"}


@dataclass(frozen=True)
class NodeHints:
    node: NodeRef
    magnitude: float | int | None = None
    role: str | None = None
    shape_role: str | None = None
    emphasis: str | None = None
    badge: str | None = None
    ring: str | None = None
    label: str | None = None
    visibility: str | None = None
    lod_min: int | None = None
    selectable: bool | None = None
    focusable: bool | None = None
    expandable: bool | None = None
    drilldown: bool | None = None
    temporal_state: str | None = None
    temporal_order: int | None = None
    layout_rank: int | None = None
    layout_anchor: bool | None = None
    a11y_text: str | None = None
    a11y_role: str | None = None


@dataclass(frozen=True)
class EdgeHints:
    edge: EdgeAddress
    role: str | None = None
    pattern_role: str | None = None
    emphasis: str | None = None
    direction_display: str | None = None
    label: str | None = None
    visibility: str | None = None
    lod_min: int | None = None
    selectable: bool | None = None
    focusable: bool | None = None
    temporal_state: str | None = None
    temporal_order: int | None = None
    a11y_text: str | None = None


@dataclass(frozen=True)
class Group:
    group_id: str
    intent: str
    parent_group_id: str | None = None
    label: str | None = None
    role: str | None = None
    collapsed: bool | None = None
    visibility: str | None = None
    lod_min: int | None = None
    a11y_text: str | None = None


@dataclass(frozen=True)
class Member:
    group_id: str
    node: NodeRef


@dataclass(frozen=True)
class LayoutHints:
    family: str | None = None
    direction: str | None = None
    stability: str | None = None


@dataclass(frozen=True)
class Limits:
    max_payload_bytes: int = 64 * 1024 * 1024
    max_graph_bytes: int = 256 * 1024 * 1024
    max_rows_per_table: int = 1_048_576
    max_group_depth: int = 64


DEFAULT_LIMITS = Limits()

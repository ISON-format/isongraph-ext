# isongraph-ext/src/isongraph_ext/igdc/derive.py
"""IGDC/1 derivation (26 §3): a pure function of a verified IGDM/1 payload and two facts about the target."""
from __future__ import annotations

from collections.abc import Mapping

from ison_graph.multigraph import MultiGraph

from ..igdm import records as R
from ..igdm.payload import DatamaticsPayload
from ..igdm.verify import verify as igdm_verify
from ..igpv.resolve import load_graph
from ..igx.baselines import BASELINES, Baseline
from ..igx.binding import ExtensionBinding
from ..igx.digest import sha256_hex
from ..igx.registry import DEFAULT_REGISTRY, CapabilityRegistry
from ..igx.source import as_bytes
from .address import edge_address, node_address
from .errors import IGDCError
from .hints import EDGE_COLUMNS, GROUP_COLUMNS, LAYOUT_COLUMNS, NODE_COLUMNS, X_SPLIT, HintSet


def _tok(v: bool | None) -> str | None:
    return None if v is None else ("true" if v else "false")


def _split(value, col: str, out: dict, xcols: tuple[str, ...]) -> None:
    """26 §2.2: a closed value stays in `col`; an x- token moves to `col_x`; never both."""
    if col in xcols and isinstance(value, str) and R.X_TOKEN.fullmatch(value):
        out[col], out[col + "_x"] = None, value
    else:
        out[col] = value
        if col in xcols:
            out[col + "_x"] = None


def _row(cols: tuple[str, ...], values: dict, xcols: tuple[str, ...], bools: set[str]) -> dict:
    out: dict = {}
    for c in cols:
        if c.endswith("_x") and c[:-2] in xcols:
            continue                          # filled by _split
        v = values.get(c)
        if c in bools:
            v = _tok(v)
        _split(v, c, out, xcols)
    return {c: out.get(c) for c in cols}


def derive(p: DatamaticsPayload, *, directed: bool, multigraph: bool, payload_bytes: bytes) -> HintSet:
    nodes, edges, groups, members = [], [], [], []
    for n in p.nodes:
        a = node_address(n.node)
        vals = {c: getattr(n, c) for c in R.NODE_HINTS} | {"node_type": a.node_type, "node_id": a.node_id}
        nodes.append(_row(NODE_COLUMNS, vals, X_SPLIT["nodes"], R.BOOL_COLUMNS))
    for e in p.edges:
        a = edge_address(e.edge, directed=directed, multigraph=multigraph)
        vals = {c: getattr(e, c) for c in R.EDGE_HINTS} | {"source_type": a.source.node_type, "source_id": a.source.node_id, "relation": a.relation,
                                                            "target_type": a.target.node_type, "target_id": a.target.node_id, "ordinal": a.ordinal}
        edges.append(_row(EDGE_COLUMNS, vals, X_SPLIT["edges"], R.BOOL_COLUMNS))
    for g in p.groups:
        groups.append(_row(GROUP_COLUMNS, {c: getattr(g, c) for c in R.GROUP_FIELDS}, X_SPLIT["groups"], R.BOOL_COLUMNS))
    for m in p.members:
        a = node_address(m.node)
        members.append({"group_id": m.group_id, "node_type": a.node_type, "node_id": a.node_id})
    layout = _row(LAYOUT_COLUMNS, {"family": p.layout.family, "direction": p.layout.direction, "stability": p.layout.stability}, X_SPLIT["layout"], set())
    meta = {"consumption_spec": "IGDC/1", "address_scheme": "igs-addr/1", "igdm_payload_sha256": sha256_hex(payload_bytes),
            "target_artifact_sha256": p.target_artifact_sha256, "target_directed": _tok(directed), "target_multigraph": _tok(multigraph),
            "target_serialization_profile": p.target_serialization_profile}
    return HintSet(meta, layout, tuple(nodes), tuple(edges), tuple(groups), tuple(members))


def consume(payload: bytes | str, binding: ExtensionBinding, target: bytes | str, *, limits: R.Limits = R.DEFAULT_LIMITS,
            baselines: Mapping[str, Baseline] = BASELINES, registry: CapabilityRegistry = DEFAULT_REGISTRY) -> HintSet:
    payload_bytes, target_bytes = as_bytes(payload), as_bytes(target)
    _, dm = igdm_verify(payload_bytes, binding, target_bytes, limits=limits, baselines=baselines, registry=registry)   # errors propagate unwrapped
    if dm.object_resolution != "full":                                                                                  # P0
        raise IGDCError("RESOLUTION_REQUIRED", "object_resolution", "IGDC/1 needs a full verification: this one skipped object resolution (limited runtime)", "P0")
    p = DatamaticsPayload.from_ison(payload_bytes, limits=limits)
    graph = load_graph(target_bytes, binding.serialization_profile, "target")
    h = derive(p, directed=bool(getattr(graph, "directed", True)), multigraph=isinstance(graph, MultiGraph), payload_bytes=payload_bytes)
    size = len(h.to_ison().encode("utf-8"))                                                                              # P1
    if size > limits.max_payload_bytes:
        raise IGDCError("DATAMATICS_LIMIT_EXCEEDED", "max_payload_bytes", f"the derived hint document is {size} bytes > {limits.max_payload_bytes}", "P1")
    return h

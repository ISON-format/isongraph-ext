"""Q1: exact source acceptance (21 §4.1). A permissive from_ison() success is not evidence of the required profile."""

from __future__ import annotations

from ison_graph import ISONGraph
from ison_parser import loads

from ..igpv.records import INT64_MAX, INT64_MIN, is_int
from ..igx.source import MULTIGRAPH_FORMAT
from .errors import IGPError
from .records import Limits


def _no(field: str, detail: str) -> IGPError:
    return IGPError("SOURCE_UNSUPPORTED", field, detail, "Q1")


def load_source(data: bytes, limits: Limits) -> ISONGraph:
    if len(data) > limits.max_source_bytes:
        raise IGPError("PROJECTION_LIMIT_EXCEEDED", "max_source_bytes", f"{len(data)} > {limits.max_source_bytes}", "Q1")
    try:
        text = data.decode("utf-8")                                    # 1. strict UTF-8
    except UnicodeDecodeError as e:
        raise _no("source", f"not UTF-8: {e}") from None
    try:
        doc = loads(text)                                              # 2. an ISON document, not an ISONL one
    except Exception as e:
        raise _no("source", f"not an ISON document: {e}") from None
    for b in doc.blocks:                                               # 3. not a MultiGraph document
        if (b.kind, b.name) == ("meta", "graph") and any(r.get("format") == MULTIGRAPH_FORMAT for r in b.rows):
            raise _no("meta.graph.format", f"{MULTIGRAPH_FORMAT} documents are not supported")
    try:
        g = ISONGraph.from_ison(text)                                  # 4. Core loads it (twin ids fail here) ...
    except Exception as e:
        raise _no("source", f"Core cannot load it as a simple graph: {e}") from None
    if not g.directed:
        raise _no("meta.graph.directed", "undirected graphs are not supported")        # ... and it is directed
    emitted = g.to_ison().encode("utf-8")                              # 5. canonical ison-v1 profile (same test as IGX source_canonical)
    if data not in (emitted, emitted + b"\n"):
        raise _no("source", "bytes are not the Core writer's output for this graph (not canonical ison-v1)")
    for n in g.nodes():                                                # 6. NodeRef/2 addresses
        if is_int(n.id) and not (INT64_MIN <= n.id <= INT64_MAX):
            raise _no(f"nodes.{n.type}.{n.id}", "integer id outside INT64")
    return g

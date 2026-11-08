"""Runtime-derived facts about the source artifact (17 §4 V4, §4.1). Never trust the caller for these.

Value domain note (17 §4.1): ISON values are scalars only - integer, float, boolean, string, null, reference;
a bracketed or braced token parses as a string - so node ids plus node and edge property values are the whole
domain the eligibility classifier has to inspect.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from ison_graph import MULTIGRAPH_FORMAT, ISONGraph
from ison_graph.multigraph import MultiGraph
from ison_parser import loads, loads_isonl

from .errors import IGXError

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


def as_bytes(source: str | bytes) -> bytes:
    """A str is UTF-8 encoded as given; a str with no UTF-8 encoding (lone surrogates) has no bytes to bind."""
    if isinstance(source, str):
        try:
            return source.encode("utf-8")
        except UnicodeEncodeError as e:
            raise IGXError("SOURCE_BINDING_MISMATCH", "source", f"source text is not UTF-8-encodable: {e}", "V4") from None
    return source


def _parse(text: str, profile: str):
    return loads_isonl(text) if profile == "isonl-v1" else loads(text)


def _is_multigraph_document(doc) -> bool:
    for b in doc.blocks:
        if (b.kind, b.name) == ("meta", "graph"):
            for row in b.rows:
                if row.get("format") == MULTIGRAPH_FORMAT:
                    return True
    return False


def _load(source: bytes, profile: str):
    """Load with the pinned Python Core using the profile's loader. Raises on anything the Core rejects."""
    text = source.decode("utf-8")  # strict: a non-UTF-8 artifact is not the writer's output
    doc = _parse(text, profile)
    cls = MultiGraph if _is_multigraph_document(doc) else ISONGraph
    graph = cls.from_isonl(text) if profile == "isonl-v1" else cls.from_ison(text)
    return graph, doc


class Loaded(NamedTuple):
    """The outcome of loading a source once. `error` is set when the pinned Core rejects it; then graph and doc are None."""

    graph: Any
    doc: Any
    error: Exception | None


def load_source(source: bytes, profile: str) -> Loaded:
    """Load once. A source the Core rejects is an answer, not an exception: callers map `error` to their own outcome ("false" for
    canonicality, "unclassified" for eligibility). Pass the result to derive_canonical / classify_eligibility so one verification
    parses the artifact once instead of once per question."""
    try:
        graph, doc = _load(source, profile)
    except Exception as e:
        return Loaded(None, None, e)
    return Loaded(graph, doc, None)


def _emit(graph, profile: str) -> bytes:
    return (graph.to_isonl() if profile == "isonl-v1" else graph.to_ison()).encode("utf-8")


def derive_canonical(source: bytes, profile: str, producer_port: str, *, loaded: Loaded | None = None) -> str:
    if producer_port != "python":
        return "unverified"
    if loaded is None:
        loaded = load_source(source, profile)
    if loaded.error is not None:
        return "false"
    try:
        emitted = _emit(loaded.graph, profile)
    except Exception:
        return "false"
    return "true" if source in (emitted, emitted + b"\n") else "false"


def _int_out_of_range(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and not (INT64_MIN <= value <= INT64_MAX)


def classify_eligibility(source: bytes, profile: str, *, loaded: Loaded | None = None) -> tuple[str, str | None]:
    if loaded is None:
        loaded = load_source(source, profile)
    if loaded.error is not None:
        return ("unclassified", None)
    graph, doc = loaded.graph, loaded.doc
    if _is_multigraph_document(doc):
        return ("ineligible", "MULTIGRAPH_DOCUMENT")
    for node in graph.nodes():
        if _int_out_of_range(node.id) or any(_int_out_of_range(v) for v in node.properties.values()):
            return ("ineligible", "INTEGER_OUT_OF_INT64")
    for edge in graph.edges():
        if any(_int_out_of_range(v) for v in edge.properties.values()):
            return ("ineligible", "INTEGER_OUT_OF_INT64")
    return ("eligible", None)

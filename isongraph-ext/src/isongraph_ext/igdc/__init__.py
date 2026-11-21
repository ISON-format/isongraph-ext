# isongraph-ext/src/isongraph_ext/igdc/__init__.py   (interim)
"""IGDC/1 - Datamatics Consumption (26): typed-address mapping and the canonical hint contract."""
from .address import TwinGuard, TypedEdge, TypedNode, edge_address, edge_semantic_key, node_address, parse_id, semantic_key, tag_id  # noqa: F401
from .errors import IGDCError  # noqa: F401
from .hints import HintSet  # noqa: F401
from .verify import verify_hints  # noqa: F401

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]              # repo root
PKG = ROOT / "isongraph-ext" / "src" / "isongraph_ext"
BASELINES_ROOT = PKG / "baselines"
CORE_COMMIT = "ce9d3b78afd79cbdffdd67546bcb5278dc38be70"
BASELINE_DIR = BASELINES_ROOT / CORE_COMMIT
CORE_REPO = Path(os.environ.get("ISONGRAPH_CORE_REPO", "../isongraph"))
BLUEPRINT = Path("../isongraphext/isongraphext/docs/isongraph-ext-blueprint")

RECEIPT_SHA = {
    "python": "cece1259ac61172a1d519b5ad31cef8b29ff3e466f629f4cb72b4f34fdda9ac0",
    "ts": "393ba7e64e6c2be3606f2e8b03124dd2ff0cef33d069f38c6cb0b075dec268c4",
    "js": "acbe2104736148bf19c0d93649781b9c142066bec4fe1ab0b6fdc116abc39ed6",
    "rust": "6dd9c2dcf5407f598233f6c3f21bf831a02f141a509ff45b112729ae35690040",
    "cs": "f37d41566cf69c3e6b933483946bc8559c8ceb160c2d6d4ea36caab8f94ccfc7",
    "cpp": "b330dc23e4d882c71942d035d1848f03841f932345c823f93b560c86f40e83a8",
}
CORE_RUNTIME_SHA = {
    "ison_graph/__init__.py": "2a13a36d63d85e766df961aae2d52550c2e9c52f60a5ee46560ddce4a301ece4",
    "ison_graph/multigraph.py": "6d4e874a75f43d8914422bf2006f995a6334bfe4fe9eb5552c0f2f31fb4ff3e6",
    "ison_graph/query.py": "d0c34fa8649de066049a1670ccc00f8af28029c2ed7374256b9fb9a978423cd4",
    "ison_graph/schema.py": "06f82dc13eb02794b11d0386c8f8090b0f9a5d2f48be839e828703e2e5e2d1b4",
    "ison_graph/structural.py": "ffa53c3edd5dc76e6e7db20b74473f59bb6b329b09479445699eeba59e2232c7",
    "ison_graph/viz.py": "e62949eb91c9a3fe4be3972de94baddf7f41f034f5c61db51ceb8bcb4ca9b6d6",
}


@pytest.fixture(scope="session")
def baseline():
    from isongraph_ext.igx.baselines import DEFAULT_BASELINE

    return DEFAULT_BASELINE


def make_binding(**overrides):
    from isongraph_ext.igx.binding import ExtensionBinding
    from isongraph_ext.igx.digest import sha256_file

    base = dict(
        identity_claim="producer_bound",
        artifact_sha256=sha256_file(CORE_REPO / "vectors" / "ids" / "positive-int.ison"),
        serialization_profile="ison-v1", source_canonical="true",
        source_semantic_eligibility="eligible", source_semantic_reason=None,
        core_writer_implementation="isongraph-python", core_writer_version="1.4.1",
        semantic_digest=None, semantic_digest_algorithm=None,
        core_format="isongraph", core_version="1.4.1", core_commit=CORE_COMMIT,
        core_semantic_spec="ISONGraph-Semantic/2-draft", core_vector_corpus_version=1,
        core_vector_corpus_commit="f88af8bd29680e7b6e7716585be936d5738eb55f",
        core_vector_corpus_digest="1d1a6648abeeadece24b43a163949d02241911706866236cc32bd6b61745bcb0",
        producer_port="python", producer_port_version="1.4.1", producer_core_posture="FULL",
        core_conformance_receipt=RECEIPT_SHA["python"], capabilities=(), consumer=None,
    )
    base.update(overrides)
    return ExtensionBinding(**base)


GRAPHS = ROOT / "vectors" / "igx1" / "graphs"


def graph_bytes(rel: str) -> bytes:
    return (GRAPHS / rel).read_bytes()

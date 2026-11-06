"""Immutable Core baselines shipped as package data (17 §6) and the pinned Core runtime's identity (17 §4 V0)."""

from __future__ import annotations

import importlib.metadata
import importlib.resources
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ison_parser import loads

from .digest import normalize_newlines, sha256_hex
from .receipt_rules import ReceiptContentError, validate_receipt_row

PORTS = ("python", "ts", "js", "rust", "cs", "cpp")
CORE_MODULES = ("__init__.py", "multigraph.py", "query.py", "schema.py", "structural.py", "viz.py")
class BaselineDataError(RuntimeError):
    """The package's baseline data does not hash to its own MANIFEST or is internally inconsistent - an install problem, not a binding fault."""


@dataclass(frozen=True)
class Receipt:
    sha256: str
    port: str
    port_version: str
    posture: str
    core_commit: str
    core_format: str
    core_version: str
    corpus_commit: str
    corpus_digest: str
    corpus_version: int
    semantic_spec: str


@dataclass(frozen=True)
class Baseline:
    core_format: str
    core_version: str
    core_commit: str
    core_semantic_spec: str
    corpus_version: int
    corpus_commit: str
    corpus_digest: str
    receipts: Mapping[str, Receipt]
    domains: Mapping[str, frozenset[str]]
    core_runtime: Mapping[str, str]
    core_runtime_dist: tuple[str, str]
    canonical_writer_dist: tuple[str, str]     # ison-py: the writer both canonicality verdicts run through (17 §4 V0)
    retired: bool
    adopted: str


def _blocks(path: Path) -> dict[tuple[str, str], list[dict]]:
    doc = loads(path.read_bytes().decode("utf-8"))
    return {(b.kind, b.name): b.rows for b in doc.blocks}


def _validate_receipt(baseline_name: str, port: str, r: dict) -> None:
    """A hash-valid receipt can still be internally inconsistent (17 §6); rules live in receipt_rules."""
    try:
        validate_receipt_row(f"{baseline_name}/receipts/{port}.ison", port, r)
    except ReceiptContentError as e:
        raise BaselineDataError(str(e)) from None


def load_baseline(directory: Path, *, retired: bool, adopted: str) -> Baseline:
    directory = Path(directory)
    blocks = _blocks(directory / "MANIFEST.ison")
    meta = blocks[("meta", "baseline")][0]
    for row in blocks[("table", "files")]:
        actual = sha256_hex((directory / row["path"]).read_bytes())
        if actual != row["sha256"]:
            raise BaselineDataError(f"{directory.name}/{row['path']}: sha256 {actual} != manifest {row['sha256']}")
    receipts: dict[str, Receipt] = {}
    for port in PORTS:
        data = (directory / "receipts" / f"{port}.ison").read_bytes()
        r = loads(data.decode("utf-8")).blocks[0].rows[0]
        _validate_receipt(directory.name, port, r)
        receipts[port] = Receipt(
            sha256=sha256_hex(data), port=r["port"], port_version=str(r["port_version"]), posture=r["posture"],
            core_commit=r["core_commit"], core_format=r["core_format"], core_version=str(r["core_version"]),
            corpus_commit=r["corpus_commit"], corpus_digest=r["corpus_digest"], corpus_version=int(r["corpus_version"]),
            semantic_spec=r["semantic_spec"],
        )
    domains: dict[str, set[str]] = {p: set() for p in PORTS}
    for row in _blocks(directory / "domains.ison").get(("table", "domains"), []):
        domains[row["port"]].add(row["tag"])
    return Baseline(
        core_format=meta["core_format"], core_version=str(meta["core_version"]), core_commit=meta["core_commit"],
        core_semantic_spec=meta["core_semantic_spec"], corpus_version=int(meta["core_vector_corpus_version"]),
        corpus_commit=meta["core_vector_corpus_commit"], corpus_digest=meta["core_vector_corpus_digest"],
        receipts=receipts, domains={p: frozenset(t) for p, t in domains.items()},
        core_runtime={r["module"]: r["sha256"] for r in blocks[("table", "core_runtime")]},
        core_runtime_dist=(meta["core_runtime_dist"], str(meta["core_runtime_dist_version"])),
        canonical_writer_dist=(meta["canonical_writer_dist"], str(meta["canonical_writer_dist_version"])),
        retired=retired, adopted=adopted,
    )


def load_registry(root: Path) -> dict[str, Baseline]:
    root = Path(root)
    rows = _blocks(root / "REGISTRY.ison")[("table", "baselines")]
    return {r["core_commit"]: load_baseline(root / r["core_commit"], retired=bool(r["retired"]), adopted=str(r["adopted"])) for r in rows}


def _dist_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None   # e.g. a source checkout on sys.path: classify as a mismatch, never raise (17 §4 V0)


def installed_core_runtime(modules: Mapping[str, str] | Iterable[str]) -> tuple[tuple[str, str | None], dict[str, str | None], tuple[str, str | None]]:
    """What is installed, measured against the module list THE BASELINE names.

    Returns ((dist, version), {module: sha256 | None if the file is absent}, (writer dist, version)).
    Never raises for a missing module or missing distribution metadata: the caller decides what a mismatch means.
    """
    import ison_graph

    pkg = Path(ison_graph.__file__).parent
    hashes: dict[str, str | None] = {}
    for module in modules:
        path = pkg / module.removeprefix("ison_graph/")
        hashes[module] = sha256_hex(normalize_newlines(path.read_bytes())) if path.is_file() else None
    return ("ison-graph", _dist_version("ison-graph")), hashes, ("ison-py", _dist_version("ison-py"))


_ROOT = Path(str(importlib.resources.files("isongraph_ext") / "baselines"))
BASELINES: Mapping[str, Baseline] = load_registry(_ROOT)
DEFAULT_BASELINE: Baseline = max((b for b in BASELINES.values() if not b.retired), key=lambda b: b.adopted)

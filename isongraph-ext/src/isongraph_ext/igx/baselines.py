"""Immutable Core baselines shipped as package data (17 §6) and the pinned Core runtime's identity (17 §4 V0)."""

from __future__ import annotations

import importlib.metadata
import importlib.resources
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ison_parser import loads

from .digest import normalize_newlines, sha256_hex

PORTS = ("python", "ts", "js", "rust", "cs", "cpp")
CORE_MODULES = ("__init__.py", "multigraph.py", "query.py", "schema.py", "structural.py", "viz.py")
POSTURES = ("FULL", "LOSSY_KNOWN", "KNOWN_DEFECT", "PARTIAL", "INCONCLUSIVE", "NONCONFORMANT")
COUNTERS = ("pass", "canonicalized", "lossy", "defect", "rejected_as_expected", "todo")


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
    retired: bool
    adopted: str


def _blocks(path: Path) -> dict[tuple[str, str], list[dict]]:
    doc = loads(path.read_bytes().decode("utf-8"))
    return {(b.kind, b.name): b.rows for b in doc.blocks}


def _validate_receipt(baseline_name: str, port: str, r: dict) -> None:
    """A hash-valid receipt can still be internally inconsistent (17 §6). Mirror Core's corpus_receipt.py posture rules."""
    where = f"{baseline_name}/receipts/{port}.ison"
    if r.get("port") != port:
        raise BaselineDataError(f"{where}: port {r.get('port')!r} != file name")
    if r.get("posture") not in POSTURES:
        raise BaselineDataError(f"{where}: posture {r.get('posture')!r}")
    counts = {k: r.get(k) for k in COUNTERS + ("total",)}
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in counts.values()):
        raise BaselineDataError(f"{where}: counters must be non-negative integers: {counts}")
    if sum(counts[k] for k in COUNTERS) != counts["total"]:
        raise BaselineDataError(f"{where}: counters do not sum to total: {counts}")
    p, todo, lossy, defect, total = r["posture"], counts["todo"], counts["lossy"], counts["defect"], counts["total"]
    ok = {
        "FULL": todo == 0 and lossy == 0 and defect == 0,
        "LOSSY_KNOWN": todo == 0 and defect == 0 and lossy > 0,
        "KNOWN_DEFECT": todo == 0 and defect > 0,
        "PARTIAL": todo == total,
        "INCONCLUSIVE": todo > 0,
        "NONCONFORMANT": True,
    }[p]
    if not ok:
        raise BaselineDataError(f"{where}: posture {p} inconsistent with counters {counts}")


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
        retired=retired, adopted=adopted,
    )


def load_registry(root: Path) -> dict[str, Baseline]:
    root = Path(root)
    rows = _blocks(root / "REGISTRY.ison")[("table", "baselines")]
    return {r["core_commit"]: load_baseline(root / r["core_commit"], retired=bool(r["retired"]), adopted=str(r["adopted"])) for r in rows}


def installed_core_runtime() -> tuple[tuple[str, str], dict[str, str]]:
    import ison_graph

    pkg = Path(ison_graph.__file__).parent
    hashes = {f"ison_graph/{m}": sha256_hex(normalize_newlines((pkg / m).read_bytes())) for m in CORE_MODULES}
    return ("ison-graph", importlib.metadata.version("ison-graph")), hashes


_ROOT = Path(str(importlib.resources.files("isongraph_ext") / "baselines"))
BASELINES: Mapping[str, Baseline] = load_registry(_ROOT)
DEFAULT_BASELINE: Baseline = max((b for b in BASELINES.values() if not b.retired), key=lambda b: b.adopted)

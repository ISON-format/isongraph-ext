"""Synthetic baselines for tests only (17 §5). Deterministic; re-run to regenerate; outputs are committed."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical, loads

HERE = Path(__file__).resolve().parent
REAL = HERE.parents[1] / "src" / "isongraph_ext" / "baselines" / "ce9d3b78afd79cbdffdd67546bcb5278dc38be70"
PORTS = ("python", "ts", "js", "rust", "cs", "cpp")
REAL_COMMIT = "ce9d3b78afd79cbdffdd67546bcb5278dc38be70"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write(path: Path, doc: Document, newline: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((dumps_canonical(doc) + ("\n" if newline else "")).encode("utf-8"))


def rows_of(path: Path, kind: str, name: str) -> list[dict]:
    return [r for b in loads(path.read_bytes().decode("utf-8")).blocks if (b.kind, b.name) == (kind, name) for r in b.rows]


def build(commit: str, adopted: str, retired: bool, tweak_python, extra_domains: list[dict], foreign_python: bool,
          runtime_differs: bool = False) -> dict:
    out = HERE / "baselines" / commit
    manifest_meta = dict(rows_of(REAL / "MANIFEST.ison", "meta", "baseline")[0])
    manifest_meta["core_commit"] = commit
    runtime = rows_of(REAL / "MANIFEST.ison", "table", "core_runtime")
    if runtime_differs:
        # A historical Core the installed runtime is NOT: hashes that no real module has (17 §4 V0 "limited").
        manifest_meta["core_runtime_dist_version"] = "1.3.9"
        runtime = [{"module": r["module"], "sha256": sha(f"historical:{r['module']}".encode())} for r in runtime]
    files = []
    for port in PORTS:
        row = dict(rows_of(REAL / "receipts" / f"{port}.ison", "meta", "core_conformance_receipt")[0])
        row["core_commit"] = REAL_COMMIT if (foreign_python and port == "python") else commit
        if port == "python":
            tweak_python(row)
        write(out / "receipts" / f"{port}.ison", Document(blocks=[Block("meta", "core_conformance_receipt", list(row), [row])]), newline=True)
        files.append({"path": f"receipts/{port}.ison", "sha256": sha((out / "receipts" / f"{port}.ison").read_bytes())})
    domains = rows_of(REAL / "domains.ison", "table", "domains") + extra_domains
    write(out / "domains.ison", Document(blocks=[Block("table", "domains", ["port", "tag"], domains)]))
    files.append({"path": "domains.ison", "sha256": sha((out / "domains.ison").read_bytes())})
    write(out / "MANIFEST.ison", Document(blocks=[
        Block("meta", "baseline", list(manifest_meta), [manifest_meta]),
        Block("table", "files", ["path", "sha256"], files),
        Block("table", "core_runtime", ["module", "sha256"], runtime),
    ]))
    return {"adopted": adopted, "core_commit": commit, "retired": retired}


def main() -> int:
    def lossy(row: dict) -> None:
        row["posture"], row["pass"], row["lossy"] = "LOSSY_KNOWN", 17, 2

    registry = [
        build("1" * 40, "2026-01-01", True, lambda r: None, [], False, runtime_differs=True),
        build("2" * 40, "2026-01-02", False, lossy, [{"port": "python", "tag": "binary64-inexact-int"}], False),
        build("3" * 40, "2026-01-03", False, lambda r: None, [], True),
    ]
    write(HERE / "baselines" / "REGISTRY.ison", Document(blocks=[Block("table", "baselines", ["adopted", "core_commit", "retired"], registry)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

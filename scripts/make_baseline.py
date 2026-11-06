#!/usr/bin/env python3
"""Build an immutable IGX/1 baseline directory from a Core checkout (17 §6).

    python scripts/make_baseline.py --core <isongraph checkout> --commit <40hex> \
        --receipts <dir with python.ison ... cpp.ison> --adopted YYYY-MM-DD --out <baselines root> [--verify]

Module hashes come from `git show <commit>:path` (repository bytes, LF), never the working tree.
Domain tags are derived from the corpus manifest at <commit>; an unmapped lossy/defect cell is an error.
Baselines are immutable: writing into an existing <out>/<commit> exits 3; --verify regenerates into a
scratch directory and compares byte-for-byte without touching <out>.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical, loads

PORTS = ("python", "ts", "js", "rust", "cs", "cpp")
MODULES = ("__init__.py", "multigraph.py", "query.py", "schema.py", "structural.py", "viz.py")
TAG_OF = {
    "ids/int64-extremes": "binary64-inexact-int",
    "values/int64-extreme-values": "binary64-inexact-int",
    "values/int-beyond-int64-inexact": "binary64-inexact-int",
    "values/int-vs-integral-float": "integral-float-collapse",
}
DEFECT_TAG_OF = {"structure/multigraph-document": "multigraph-document-accepted"}


def git_show(core: Path, commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(core), "show", f"{commit}:{path}"])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, doc: Document) -> None:
    path.write_bytes(dumps_canonical(doc).encode("utf-8"))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--core", required=True, type=Path)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--receipts", required=True, type=Path)
    ap.add_argument("--adopted", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--verify", action="store_true", help="non-mutating: regenerate into a scratch dir and compare byte-for-byte with --out")
    a = ap.parse_args(argv[1:])
    if not re.fullmatch(r"[0-9a-f]{40}", a.commit):
        print("commit must be a full 40-hex id", file=sys.stderr)
        return 2
    if a.verify:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            rc = main([argv[0], "--core", str(a.core), "--commit", a.commit, "--receipts", str(a.receipts), "--adopted", a.adopted, "--out", tmp])
            if rc:
                return rc
            want, have = Path(tmp) / a.commit, a.out / a.commit
            names = sorted(p.relative_to(want).as_posix() for p in want.rglob("*") if p.is_file())
            bad = [n for n in names if not (have / n).is_file() or (have / n).read_bytes() != (want / n).read_bytes()]
            reg_ok = any(r["core_commit"] == a.commit for b in loads((a.out / "REGISTRY.ison").read_bytes().decode("utf-8")).blocks for r in b.rows)
            print("baseline reproduces" if not bad and reg_ok else f"MISMATCH: {bad or 'registry row missing'}")
            return 0 if not bad and reg_ok else 1

    out = a.out / a.commit
    if out.exists():
        print(f"refusing to write into existing baseline {out} - baselines are immutable (use --verify)", file=sys.stderr)
        return 3
    (out / "receipts").mkdir(parents=True, exist_ok=True)
    receipts = {}
    for port in PORTS:
        data = (a.receipts / f"{port}.ison").read_bytes()
        (out / "receipts" / f"{port}.ison").write_bytes(data)
        receipts[port] = loads(data.decode("utf-8")).blocks[0].rows[0]
    py = receipts["python"]
    if a.commit != py["core_commit"]:
        print("receipts were not generated at --commit", file=sys.stderr)
        return 2

    manifest = loads(git_show(a.core, a.commit, "vectors/manifest.ison").decode("utf-8"))
    rows = [r for b in manifest.blocks if (b.kind, b.name) == ("table", "vectors") for r in b.rows]
    domain_rows = []
    for port in PORTS:
        tags = set()
        for r in rows:
            cell = r[port]
            if cell == "pass:lossy":
                if r["id"] not in TAG_OF:
                    print(f"unmapped lossy vector {r['id']} for {port}", file=sys.stderr)
                    return 2
                tags.add(TAG_OF[r["id"]])
            elif cell == "defect":
                if r["id"] not in DEFECT_TAG_OF:
                    print(f"unmapped defect vector {r['id']} for {port}", file=sys.stderr)
                    return 2
                tags.add(DEFECT_TAG_OF[r["id"]])
        domain_rows += [{"port": port, "tag": t} for t in sorted(tags)]
    write(out / "domains.ison", Document(blocks=[Block(kind="table", name="domains", fields=["port", "tag"], rows=domain_rows)]))

    pyproject = git_show(a.core, a.commit, "ison-graph/pyproject.toml").decode("utf-8")
    dist_version = re.search(r'^version = "([^"]+)"', pyproject, flags=re.M).group(1)
    runtime_rows = [{"module": f"ison_graph/{m}", "sha256": sha(git_show(a.core, a.commit, f"ison-graph/src/ison_graph/{m}"))} for m in MODULES]
    file_rows = [{"path": f"receipts/{p}.ison", "sha256": sha((out / "receipts" / f"{p}.ison").read_bytes())} for p in PORTS]
    file_rows.append({"path": "domains.ison", "sha256": sha((out / "domains.ison").read_bytes())})
    meta = {
        "core_format": py["core_format"], "core_version": py["core_version"], "core_commit": a.commit,
        "core_semantic_spec": py["semantic_spec"], "core_vector_corpus_version": py["corpus_version"],
        "core_vector_corpus_commit": py["corpus_commit"], "core_vector_corpus_digest": py["corpus_digest"],
        "core_runtime_dist": "ison-graph", "core_runtime_dist_version": dist_version,
    }
    write(out / "MANIFEST.ison", Document(blocks=[
        Block(kind="meta", name="baseline", fields=list(meta), rows=[meta]),
        Block(kind="table", name="files", fields=["path", "sha256"], rows=file_rows),
        Block(kind="table", name="core_runtime", fields=["module", "sha256"], rows=runtime_rows),
    ]))

    reg_path = a.out / "REGISTRY.ison"
    existing = []
    if reg_path.exists():
        existing = [r for b in loads(reg_path.read_bytes().decode("utf-8")).blocks for r in b.rows]
        if any(r["core_commit"] == a.commit for r in existing):
            print(f"registry already lists {a.commit}; rows are append-only", file=sys.stderr)
            return 3
    existing.append({"adopted": a.adopted, "core_commit": a.commit, "retired": False})
    write(reg_path, Document(blocks=[Block(kind="table", name="baselines", fields=["adopted", "core_commit", "retired"], rows=existing)]))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

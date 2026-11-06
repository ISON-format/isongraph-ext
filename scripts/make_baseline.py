#!/usr/bin/env python3
"""Build an immutable IGX/1 baseline directory from a Core checkout (17 §6).

    python scripts/make_baseline.py --core <isongraph checkout> --commit <40hex> \
        --receipts <dir with python.ison ... cpp.ison> --adopted YYYY-MM-DD --out <baselines root> [--verify]

Module hashes come from `git show <commit>:path` (repository bytes, LF), never the working tree.
Domain tags are derived from the corpus manifest at <commit>; an unmapped lossy/defect cell is an error.

Fail closed: every input is validated BEFORE anything is written (receipt framing `dumps_canonical(row)+"\\n"`,
receipt content rules, cross-fields across all six receipts, registry state); the directory is built in a
scratch location and moved into place last, so a failed run leaves nothing behind. Writing into an existing
<out>/<commit> exits 3; --verify regenerates into a scratch directory and compares byte-for-byte without
touching <out>.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical, loads

# Load the receipt rules module by file so the package __init__ (which eagerly loads the baseline data this
# script is about to create) is not imported - the generator must work before any baseline exists.
import importlib.util  # noqa: E402

_RULES_PATH = Path(__file__).resolve().parents[1] / "isongraph-ext" / "src" / "isongraph_ext" / "igx" / "receipt_rules.py"
_spec = importlib.util.spec_from_file_location("receipt_rules", _RULES_PATH)
_rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rules)  # type: ignore[union-attr]
ReceiptContentError, validate_receipt_row = _rules.ReceiptContentError, _rules.validate_receipt_row

PORTS = ("python", "ts", "js", "rust", "cs", "cpp")
MODULES = ("__init__.py", "multigraph.py", "query.py", "schema.py", "structural.py", "viz.py")
TAG_OF = {
    "ids/int64-extremes": "binary64-inexact-int",
    "values/int64-extreme-values": "binary64-inexact-int",
    "values/int-beyond-int64-inexact": "binary64-inexact-int",
    "values/int-vs-integral-float": "integral-float-collapse",
}
DEFECT_TAG_OF = {"structure/multigraph-document": "multigraph-document-accepted"}
CROSS = ("core_commit", "core_format", "core_version", "corpus_commit", "corpus_digest", "corpus_version", "semantic_spec")


class InputError(Exception):
    pass


def git_show(core: Path, commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(core), "show", f"{commit}:{path}"])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, doc: Document) -> None:
    path.write_bytes(dumps_canonical(doc).encode("utf-8"))


def load_receipts(receipts_dir: Path, commit: str) -> dict[str, tuple[bytes, dict]]:
    """Validate the six receipts as bytes + content before anything is written."""
    out: dict[str, tuple[bytes, dict]] = {}
    for port in PORTS:
        path = receipts_dir / f"{port}.ison"
        if not path.is_file():
            raise InputError(f"missing receipt {path}")
        data = path.read_bytes()
        if b"\r" in data:
            raise InputError(f"{path.name}: receipt framing is CRLF; a receipt is dumps_canonical(row)+LF (Windows text-mode capture?)")
        try:
            doc = loads(data.decode("utf-8"))
        except Exception as e:
            raise InputError(f"{path.name}: not ISON: {e}") from None
        if len(doc.blocks) != 1 or (doc.blocks[0].kind, doc.blocks[0].name) != ("meta", "core_conformance_receipt") or len(doc.blocks[0].rows) != 1:
            raise InputError(f"{path.name}: expected exactly one meta.core_conformance_receipt row")
        row = doc.blocks[0].rows[0]
        if (dumps_canonical(Document(blocks=[Block("meta", "core_conformance_receipt", list(row), [row])])) + "\n").encode("utf-8") != data:
            raise InputError(f"{path.name}: receipt framing is not dumps_canonical(row)+LF (CRLF or non-canonical bytes?)")
        try:
            validate_receipt_row(path.name, port, row)
        except ReceiptContentError as e:
            raise InputError(str(e)) from None
        out[port] = (data, row)
    py = out["python"][1]
    if py["core_commit"] != commit:
        raise InputError(f"receipts were generated at {py['core_commit']}, not --commit {commit}")
    for port, (_, row) in out.items():
        for k in CROSS:
            if row[k] != py[k]:
                raise InputError(f"{port}.ison: {k}={row[k]!r} disagrees with python.ison {py[k]!r}")
    return out


def domain_rows(core: Path, commit: str) -> list[dict]:
    manifest = loads(git_show(core, commit, "vectors/manifest.ison").decode("utf-8"))
    rows = [r for b in manifest.blocks if (b.kind, b.name) == ("table", "vectors") for r in b.rows]
    result = []
    for port in PORTS:
        tags = set()
        for r in rows:
            cell = r[port]
            if cell == "pass:lossy":
                if r["id"] not in TAG_OF:
                    raise InputError(f"unmapped lossy vector {r['id']} for {port}")
                tags.add(TAG_OF[r["id"]])
            elif cell == "defect":
                if r["id"] not in DEFECT_TAG_OF:
                    raise InputError(f"unmapped defect vector {r['id']} for {port}")
                tags.add(DEFECT_TAG_OF[r["id"]])
        result += [{"port": port, "tag": t} for t in sorted(tags)]
    return result


def build(core: Path, commit: str, receipts: dict[str, tuple[bytes, dict]], out: Path) -> None:
    """Write a complete baseline directory at `out` (a scratch location)."""
    (out / "receipts").mkdir(parents=True)
    py = receipts["python"][1]
    file_rows = []
    for port in PORTS:
        (out / "receipts" / f"{port}.ison").write_bytes(receipts[port][0])
        file_rows.append({"path": f"receipts/{port}.ison", "sha256": sha(receipts[port][0])})
    write(out / "domains.ison", Document(blocks=[Block("table", "domains", ["port", "tag"], domain_rows(core, commit))]))
    file_rows.append({"path": "domains.ison", "sha256": sha((out / "domains.ison").read_bytes())})
    pyproject = git_show(core, commit, "ison-graph/pyproject.toml").decode("utf-8")
    dist_version = re.search(r'^version = "([^"]+)"', pyproject, flags=re.M).group(1)
    runtime_rows = [{"module": f"ison_graph/{m}", "sha256": sha(git_show(core, commit, f"ison-graph/src/ison_graph/{m}"))} for m in MODULES]
    meta = {
        "core_format": py["core_format"], "core_version": py["core_version"], "core_commit": commit,
        "core_semantic_spec": py["semantic_spec"], "core_vector_corpus_version": py["corpus_version"],
        "core_vector_corpus_commit": py["corpus_commit"], "core_vector_corpus_digest": py["corpus_digest"],
        "core_runtime_dist": "ison-graph", "core_runtime_dist_version": dist_version,
        # The canonical writer every canonicality verdict runs through (17 §4 V0): the ison-py this baseline was built with.
        "canonical_writer_dist": "ison-py", "canonical_writer_dist_version": importlib.metadata.version("ison-py"),
    }
    write(out / "MANIFEST.ison", Document(blocks=[
        Block("meta", "baseline", list(meta), [meta]),
        Block("table", "files", ["path", "sha256"], file_rows),
        Block("table", "core_runtime", ["module", "sha256"], runtime_rows),
    ]))


def registry_rows(reg_path: Path) -> list[dict]:
    if not reg_path.exists():
        return []
    return [r for b in loads(reg_path.read_bytes().decode("utf-8")).blocks for r in b.rows]


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
    try:
        receipts = load_receipts(a.receipts, a.commit)
    except InputError as e:
        print(f"invalid input: {e}", file=sys.stderr)
        return 2

    if a.verify:
        with tempfile.TemporaryDirectory() as tmp:
            want = Path(tmp) / a.commit
            try:
                build(a.core, a.commit, receipts, want)
            except InputError as e:
                print(f"invalid input: {e}", file=sys.stderr)
                return 2
            have = a.out / a.commit
            want_names = sorted(p.relative_to(want).as_posix() for p in want.rglob("*") if p.is_file())
            have_names = sorted(p.relative_to(have).as_posix() for p in have.rglob("*") if p.is_file()) if have.is_dir() else []
            bad = [n for n in want_names if n not in have_names or (have / n).read_bytes() != (want / n).read_bytes()]
            extra = [n for n in have_names if n not in want_names]
            row = next((r for r in registry_rows(a.out / "REGISTRY.ison") if r["core_commit"] == a.commit), None)
            reg_ok = row is not None and str(row["adopted"]) == a.adopted
            ok = not bad and not extra and reg_ok
            print("baseline reproduces" if ok else f"MISMATCH: changed={bad} extra={extra} registry_ok={reg_ok}")
            return 0 if ok else 1

    out = a.out / a.commit
    if out.exists():
        print(f"refusing to write into existing baseline {out} - baselines are immutable (use --verify)", file=sys.stderr)
        return 3
    existing = registry_rows(a.out / "REGISTRY.ison")
    if any(r["core_commit"] == a.commit for r in existing):
        print(f"registry already lists {a.commit}; rows are append-only", file=sys.stderr)
        return 3
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / a.commit
        try:
            build(a.core, a.commit, receipts, scratch)
        except InputError as e:
            print(f"invalid input: {e}", file=sys.stderr)
            return 2
        a.out.mkdir(parents=True, exist_ok=True)
        shutil.move(str(scratch), str(out))   # complete directory appears in one step; nothing partial is ever left
    existing.append({"adopted": a.adopted, "core_commit": a.commit, "retired": False})
    write(a.out / "REGISTRY.ison", Document(blocks=[Block("table", "baselines", ["adopted", "core_commit", "retired"], existing)]))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

import hashlib
import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import BASELINE_DIR, BASELINES_ROOT, BLUEPRINT, CORE_COMMIT, CORE_REPO, CORE_RUNTIME_SHA, RECEIPT_SHA, ROOT
from ison_parser import loads

from isongraph_ext.igx.baselines import BASELINES, DEFAULT_BASELINE, BaselineDataError, installed_core_runtime, load_baseline
from isongraph_ext.igx.digest import sha256_file

PORTS = ("python", "ts", "js", "rust", "cs", "cpp")


def test_receipt_bytes_are_the_pinned_ones():
    for port, sha in RECEIPT_SHA.items():
        assert sha256_file(BASELINE_DIR / "receipts" / f"{port}.ison") == sha, port


def test_manifest_file_table_matches_files():
    doc = loads((BASELINE_DIR / "MANIFEST.ison").read_bytes().decode("utf-8"))
    files = {r["path"]: r["sha256"] for b in doc.blocks if (b.kind, b.name) == ("table", "files") for r in b.rows}
    assert set(files) == {f"receipts/{p}.ison" for p in PORTS} | {"domains.ison"}
    for rel, sha in files.items():
        assert sha256_file(BASELINE_DIR / rel) == sha, rel


def test_default_baseline_values(baseline):
    assert baseline.core_commit == CORE_COMMIT
    assert (baseline.core_format, baseline.core_version, baseline.core_semantic_spec) == ("isongraph", "1.4.1", "ISONGraph-Semantic/2-draft")
    assert (baseline.corpus_version, baseline.corpus_commit) == (1, "f88af8bd29680e7b6e7716585be936d5738eb55f")
    assert baseline.corpus_digest == "1d1a6648abeeadece24b43a163949d02241911706866236cc32bd6b61745bcb0"
    assert baseline.retired is False and baseline.adopted == "2026-11-05"
    assert baseline.core_runtime_dist == ("ison-graph", "1.4.1")
    assert dict(baseline.core_runtime) == CORE_RUNTIME_SHA
    assert BASELINES[CORE_COMMIT] is DEFAULT_BASELINE and len(BASELINES) == 1


def test_receipts_parsed_and_cross_fields(baseline):
    assert set(baseline.receipts) == set(PORTS)
    r = baseline.receipts["python"]
    assert (r.sha256, r.port, r.port_version, r.posture) == (RECEIPT_SHA["python"], "python", "1.4.1", "FULL")
    assert (r.core_commit, r.corpus_commit, r.corpus_digest, r.corpus_version, r.semantic_spec) == (
        baseline.core_commit, baseline.corpus_commit, baseline.corpus_digest, 1, baseline.core_semantic_spec)
    assert {p: baseline.receipts[p].posture for p in PORTS} == {
        "python": "FULL", "ts": "KNOWN_DEFECT", "js": "KNOWN_DEFECT", "rust": "PARTIAL", "cs": "PARTIAL", "cpp": "PARTIAL"}


def test_domains(baseline):
    tags = frozenset({"binary64-inexact-int", "integral-float-collapse", "multigraph-document-accepted"})
    assert baseline.domains["ts"] == tags and baseline.domains["js"] == tags
    assert baseline.domains["python"] == frozenset() and baseline.domains["rust"] == frozenset()


def test_installed_core_runtime_is_the_baseline_implementation(baseline):
    dist, hashes, writer = installed_core_runtime(baseline.core_runtime)
    assert dist == baseline.core_runtime_dist
    assert hashes == dict(baseline.core_runtime)
    assert writer == baseline.canonical_writer_dist == ("ison-py", "1.2.0")
    assert importlib.metadata.version("ison-graph") == "1.4.1"


def test_installed_core_runtime_reports_missing_modules_as_none():
    _, hashes, _ = installed_core_runtime({"ison_graph/does_not_exist.py": "0" * 64})
    assert hashes == {"ison_graph/does_not_exist.py": None}


def test_test_paths_are_portable():
    # CI has neither d:/ nor the author's checkout: the blueprint copy and the graph inputs live in this repo.
    assert BLUEPRINT.is_relative_to(ROOT) and (BLUEPRINT / "receipts" / "python.ison").is_file()
    assert b"\r" not in (BLUEPRINT / "receipts" / "python.ison").read_bytes()


def test_load_baseline_detects_corruption(tmp_path: Path):
    import shutil
    dst = tmp_path / CORE_COMMIT
    shutil.copytree(BASELINE_DIR, dst)
    (dst / "receipts" / "python.ison").write_bytes(b"meta.x\na\n1\n")
    with pytest.raises(BaselineDataError):
        load_baseline(dst, retired=False, adopted="2026-11-05")


def test_load_baseline_rejects_inconsistent_receipt(tmp_path: Path):
    import shutil
    from ison_parser import Block, Document, dumps_canonical
    dst = tmp_path / CORE_COMMIT
    shutil.copytree(BASELINE_DIR, dst)
    row = loads((dst / "receipts" / "python.ison").read_bytes().decode("utf-8")).blocks[0].rows[0]
    row["lossy"] = 2                                  # FULL posture with lossy > 0, and counters no longer sum to total
    data = (dumps_canonical(Document(blocks=[Block("meta", "core_conformance_receipt", list(row), [row])])) + "\n").encode("utf-8")
    (dst / "receipts" / "python.ison").write_bytes(data)
    # keep the MANIFEST hash honest so the failure is the content rule, not the hash rule
    man = (dst / "MANIFEST.ison").read_bytes().decode("utf-8").replace(RECEIPT_SHA["python"], hashlib.sha256(data).hexdigest())
    (dst / "MANIFEST.ison").write_bytes(man.encode("utf-8"))
    with pytest.raises(BaselineDataError, match="inconsistent|sum"):
        load_baseline(dst, retired=False, adopted="2026-11-05")


SCRIPT = [sys.executable, str(ROOT / "scripts" / "make_baseline.py"), "--commit", CORE_COMMIT, "--adopted", "2026-11-05"]
needs_core = pytest.mark.skipif(not (CORE_REPO / ".git").exists(), reason="set ISONGRAPH_CORE_REPO to a Core checkout containing ce9d3b7")


@needs_core
def test_make_baseline_reproduces_committed_directory(tmp_path: Path):
    out = tmp_path / "baselines"
    subprocess.run(SCRIPT + ["--core", str(CORE_REPO), "--receipts", str(BLUEPRINT / "receipts"), "--out", str(out)], check=True)
    for rel in ["REGISTRY.ison", f"{CORE_COMMIT}/MANIFEST.ison", f"{CORE_COMMIT}/domains.ison"] + [f"{CORE_COMMIT}/receipts/{p}.ison" for p in PORTS]:
        assert (out / rel).read_bytes() == (BASELINES_ROOT / rel).read_bytes(), rel


@needs_core
def test_make_baseline_fails_closed_on_crlf_receipts_and_writes_nothing(tmp_path: Path):
    bad = tmp_path / "receipts"
    bad.mkdir()
    for p in PORTS:
        bad.joinpath(f"{p}.ison").write_bytes((BLUEPRINT / "receipts" / f"{p}.ison").read_bytes().replace(b"\n", b"\r\n"))
    out = tmp_path / "baselines"
    p = subprocess.run(SCRIPT + ["--core", str(CORE_REPO), "--receipts", str(bad), "--out", str(out)], capture_output=True, text=True)
    assert p.returncode == 2 and "framing" in p.stderr.lower(), p.stderr
    assert not out.exists(), "a failed run must leave nothing behind"


@needs_core
def test_make_baseline_refuses_to_overwrite_and_verify_mode_passes():
    p = subprocess.run(SCRIPT + ["--core", str(CORE_REPO), "--receipts", str(BLUEPRINT / "receipts"), "--out", str(BASELINES_ROOT)], capture_output=True, text=True)
    assert p.returncode == 3 and "immutable" in p.stderr
    assert (BASELINES_ROOT / CORE_COMMIT / "MANIFEST.ison").read_bytes() == (BASELINE_DIR / "MANIFEST.ison").read_bytes()
    p = subprocess.run(SCRIPT + ["--core", str(CORE_REPO), "--receipts", str(BLUEPRINT / "receipts"), "--out", str(BASELINES_ROOT), "--verify"], capture_output=True, text=True)
    assert p.returncode == 0 and "reproduces" in p.stdout

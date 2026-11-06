import glob
import hashlib
import tarfile
import zipfile

import pytest
from conftest import BASELINE_DIR, CORE_COMMIT, ROOT

DIST = ROOT / "isongraph-ext" / "dist"
EXPECTED = sorted(["baselines/REGISTRY.ison", f"baselines/{CORE_COMMIT}/MANIFEST.ison", f"baselines/{CORE_COMMIT}/domains.ison"]
                  + [f"baselines/{CORE_COMMIT}/receipts/{p}.ison" for p in ("python", "ts", "js", "rust", "cs", "cpp")])


def _needs_built(request):
    if not request.config.getoption("--built"):
        pytest.skip("run with --built after `python -m build`")


def _src_hash(rel: str) -> str:
    return hashlib.sha256((BASELINE_DIR.parent / rel[len("baselines/"):]).read_bytes()).hexdigest()


def test_wheel_contains_every_baseline_file_byte_exact(request):
    _needs_built(request)
    wheel = glob.glob(str(DIST / "isongraph_ext-0.2.0-*.whl"))
    assert wheel, "no wheel in dist/"
    z = zipfile.ZipFile(wheel[0])
    names = {n[len("isongraph_ext/"):]: n for n in z.namelist() if n.startswith("isongraph_ext/baselines/")}
    assert sorted(names) == EXPECTED
    for rel, member in names.items():
        assert hashlib.sha256(z.read(member)).hexdigest() == _src_hash(rel), rel
    names_all = set(z.namelist())
    for mod in ("__init__", "errors", "records", "payload", "locators", "resolve", "verify", "bind", "lineage", "__main__"):
        assert f"isongraph_ext/igpv/{mod}.py" in names_all, mod
    assert "isongraph_ext/igx/registry.py" in names_all


def test_sdist_contains_every_baseline_file(request):
    _needs_built(request)
    sdist = glob.glob(str(DIST / "isongraph_ext-0.2.0.tar.gz"))
    assert sdist, "no sdist in dist/"
    with tarfile.open(sdist[0]) as t:
        members = {m.name.split("/src/isongraph_ext/", 1)[1]: m for m in t.getmembers() if "/src/isongraph_ext/baselines/" in m.name and m.isfile()}
        assert sorted(members) == EXPECTED
        for rel, m in members.items():
            assert hashlib.sha256(t.extractfile(m).read()).hexdigest() == _src_hash(rel), rel


def test_pinned_dependencies_are_exact():
    text = (ROOT / "isongraph-ext" / "pyproject.toml").read_text(encoding="utf-8")
    assert '"ison-py==1.2.0"' in text and '"ison-graph==1.4.1"' in text
    assert ">=1.4" not in text.split("dependencies")[1].split("]")[0]

"""Adoption examples (examples/): smoke tests that execute them and assert meaningful output, plus a fresh-venv wheel check."""
import glob
import os
import subprocess
import sys
import xml.dom.minidom

import pytest
from conftest import ROOT

EX = ROOT / "examples"
SRC = ROOT / "isongraph-ext" / "src"
DIST = ROOT / "isongraph-ext" / "dist"


def _run(*args, cwd=None, env_extra=None, python=sys.executable):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update({"PYTHONIOENCODING": "utf-8"})
    env.update(env_extra if env_extra is not None else {"PYTHONPATH": str(SRC)})
    return subprocess.run([python, *map(str, args)], capture_output=True, env=env, cwd=cwd, timeout=300)


def _ok(p, marker):
    out = p.stdout.decode("utf-8", "replace")
    assert p.returncode == 0, (p.stderr.decode("utf-8", "replace"), out)
    assert out.rstrip().splitlines()[-1].startswith(f"OK: {marker}"), out
    return out


def test_institutional_evidence_example():
    out = _ok(_run(EX / "institutional_evidence.py"), "institutional_evidence")
    assert "tampered minutes: P5 SOURCE_ARTIFACT_MISMATCH" in out
    assert "non-stdlib modules loaded: ['ison_graph', 'ison_parser', 'isongraph_ext']" in out


def test_core_only_example_does_not_import_ext():
    out = _ok(_run(EX / "core_only.py"), "core_only (isongraph_ext not imported)")
    assert "component:C-PUMP depends on" in out


def test_measure_example_reports_separate_columns():
    out = _ok(_run(EX / "measure.py", "50"), "measure")
    row = next(l for l in out.splitlines() if l.startswith("nodes=50"))
    for col in ("core_parse=", "igx_verify=", "igpv_total=", "igpv_extra=", "igdm_total=", "igdm_extra=", "svg_render="):
        assert col in row, row


@pytest.fixture(scope="module")
def supply(tmp_path_factory):
    d = tmp_path_factory.mktemp("supply")
    out = _ok(_run(EX / "supply_chain_assets.py", "--write", d), "supply_chain_assets")
    assert "unrecognized_roles=('nodes.ring:x-supplier-audit',)" in out
    return d


def _svg(supply, out, payload=None):
    return _run(EX / "igdm_to_svg.py", supply / "assets.ison", supply / "assets.igx.ison", payload or supply / "assets.igdm.ison", out)


def test_svg_is_valid_deterministic_and_does_not_interpret_x_roles(supply, tmp_path):
    a, b = tmp_path / "a.svg", tmp_path / "b.svg"
    assert _svg(supply, a).returncode == 0 and _svg(supply, b).returncode == 0
    assert a.read_bytes() == b.read_bytes()
    text = a.read_text(encoding="utf-8")
    xml.dom.minidom.parseString(text)                       # well-formed
    assert text.count("<g><title>") == 11 and text.count("<line ") == 11   # 3 suppliers + 2 facilities + 6 components; 3+3+5 edges
    for expected in ("EMEA", "APAC", "Pump assembly P-100", "stroke-dasharray=\"5 4\"", ">audit<", "Acme Castings, under audit"):
        assert expected in text, expected
    assert "x-supplier-audit" not in text                   # preserved in the payload, never interpreted or echoed


def test_unknown_x_role_renders_exactly_like_no_hint():
    sys.path.insert(0, str(EX))
    try:
        from igdm_to_svg import render
    finally:
        sys.path.remove(str(EX))
    from ison_graph import ISONGraph

    from isongraph_ext.igdm import DatamaticsPayload, NodeHints, NodeRef
    g = ISONGraph()
    g.add_node("p", 1)
    g.add_node("p", 2)
    g.add_edge("r", ("p", 1), ("p", 2))
    gb = g.to_ison().encode("utf-8")
    with_x = DatamaticsPayload("a0" * 32, "ison-v1", nodes=(NodeHints(NodeRef("p", 1), role="x-risk", shape_role="x-blob"),))
    without = DatamaticsPayload("a0" * 32, "ison-v1", nodes=(NodeHints(NodeRef("p", 1)),))
    assert render(gb, with_x) == render(gb, without)
    assert "x-risk" not in render(gb, with_x)


def test_svg_adapter_refuses_unverified_intent(supply, tmp_path):
    bad = tmp_path / "tampered.igdm.ison"
    bad.write_bytes((supply / "assets.igdm.ison").read_bytes() + b"\n")
    out = tmp_path / "x.svg"
    p = _svg(supply, out, bad)
    assert p.returncode == 1 and not out.exists() and b"refusing to render" in p.stderr


def test_fresh_environment_installs_built_wheel_and_runs_examples(request, tmp_path, supply):
    if not request.config.getoption("--built"):
        pytest.skip("run with --built after `python -m build`")
    wheels = glob.glob(str(DIST / "isongraph_ext-0.4.1-*.whl"))
    assert wheels, "no wheel in dist/"
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    r = subprocess.run([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check", wheels[0]], capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    work = tmp_path / "work"
    work.mkdir()
    where = _run("-c", "import isongraph_ext, ison_graph; print(isongraph_ext.__file__)", cwd=work, env_extra={}, python=py)
    assert b"site-packages" in where.stdout, where
    for script, marker in (("institutional_evidence.py", "institutional_evidence"), ("supply_chain_assets.py", "supply_chain_assets"),
                           ("core_only.py", "core_only"), ("measure.py", "measure")):
        _ok(_run(EX / script, *(["50"] if script == "measure.py" else []), cwd=work, env_extra={}, python=py), marker)
    svg = work / "out.svg"
    p = _run(EX / "igdm_to_svg.py", supply / "assets.ison", supply / "assets.igx.ison", supply / "assets.igdm.ison", svg, cwd=work, env_extra={}, python=py)
    assert p.returncode == 0 and svg.read_text(encoding="utf-8").startswith("<svg")


def _fixture_files(tmp_path, g, payload_kw, profile="ison-v1", name="x"):
    sys.path.insert(0, str(SRC))
    try:
        import hashlib

        from isongraph_ext import igdm
        from isongraph_ext.igdm import DatamaticsPayload
        gb = g.to_ison().encode("utf-8") if profile == "ison-v1" else g.to_isonl().encode("utf-8")
        p = DatamaticsPayload(hashlib.sha256(gb).hexdigest(), profile, **payload_kw)
        b = igdm.bind(gb, p, serialization_profile=profile, producer_port="python", identity_claim="artifact")
    finally:
        sys.path.remove(str(SRC))
    paths = [tmp_path / f"{name}.ison", tmp_path / f"{name}.igx.ison", tmp_path / f"{name}.igdm.ison"]
    for path, data in zip(paths, (gb, b.to_ison().encode("utf-8"), p.to_ison().encode("utf-8"))):
        path.write_bytes(data)
    return paths


def test_svg_adapter_refuses_what_it_cannot_draw_without_a_traceback(tmp_path):
    from ison_graph import ISONGraph
    from ison_graph.multigraph import MultiGraph
    m = MultiGraph()
    m.add_node("p", 1)
    m.add_node("p", 2)
    m.add_edge("r", ("p", 1), ("p", 2))
    g = ISONGraph()
    g.add_node("p", 1)
    for graph, profile in ((m, "ison-v1"), (g, "isonl-v1")):
        d = tmp_path / profile
        d.mkdir()
        files = _fixture_files(d, graph, {}, profile)
        out = d / "o.svg"
        p = _run(EX / "igdm_to_svg.py", *files, out)
        assert p.returncode == 2 and not out.exists() and b"Traceback" not in p.stderr and b"cannot draw" in p.stderr, (profile, p.stderr)
    p = _run(EX / "igdm_to_svg.py", tmp_path / "missing.ison", tmp_path / "b", tmp_path / "p", tmp_path / "o.svg")
    assert p.returncode == 64 and b"Traceback" not in p.stderr


def test_svg_escapes_text_hides_hidden_nodes_and_draws_undirected_edges_once(tmp_path):
    sys.path.insert(0, str(EX))
    sys.path.insert(0, str(SRC))
    try:
        from igdm_to_svg import render
        from ison_graph import ISONGraph

        from isongraph_ext.igdm import DatamaticsPayload, EdgeAddress, EdgeHints, Group, Member, NodeHints, NodeRef
    finally:
        sys.path.remove(str(EX))
        sys.path.remove(str(SRC))
    g = ISONGraph(directed=False)
    for i in (1, 2, 3):
        g.add_node("p", i)
    g.add_edge("r", ("p", 1), ("p", 2))
    g.add_edge("r", ("p", 1), ("p", 3))
    p = DatamaticsPayload(
        "a0" * 32, "ison-v1",
        nodes=(NodeHints(NodeRef("p", 1), label="A & <B>", a11y_text='say "hi" <now>', badge="<>"), NodeHints(NodeRef("p", 3), visibility="hidden", label="SECRET")),
        edges=(EdgeHints(EdgeAddress(NodeRef("p", 1), "r", NodeRef("p", 2)), pattern_role="dashed", label="x & y"),),
        groups=(Group("g", "hull", label="G <1>"),), members=(Member("g", NodeRef("p", 1)),))
    svg = render(g.to_ison().encode("utf-8"), p)
    xml.dom.minidom.parseString(svg)
    assert "A &amp; &lt;B&gt;" in svg and "G &lt;1&gt;" in svg and "x &amp; y" in svg and "SECRET" not in svg
    assert svg.count("<line ") == 1 and "marker-end" not in svg and 'stroke-dasharray="5 4"' in svg   # one logical edge, hint applied, no arrow

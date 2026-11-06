import os
import subprocess
import sys
from pathlib import Path

from conftest import ROOT, graph_bytes
from ison_parser import loads

from isongraph_ext.igx.bind import bind

SRC_DIR = ROOT / "isongraph-ext" / "src"


def run(*args):
    env = {**os.environ, "PYTHONPATH": str(SRC_DIR), "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, "-m", "isongraph_ext.igx", *map(str, args)], capture_output=True, text=True, env=env)
    return p.returncode, p.stdout


def _row(stdout, name):
    doc = loads(stdout)
    return next(b for b in doc.blocks if b.name == name).rows[0]


def _files(tmp_path: Path, graph_rel="ids/positive-int.ison", claim="producer_bound", mutate=None):
    g = tmp_path / "g.ison"
    g.write_bytes(graph_bytes(graph_rel))
    text = bind(g.read_bytes(), serialization_profile="ison-v1", producer_port="python", identity_claim=claim).to_ison()
    b = tmp_path / "g.igx.ison"
    b.write_bytes((mutate(text) if mutate else text).encode("utf-8"))
    return g, b


def test_verify_ok(tmp_path):
    g, b = _files(tmp_path)
    code, out = run("verify", g, b)
    assert code == 0
    row = _row(out, "verification")
    assert row["source_canonical"] == "true" and row["steps_passed"] == "V0,V1,V2,V3,V4,V5"


def test_verify_rejects_crlf_binding_file(tmp_path):
    # Review Focus 1: the CLI reads bytes, so an editor's CRLF rewrite is caught as non-canonical.
    g, b = _files(tmp_path, mutate=lambda t: t.replace("\n", "\r\n"))
    code, out = run("verify", g, b)
    assert code == 1 and _row(out, "error")["code"] == "MALFORMED_BINDING" and _row(out, "error")["field"] == "canonical_form"


def test_verify_wrong_graph(tmp_path):
    g, b = _files(tmp_path)
    g.write_bytes(graph_bytes("structure/undirected-basic.ison"))
    code, out = run("verify", g, b)
    assert code == 1 and _row(out, "error")["code"] == "SOURCE_BINDING_MISMATCH" and _row(out, "error")["step"] == "V4"


def test_admit_ok(tmp_path):
    g, b = _files(tmp_path)
    code, out = run("admit", g, b)
    assert code == 0 and _row(out, "admission")["admitted"] is True and _row(out, "admission")["receipt_posture"] == "OK"


def test_admit_denied_exit_2(tmp_path):
    g, b = _files(tmp_path, graph_rel="values/int-beyond-int64.ison", claim="artifact",
                  mutate=lambda t: t.replace("IGX/1 artifact", "IGX/1 producer_bound"))
    code, out = run("admit", g, b)
    assert code == 2
    row = _row(out, "admission")
    assert row["admitted"] is False and row["code"] == "IDENTITY_CLAIM_INADMISSIBLE" and "SOURCE_NOT_ELIGIBLE:INTEGER_OUT_OF_INT64" in row["reasons"]


def test_admit_invalid_exit_1(tmp_path):
    g, b = _files(tmp_path, mutate=lambda t: t + "\n")
    code, out = run("admit", g, b)
    assert code == 1 and _row(out, "error")["step"] == "V1"


def test_usage_errors_exit_64_never_2(tmp_path):
    code, out = run("verify")
    assert code == 64 and out == ""
    code, out = run("admit", tmp_path / "missing.ison", tmp_path / "missing.igx.ison")
    assert code == 64 and out == ""

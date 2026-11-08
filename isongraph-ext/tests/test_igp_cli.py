import os
import subprocess
import sys

from conftest import ROOT
from igp_helpers import INSTITUTIONAL, pol
from ison_parser import loads

SRC = ROOT / "isongraph-ext" / "src"
POLICY = pol(("decision", "D-4"), mandatory=[("meeting", "2026-03-12")], direction="both", depth=2)


def run(*args):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env.update({"PYTHONPATH": str(SRC), "PYTHONUTF8": "0"})
    p = subprocess.run([sys.executable, "-m", "isongraph_ext.igp", *map(str, args)], capture_output=True, env=env)
    return p.returncode, p.stdout.decode("utf-8")


def block(out):
    (b,) = loads(out).blocks
    return b.name, b.rows[0]


def files(tmp_path):
    s, p = tmp_path / "s.ison", tmp_path / "p.igp.ison"
    s.write_bytes(INSTITUTIONAL)
    p.write_bytes(POLICY.to_ison().encode("utf-8"))
    return s, p


def test_project_writes_result_and_payload_and_prints_one_block(tmp_path):
    s, p = files(tmp_path)
    code, out = run("project", s, p, "--out", tmp_path / "out")
    name, row = block(out)
    assert code == 0 and name == "projection" and out.endswith("\n") and "\r" not in out
    assert row["policy_sha256"] == POLICY.digest and row["selected_nodes"] == 5 and row["truncated"] is False
    assert (tmp_path / "out" / "result.ison").is_file() and (tmp_path / "out" / "result.igpv.ison").is_file()


def test_verify_roundtrip_and_tamper(tmp_path):
    s, p = files(tmp_path)
    assert run("project", s, p, "--out", tmp_path / "out")[0] == 0
    r, pl = tmp_path / "out" / "result.ison", tmp_path / "out" / "result.igpv.ison"
    code, out = run("verify", s, p, r, pl)
    assert code == 0 and block(out)[0] == "projection"
    r.write_bytes(r.read_bytes() + b"\n")
    code, out = run("verify", s, p, r, pl)
    name, row = block(out)
    assert code == 1 and name == "error" and row["code"] == "RESULT_MISMATCH" and row["step"] == "Q4"


def test_policy_and_source_errors_exit_1_and_usage_exit_64(tmp_path):
    s, p = files(tmp_path)
    bad = tmp_path / "bad.igp.ison"
    bad.write_bytes(b"nope")
    code, out = run("project", s, bad, "--out", tmp_path / "o")
    assert code == 1 and block(out)[1]["code"] == "POLICY_MALFORMED"
    assert run("project", s, p)[0] == 64
    assert run("project", tmp_path / "missing", p, "--out", tmp_path / "o")[0] == 64
    assert run("verify", s, p)[0] == 64

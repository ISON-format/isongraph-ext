import os
import subprocess
import sys

from conftest import ROOT
from igdm_helpers import real_payload, sha, target_graph
from ison_parser import loads

from isongraph_ext.igx.bind import bind as igx_bind
from isongraph_ext.igx.binding import Capability

SRC_DIR = ROOT / "isongraph-ext" / "src"
T = target_graph()


def run(*args):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env.update({"PYTHONPATH": str(SRC_DIR), "PYTHONUTF8": "0"})
    p = subprocess.run([sys.executable, "-m", "isongraph_ext.igdm", *map(str, args)], capture_output=True, env=env)
    return p.returncode, p.stdout.decode("utf-8")


def _blocks(out):
    return {b.name: b for b in loads(out).blocks}


def _files(tmp_path, mutate_payload=None):
    p = real_payload(T)
    g, b, pl = tmp_path / "g.ison", tmp_path / "g.igx.ison", tmp_path / "g.igdm.ison"
    g.write_bytes(T)
    text = p.to_ison()
    pbytes = (mutate_payload(text) if mutate_payload else text).encode("utf-8")
    pl.write_bytes(pbytes)
    b.write_bytes(igx_bind(T, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact",
                           capabilities=(Capability("igdm", "^1", "REQUIRED", sha(pbytes)),)).to_ison().encode("utf-8"))
    return g, b, pl


def test_verify_ok_single_document(tmp_path):
    g, b, pl = _files(tmp_path)
    code, out = run("verify", g, b, pl)
    blocks = _blocks(out)
    assert code == 0 and set(blocks) == {"verification", "datamatics", "admission"} and out.endswith("\n") and "\r" not in out
    dm = blocks["datamatics"].rows[0]
    assert dm["object_resolution"] == "full" and dm["counts"] == "nodes=2,edges=1,groups=2,members=3" and dm["steps_passed"] == "D0,D1,D2,D3,D4"


def test_error_exit_1_and_usage_64(tmp_path):
    g, b, pl = _files(tmp_path, mutate_payload=lambda t: t + "\n")
    code, out = run("verify", g, b, pl)
    assert code == 1 and set(_blocks(out)) == {"error"} and _blocks(out)["error"].rows[0]["code"] == "MALFORMED_DATAMATICS"
    assert run("verify")[0] == 64 and run("verify", g, b, tmp_path / "missing")[0] == 64

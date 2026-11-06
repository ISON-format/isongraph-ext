import dataclasses
import os
import subprocess
import sys

from conftest import ROOT
from igpv_helpers import bound, doc_bytes, origin_graph, real_payload, sha, target_graph
from ison_graph import ISONGraph
from ison_parser import loads

from isongraph_ext.igpv.records import Artifact, Attribution, GraphObject, Producer
from isongraph_ext.igx.bind import bind as igx_bind
from isongraph_ext.igx.binding import Capability

SRC_DIR = ROOT / "isongraph-ext" / "src"
T, O, D = target_graph(), origin_graph(), doc_bytes()


def run(*args):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env.update({"PYTHONPATH": str(SRC_DIR), "PYTHONUTF8": "0"})
    p = subprocess.run([sys.executable, "-m", "isongraph_ext.igpv", *map(str, args)], capture_output=True, env=env)
    return p.returncode, p.stdout.decode("utf-8")


def _blocks(out):
    return {b.name: b for b in loads(out).blocks}


def _files(tmp_path, p=None, mutate_payload=None, mutate_binding=None):
    p = p or real_payload(T, O, D)
    g, b, pl = tmp_path / "g.ison", tmp_path / "g.igx.ison", tmp_path / "g.igpv.ison"
    g.write_bytes(T)
    ptext = p.to_ison()
    pbytes = (mutate_payload(ptext) if mutate_payload else ptext).encode("utf-8")
    pl.write_bytes(pbytes)
    # the binding carries the digest of the payload bytes actually shipped, so a mutated payload reaches P1, not P0
    text = igx_bind(T, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact",
                    capabilities=(Capability("igpv", "^1", "REQUIRED", sha(pbytes)),)).to_ison()
    b.write_bytes((mutate_binding(text) if mutate_binding else text).encode("utf-8"))
    return g, b, pl


def test_verify_ok_prints_three_blocks_and_sources_verify(tmp_path):
    g, b, pl = _files(tmp_path)
    code, out = run("verify", g, b, pl)
    blocks = _blocks(out)
    assert code == 0 and set(blocks) == {"verification", "provenance", "admission"}
    prov = blocks["provenance"].rows[0]
    assert prov["object_resolution"] == "full" and prov["locators"] == "a0=UNVERIFIED,a2=UNVERIFIED" and prov["steps_passed"] == "P0,P1,P2,P3,P4,P5"
    assert out.endswith("\n") and "\r" not in out
    d = tmp_path / "doc.md"
    d.write_bytes(D)
    o = tmp_path / "o.ison"
    o.write_bytes(O)
    code, out = run("verify", g, b, pl, "--source", f"{sha(D)}={d}", "--source", f"{sha(O)}={o}")
    prov = _blocks(out)["provenance"].rows[0]
    assert code == 0 and prov["locators"] == "a0=VERIFIED,a2=VERIFIED" and prov["origin_resolution"] == "g0=verified"


def test_provenance_error_exit_1_no_admission_block(tmp_path):
    g, b, pl = _files(tmp_path, mutate_payload=lambda t: t + "\n")
    code, out = run("verify", g, b, pl)
    blocks = _blocks(out)
    assert code == 1 and set(blocks) == {"error"} and blocks["error"].rows[0]["code"] == "MALFORMED_PROVENANCE"
    g, b, pl = _files(tmp_path, mutate_binding=lambda t: t.replace("\n", "\r\n"))
    code, out = run("verify", g, b, pl)
    assert code == 1 and _blocks(out)["error"].rows[0]["code"] == "MALFORMED_BINDING"


def test_admission_denied_exit_2_after_full_verification(tmp_path):
    # Target ineligible for a Core-semantic identity (id beyond INT64); the payload attributes only the graph object,
    # so IGPV/1 verifies fully, and the producer_bound claim is denied by IGX/1 admission -> exit 2 with all three blocks.
    big = ISONGraph()
    big.add_node("p", 2**70)
    tb = big.to_ison().encode("utf-8")
    p = real_payload(tb, O, D, artifacts=(Artifact("src0", sha(D), "document", len(D), media_type="text/markdown"),),
                     producers=(Producer("x0", "extractor", "ext", "1.0.0"),),
                     objects=(GraphObject("G", "graph"),), attributions=(Attribution("a3", "G", "src0", "x0"),), derivations=())
    # igx.bind() refuses an inadmissible claim, so the binding file is produced by field replacement, as a historical file would arrive.
    base = igx_bind(tb, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact",
                    capabilities=(Capability("igpv", "^1", "REQUIRED", p.digest),))
    g, bf, pl = tmp_path / "g.ison", tmp_path / "g.igx.ison", tmp_path / "g.igpv.ison"
    g.write_bytes(tb)
    bf.write_bytes(dataclasses.replace(base, identity_claim="producer_bound").to_ison().encode("utf-8"))
    pl.write_bytes(p.to_ison().encode("utf-8"))
    code, out = run("verify", g, bf, pl)
    blocks = _blocks(out)
    assert code == 2 and set(blocks) == {"verification", "provenance", "admission"}
    assert blocks["admission"].rows[0]["code"] == "IDENTITY_CLAIM_INADMISSIBLE"


def test_usage_errors_exit_64(tmp_path):
    g, b, pl = _files(tmp_path)
    assert run("verify")[0] == 64
    assert run("verify", g, b, tmp_path / "missing.igpv.ison")[0] == 64
    assert run("verify", g, b, pl, "--source", "nothex=" + str(g))[0] == 64
    assert run("verify", g, b, pl, "--source", f"{sha(D)}={tmp_path / 'missing.md'}")[0] == 64
    assert run("origins", "zz", pl)[0] == 64
    assert run("origins", sha(T), pl, "--node", "p", "1", "--edge", "p", "1", "knows", "p", "s1")[0] == 64


def test_origins_table(tmp_path):
    g, b, pl = _files(tmp_path)
    code, out = run("origins", sha(T), pl, "--node", "p", "1")
    rows = _blocks(out)["lineage"].rows
    assert code == 0 and [(r["depth"], r["node_id"], r["derivation_kind"], r["terminal"]) for r in rows] == [
        (1, 7, "collapse", None), (1, 7, None, "payload_unavailable"), (1, 8, "collapse", None), (1, 8, None, "payload_unavailable")]
    code, out = run("origins", sha(T), pl, "--node", "p", '"1"')
    assert code == 0 and _blocks(out)["lineage"].rows[0]["terminal"] == "no_derivation_record"
    code, out = run("origins", sha(T), pl, "--edge", "p", "1", "knows", "p", "s1")
    assert code == 0 and _blocks(out)["lineage"].rows[0]["terminal"] == "no_derivation_record"

# isongraph-ext/tests/test_igdc_cli.py
"""IGDC/1 CLI: derive / verify, exit codes 0 / 1 / 64, one canonical document per response, inputs read within the byte budget."""
import os
import subprocess
import sys

from conftest import ROOT
from igdm_helpers import bound, real_payload, target_graph
from ison_parser import dumps_canonical, loads

from isongraph_ext import _cli
from isongraph_ext.igdc import consume
from isongraph_ext.igdc.__main__ import main as igdc_main
from isongraph_ext.igdm.records import Limits

SRC_DIR = ROOT / "isongraph-ext" / "src"
T = target_graph()


def run(*args):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env.update({"PYTHONPATH": str(SRC_DIR), "PYTHONUTF8": "0"})
    p = subprocess.run([sys.executable, "-m", "isongraph_ext.igdc", *map(str, args)], capture_output=True, env=env)
    return p.returncode, p.stdout, p.stderr


def _blocks(out: bytes):
    return {b.name: b for b in loads(out.decode("utf-8")).blocks}


def _files(tmp_path):
    p = real_payload(T)
    b = bound(p, T)
    g, bf, pl = tmp_path / "g.ison", tmp_path / "g.igx.ison", tmp_path / "g.igdm.ison"
    g.write_bytes(T)
    pl.write_bytes(p.to_ison().encode("utf-8"))
    bf.write_bytes(b.to_ison().encode("utf-8"))
    return g, bf, pl, consume(p.to_ison(), b, T)


def test_derive_prints_exactly_the_consume_bytes(tmp_path):
    g, b, pl, expected = _files(tmp_path)
    code, out, err = run("derive", g, b, pl)
    assert code == 0 and err == b"" and out == expected.to_ison().encode("utf-8") and b"\r" not in out


def test_verify_accepts_a_derived_document_with_and_without_the_target(tmp_path):
    g, b, pl, expected = _files(tmp_path)
    hints = tmp_path / "h.igdc.ison"
    hints.write_bytes(run("derive", g, b, pl)[1])
    code, out, _ = run("verify", hints)
    row = _blocks(out)["verification"].rows[0]
    assert code == 0 and set(_blocks(out)) == {"verification"} and out.endswith(b"\n") and b"\r" not in out
    assert row["steps_passed"] == "C0,C1,C2,C3" and row["derivation_checked"] is False and row["hints_sha256"] == expected.digest
    code, out, _ = run("verify", hints, g, b, pl)
    row = _blocks(out)["verification"].rows[0]
    assert code == 0 and row["steps_passed"] == "C0,C1,C2,C3,C4" and row["derivation_checked"] is True


def test_verify_exit_1_on_a_corrupted_copy(tmp_path):
    g, b, pl, _ = _files(tmp_path)
    hints = tmp_path / "h.igdc.ison"
    hints.write_bytes(run("derive", g, b, pl)[1] + b"\n")
    code, out, _ = run("verify", hints)
    err = _blocks(out)["error"].rows[0]
    assert code == 1 and set(_blocks(out)) == {"error"} and err["code"] == "MALFORMED_CONSUMPTION" and err["step"] == "C0"


def test_verify_exit_1_on_a_repeated_column_document(tmp_path):
    g, b, pl, expected = _files(tmp_path)
    d = expected.to_document()
    d.blocks[-1].fields.append(d.blocks[-1].fields[0])
    hints = tmp_path / "h.igdc.ison"
    hints.write_bytes(dumps_canonical(d).encode("utf-8"))
    code, out, _ = run("verify", hints)
    err = _blocks(out)["error"].rows[0]
    assert code == 1 and err["code"] == "MALFORMED_CONSUMPTION" and err["step"] == "C1"


def test_verify_c4_mismatch_is_an_error_and_igdm_errors_pass_through(tmp_path):
    g, b, pl, expected = _files(tmp_path)
    other = real_payload(T, nodes=(), edges=(), groups=(), members=())
    other_hints = tmp_path / "o.igdc.ison"
    other_hints.write_bytes(consume(other.to_ison(), bound(other, T), T).to_ison().encode("utf-8"))
    code, out, _ = run("verify", other_hints, g, b, pl)
    assert code == 1 and _blocks(out)["error"].rows[0]["code"] == "DERIVATION_MISMATCH"
    bad = tmp_path / "bad.igdm.ison"
    bad.write_bytes(pl.read_bytes() + b"\n")
    code, out, _ = run("derive", g, b, bad)
    assert code == 1 and set(_blocks(out)) == {"error"} and _blocks(out)["error"].rows[0]["code"] == "PAYLOAD_DIGEST_MISMATCH"        # the binding pins the payload digest: igdm refuses first


def test_usage_errors_exit_64(tmp_path):
    g, b, pl, _ = _files(tmp_path)
    hints = tmp_path / "h.igdc.ison"
    hints.write_bytes(run("derive", g, b, pl)[1])
    assert run()[0] == 64 and run("derive")[0] == 64 and run("derive", g, b)[0] == 64 and run("verify")[0] == 64
    assert run("verify", hints, g)[0] == 64 and run("verify", hints, g, b)[0] == 64          # C4 needs all three inputs or none
    assert run("verify", tmp_path / "missing")[0] == 64 and run("derive", g, b, tmp_path / "missing")[0] == 64
    assert run("bogus")[0] == 64


def test_an_oversized_input_is_refused_before_it_is_fully_read(tmp_path, monkeypatch, capsys):
    import isongraph_ext.igdc.__main__ as m
    g, b, pl, _ = _files(tmp_path)
    hints = tmp_path / "h.igdc.ison"
    hints.write_bytes(run("derive", g, b, pl)[1])
    monkeypatch.setattr(m, "DEFAULT_LIMITS", Limits(max_payload_bytes=5))
    seen = []
    real = _cli.read_capped
    monkeypatch.setattr(m, "read_capped", lambda p, n: (seen.append((p.name, n)), real(p, n))[1])
    assert igdc_main(["verify", str(hints)]) == 1
    assert "DATAMATICS_LIMIT_EXCEEDED" in capsys.readouterr().out and ("h.igdc.ison", 5) in seen
    seen.clear()
    assert igdc_main(["derive", str(g), str(b), str(pl)]) == 1
    assert "DATAMATICS_LIMIT_EXCEEDED" in capsys.readouterr().out and ("g.igdm.ison", 5) in seen


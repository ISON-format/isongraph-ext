# isongraph-ext/tests/test_igar_cli.py
"""IGAR/1 CLI (25 §5): issue / inspect / subject / policy / authorize / recompute. Exit 0 / 1 / 2 / 64, one canonical document per response."""
import dataclasses
import hashlib
import os
import subprocess
import sys

import pytest
from conftest import CORE_COMMIT, ROOT
from igdm_helpers import bound, real_payload, target_graph
from ison_parser import Block, Document, dumps_canonical, loads

from isongraph_ext import _cli
from isongraph_ext.igar import issue
from isongraph_ext.igar.__main__ import main as igar_main
from isongraph_ext.igar.profile import Profile
from isongraph_ext.igdm.records import Limits

SRC_DIR = ROOT / "isongraph-ext" / "src"
T = target_graph()
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731


def run(*args):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env.update({"PYTHONPATH": str(SRC_DIR), "PYTHONUTF8": "0"})
    p = subprocess.run([sys.executable, "-m", "isongraph_ext.igar", *map(str, args)], capture_output=True, env=env)
    return p.returncode, p.stdout, p.stderr


def _blocks(out: bytes):
    return {b.name: b for b in loads(out.decode("utf-8")).blocks}


def _row(out: bytes, name: str) -> dict:
    return _blocks(out)[name].rows[0]


def _policy_bytes(*, verifier="isongraph-ext", version="0.4.1", profile=None, require_admission=True) -> bytes:
    prof = profile or Profile.default().digest
    doc = Document(blocks=[
        Block("meta", "policy", ["policy_spec", "require_admission", "require_full_resolution"],
              [{"policy_spec": "IGAR-POLICY/1", "require_admission": "true" if require_admission else "false", "require_full_resolution": "true"}]),
        Block("table", "verifiers", ["verifier", "verifier_version"], [{"verifier": verifier, "verifier_version": version}]),
        Block("table", "core_commits", ["core_commit"], [{"core_commit": CORE_COMMIT}]),
        Block("table", "profiles", ["profile_sha256"], [{"profile_sha256": prof}]),
        Block("table", "runtime", ["runtime_ison_graph", "runtime_ison_py"], [])])
    return dumps_canonical(doc).encode("utf-8")


@pytest.fixture()
def files(tmp_path):
    p = real_payload(T)
    b = bound(p, T)
    g, bf, pl = tmp_path / "g.ison", tmp_path / "g.igx.ison", tmp_path / "g.igdm.ison"
    g.write_bytes(T)
    pl.write_bytes(p.to_ison().encode("utf-8"))
    bf.write_bytes(b.to_ison().encode("utf-8"))
    return g, bf, pl


def _issued(tmp_path, files, *extra):
    g, bf, pl = files
    code, out, err = run("issue", g, bf, pl, *extra)
    assert code == 0 and err == b""
    rc = tmp_path / "g.igar.ison"
    rc.write_bytes(out)
    return rc, out


def _with_hints(tmp_path, files):
    hints = tmp_path / "g.igdc.ison"
    rc, out = _issued(tmp_path, files, "--igdc", hints)
    return rc, out, hints


# ---- issue --------------------------------------------------------------------------------------------------------------------------
def test_issue_prints_exactly_the_receipt_bytes_under_the_default_profile(tmp_path, files):
    g, bf, pl = files
    code, out, err = run("issue", g, bf, pl)
    expected = issue(bf.read_bytes(), pl.read_bytes(), g.read_bytes())
    assert code == 0 and err == b"" and out == expected.to_ison().encode("utf-8") and b"\r" not in out and not out.endswith(b"\n")
    assert expected.verifier["profile_sha256"] == Profile.default().digest


def test_issue_with_a_malformed_binding_is_exit_0_and_a_rejection_receipt(tmp_path, files):
    g, bf, pl = files
    bad = tmp_path / "bad.igx.ison"
    bad.write_bytes(b"not a binding")
    code, out, err = run("issue", g, bad, pl)
    assert code == 0 and err == b"" and out == issue(b"not a binding", pl.read_bytes(), g.read_bytes()).to_ison().encode("utf-8")
    assert _row(out, "failure")["check"] == "V1" and _row(out, "result")["verification"] == "not_evaluated" and _row(out, "result")["binding_schema"] == "invalid"


def test_issue_igdc_writes_the_hint_document_the_receipt_names(tmp_path, files):
    rc, out, hints = _with_hints(tmp_path, files)
    r = _row(out, "subject")
    assert r["igdc_sha256"] == sha(hints.read_bytes()) and _row(out, "result")["consumption"] == "derived"
    assert not hints.read_bytes().endswith(b"\n") and b"\r" not in hints.read_bytes()


def test_issue_igdc_writes_nothing_when_the_receipt_names_no_hint_document(tmp_path, files):
    g, bf, pl = files
    bad = tmp_path / "bad.igx.ison"
    bad.write_bytes(b"not a binding")
    hints = tmp_path / "never.igdc.ison"
    code, out, _ = run("issue", g, bad, pl, "--igdc", hints)
    assert code == 0 and _row(out, "subject")["igdc_sha256"] is None and not hints.exists()


def test_issue_with_a_profile_file_records_that_profile(tmp_path, files):
    g, bf, pl = files
    prof = dataclasses.replace(Profile.default(), limits=Limits(max_group_depth=3))
    pf = tmp_path / "p.profile.ison"
    pf.write_bytes(prof.to_ison().encode("utf-8"))
    code, out, _ = run("issue", g, bf, pl, "--profile", pf)
    assert code == 0 and _row(out, "verifier")["profile_sha256"] == prof.digest != Profile.default().digest


def test_issue_with_a_malformed_profile_exits_1(tmp_path, files):
    g, bf, pl = files
    pf = tmp_path / "p.profile.ison"
    pf.write_bytes(b"garbage")
    code, out, _ = run("issue", g, bf, pl, "--profile", pf)
    assert code == 1 and _row(out, "error")["code"] == "MALFORMED_PROFILE"


# ---- inspect ------------------------------------------------------------------------------------------------------------------------
def test_inspect_accepts_a_well_formed_receipt_and_says_only_that(tmp_path, files):
    rc, out = _issued(tmp_path, files)
    code, o, err = run("inspect", rc)
    row = _row(o, "inspection")
    assert code == 0 and err == b"" and set(_blocks(o)) == {"inspection"} and o.endswith(b"\n") and b"\r" not in o
    assert row["receipt_sha256"] == sha(out) and row["steps_passed"] == "R0,R1,R2"
    low = o.lower()
    assert b"trusted" not in low and b"authenticat" not in low and b"authorized" not in low


def test_inspect_exit_1_on_a_repeated_column_copy(tmp_path, files):
    rc, _ = _issued(tmp_path, files)
    d = loads(rc.read_text(encoding="utf-8"))
    d.blocks[0].fields.append(d.blocks[0].fields[0])
    bad = tmp_path / "dup.igar.ison"
    bad.write_bytes(dumps_canonical(d).encode("utf-8"))
    code, o, _ = run("inspect", bad)
    err = _row(o, "error")
    assert code == 1 and set(_blocks(o)) == {"error"} and err["code"] == "MALFORMED_RECEIPT"


def test_inspect_exit_1_on_a_corrupted_copy_and_64_on_a_missing_file(tmp_path, files):
    rc, out = _issued(tmp_path, files)
    bad = tmp_path / "x.igar.ison"
    bad.write_bytes(out + b"\n")
    code, o, _ = run("inspect", bad)
    assert code == 1 and _row(o, "error")["code"] == "MALFORMED_RECEIPT"
    assert run("inspect", tmp_path / "missing")[0] == 64


# ---- subject ------------------------------------------------------------------------------------------------------------------------
def test_subject_is_64_when_a_required_input_is_omitted(tmp_path, files):
    rc, _ = _issued(tmp_path, files)
    g, bf, pl = files
    assert run("subject", rc)[0] == 64
    assert run("subject", rc, "--target", g, "--binding", bf)[0] == 64
    assert run("subject", rc, "--target", g, "--payload", pl)[0] == 64
    assert run("subject", "--target", g, "--binding", bf, "--payload", pl)[0] == 64


def test_subject_accepts_exact_bytes_and_refuses_others_with_exit_2(tmp_path, files):
    rc, _ = _issued(tmp_path, files)
    g, bf, pl = files
    code, o, _ = run("subject", rc, "--target", g, "--binding", bf, "--payload", pl)
    assert code == 0 and _row(o, "subject_check")["steps_passed"] == "R0,R1,R2,R3" and _row(o, "subject_check")["igdc_checked"] is False
    assert b"trusted" not in o.lower() and b"authenticat" not in o.lower()
    other = tmp_path / "other.ison"
    other.write_bytes(T + b"\n")
    code, o, _ = run("subject", rc, "--target", other, "--binding", bf, "--payload", pl)
    assert code == 2 and _row(o, "error")["code"] == "RECEIPT_SUBJECT_MISMATCH" and _row(o, "error")["step"] == "R3"


def test_subject_with_hint_document_checks_it_in_both_directions(tmp_path, files):
    rc, _, hints = _with_hints(tmp_path, files)
    g, bf, pl = files
    code, o, _ = run("subject", rc, "--target", g, "--binding", bf, "--payload", pl, "--igdc", hints)
    assert code == 0 and _row(o, "subject_check")["igdc_checked"] is True
    code, o, _ = run("subject", rc, "--target", g, "--binding", bf, "--payload", pl)          # the receipt names a hint document that was not supplied
    assert code == 2 and _row(o, "error")["code"] == "RECEIPT_SUBJECT_MISMATCH"


# ---- policy -------------------------------------------------------------------------------------------------------------------------
def test_policy_success_says_satisfied_and_that_it_is_not_an_authorization(tmp_path, files):
    rc, _ = _issued(tmp_path, files)
    pol = tmp_path / "t.policy.ison"
    pol.write_bytes(_policy_bytes())
    code, o, err = run("policy", rc, "--trust-policy", pol)
    row = _row(o, "policy_check")
    assert code == 0 and err == b"" and row["policy_satisfied"] is True and "authorized" not in row and row["steps_passed"] == "R0,R1,R2,R4"
    assert "not an authorization" in row["note"] and "provenance" in row["note"]
    assert b"trusted" not in o.lower() and b"authenticat" not in o.lower()


def test_policy_exit_2_on_an_excluded_verifier(tmp_path, files):
    rc, _ = _issued(tmp_path, files)
    pol = tmp_path / "t.policy.ison"
    pol.write_bytes(_policy_bytes(verifier="someone-else"))
    code, o, _ = run("policy", rc, "--trust-policy", pol)
    err = _row(o, "error")
    assert code == 2 and set(_blocks(o)) == {"error"} and (err["code"], err["step"], err["field"]) == ("RECEIPT_POLICY_UNSATISFIED", "R4", "verifier")


def test_policy_file_with_an_unexpected_block_exits_1_malformed_policy(tmp_path, files):
    rc, _ = _issued(tmp_path, files)
    d = loads(_policy_bytes().decode("utf-8"))
    d.blocks.append(Block("table", "extras", ["x"], [{"x": "1"}]))
    pol = tmp_path / "t.policy.ison"
    pol.write_bytes(dumps_canonical(d).encode("utf-8"))
    code, o, _ = run("policy", rc, "--trust-policy", pol)
    assert code == 1 and _row(o, "error")["code"] == "MALFORMED_POLICY"


def test_policy_without_the_policy_file_is_64(tmp_path, files):
    rc, _ = _issued(tmp_path, files)
    assert run("policy", rc)[0] == 64 and run("policy", rc, "--trust-policy", tmp_path / "missing")[0] == 64


def test_a_rejection_receipt_never_satisfies_a_policy(tmp_path, files):
    g, bf, pl = files
    code, out, _ = run("issue", g, tmp_path / "g.igdm.ison", pl)               # the payload as a binding: a rejection receipt
    assert code == 0 and _row(out, "result")["verification"] != "verified"
    rc = tmp_path / "rej.igar.ison"
    rc.write_bytes(out)
    pol = tmp_path / "t.policy.ison"
    pol.write_bytes(_policy_bytes(require_admission=False))
    code, o, _ = run("policy", rc, "--trust-policy", pol)
    assert code == 2 and _row(o, "error")["field"] == "verification"


# ---- authorize ----------------------------------------------------------------------------------------------------------------------
def _auth_args(tmp_path, files, hints, pins_text=None, name="g.igar.ison"):
    g, bf, pl = files
    rc = tmp_path / name
    pins = tmp_path / "SHA256SUMS"
    pins.write_text(pins_text if pins_text is not None else f"{sha(rc.read_bytes())}  {name}\n", encoding="utf-8", newline="\n")
    pol = tmp_path / "t.policy.ison"
    pol.write_bytes(_policy_bytes())
    return ["authorize", rc, "--pins", pins, "--target", g, "--binding", bf, "--payload", pl, "--igdc", hints, "--trust-policy", pol]


def test_authorize_prints_the_admitted_digests_when_everything_holds(tmp_path, files):
    rc, out, hints = _with_hints(tmp_path, files)
    g, bf, pl = files
    code, o, err = run(*_auth_args(tmp_path, files, hints))
    row = _row(o, "authorization")
    assert code == 0 and err == b"" and set(_blocks(o)) == {"authorization"} and b"\r" not in o
    assert row["authorized"] is True and row["receipt_sha256"] == sha(out)
    assert (row["target_artifact_sha256"], row["binding_sha256"], row["igdm_payload_sha256"], row["igdc_sha256"]) == (
        sha(g.read_bytes()), sha(bf.read_bytes()), sha(pl.read_bytes()), sha(hints.read_bytes()))
    assert row["profile_sha256"] == Profile.default().digest and row["verifier"] == "isongraph-ext" and row["core_commit"] == CORE_COMMIT
    assert "signature" in row["note"] and "freshness" in row["note"]


def test_authorize_exit_2_not_pinned_when_the_pin_file_does_not_list_the_receipt(tmp_path, files):
    _issued_rc, _, hints = _with_hints(tmp_path, files)
    other = "a" * 64
    code, o, _ = run(*_auth_args(tmp_path, files, hints, pins_text=f"{other}  unrelated.file\n"))
    assert code == 2 and _row(o, "error")["code"] == "RECEIPT_NOT_PINNED" and _row(o, "error")["step"] == "R5"


def test_authorize_exit_2_not_pinned_when_the_pin_lists_other_bytes_for_the_name(tmp_path, files):
    _, _, hints = _with_hints(tmp_path, files)
    code, o, _ = run(*_auth_args(tmp_path, files, hints, pins_text=f"{'b' * 64}  g.igar.ison\n"))
    assert code == 2 and _row(o, "error")["code"] == "RECEIPT_NOT_PINNED"


def test_authorize_pins_only_the_receipt_file_named_on_the_command_line(tmp_path, files):
    rc, out, hints = _with_hints(tmp_path, files)
    g = files[0]
    text = f"{sha(g.read_bytes())}  g.ison\n{sha(out)}  g.igar.ison\n"                      # other lines are harmless; only this name is looked up
    assert run(*_auth_args(tmp_path, files, hints, pins_text=text))[0] == 0
    # a pin for the graph does not pin the receipt, and the receipt's own pin is by its file name
    code, o, _ = run(*_auth_args(tmp_path, files, hints, pins_text=f"{sha(out)}  elsewhere.igar.ison\n"))
    assert code == 2 and _row(o, "error")["code"] == "RECEIPT_NOT_PINNED"


def test_authorize_malformed_pin_files_exit_1_with_malformed_pins(tmp_path, files):
    rc, out, hints = _with_hints(tmp_path, files)
    line = f"{sha(out)}  g.igar.ison\n"
    for text in (line + line, "not a pin line\n", line.replace("\n", "\r"), line.replace("  ", " *")):
        code, o, _ = run(*_auth_args(tmp_path, files, hints, pins_text=text))
        assert code == 1 and _row(o, "error")["code"] == "MALFORMED_PINS", text
    pins = tmp_path / "SHA256SUMS"
    args = _auth_args(tmp_path, files, hints)
    pins.write_bytes(b"\xff\xfe")
    code, o, _ = run(*args)
    assert code == 1 and _row(o, "error")["code"] == "MALFORMED_PINS"


def test_authorize_pin_file_with_crlf_endings_is_accepted(tmp_path, files):
    rc, out, hints = _with_hints(tmp_path, files)
    pins = tmp_path / "SHA256SUMS"
    args = _auth_args(tmp_path, files, hints)
    pins.write_bytes(f"{sha(out)}  g.igar.ison\r\n".encode())
    assert run(*args)[0] == 0


def test_authorize_every_input_is_required(tmp_path, files):
    _, _, hints = _with_hints(tmp_path, files)
    args = _auth_args(tmp_path, files, hints)
    for flag in ("--pins", "--target", "--binding", "--payload", "--igdc", "--trust-policy"):
        i = args.index(flag)
        assert run(*args[:i], *args[i + 2:])[0] == 64, flag


def test_authorize_subject_and_policy_failures_exit_2_and_a_pinned_rejection_receipt_is_refused(tmp_path, files):
    rc, out, hints = _with_hints(tmp_path, files)
    args = _auth_args(tmp_path, files, hints)
    args[args.index("--target") + 1] = tmp_path / "g.igdm.ison"                          # other bytes than the receipt is about
    code, o, _ = run(*args)
    assert code == 2 and _row(o, "error")["code"] == "RECEIPT_SUBJECT_MISMATCH"
    args = _auth_args(tmp_path, files, hints)
    pol = args[args.index("--trust-policy") + 1]
    pol.write_bytes(_policy_bytes(version="9.9.9"))
    code, o, _ = run(*args)
    assert code == 2 and _row(o, "error")["code"] == "RECEIPT_POLICY_UNSATISFIED"
    g, bf, pl = files
    code, rej, _ = run("issue", g, pl, pl)                                               # a rejection receipt, delivered through the pinned channel
    assert code == 0
    rcj = tmp_path / "rej.igar.ison"
    rcj.write_bytes(rej)
    pol.write_bytes(_policy_bytes())
    pins = tmp_path / "SHA256SUMS"
    pins.write_text(f"{sha(rej)}  rej.igar.ison\n", encoding="utf-8", newline="\n")
    args = _auth_args(tmp_path, files, hints, pins_text=f"{sha(rej)}  rej.igar.ison\n", name="rej.igar.ison")
    args[args.index("--binding") + 1] = pl                                               # the rejection receipt is about exactly these bytes; only the hint document is wrong
    code, o, _ = run(*args)
    assert code == 2 and (_row(o, "error")["code"], _row(o, "error")["field"]) == ("RECEIPT_SUBJECT_MISMATCH", "meta.subject.igdc_sha256")


def test_only_a_successful_authorize_ever_says_authorized_and_nothing_else_says_trusted(tmp_path, files):
    rc, out, hints = _with_hints(tmp_path, files)
    g, bf, pl = files
    pol = tmp_path / "t.policy.ison"
    pol.write_bytes(_policy_bytes())
    pf = tmp_path / "default.profile.ison"
    pf.write_bytes(Profile.default().to_ison().encode("utf-8"))
    others = [run("inspect", rc)[1], run("subject", rc, "--target", g, "--binding", bf, "--payload", pl, "--igdc", hints)[1],
              run("recompute", rc, g, bf, pl, "--profile", pf)[1], out]
    for o in others:
        assert b"trusted" not in o.lower() and b"authenticat" not in o.lower() and b"authoriz" not in o.lower()
    pol_out = run("policy", rc, "--trust-policy", pol)[1]
    assert "authorized" not in _row(pol_out, "policy_check") and b"trusted" not in pol_out.lower() and b"authenticat" not in pol_out.lower()
    assert _row(run(*_auth_args(tmp_path, files, hints))[1], "authorization")["authorized"] is True


# ---- recompute ----------------------------------------------------------------------------------------------------------------------
def test_recompute_needs_the_profile_and_reproduces_the_receipt(tmp_path, files):
    rc, _ = _issued(tmp_path, files)
    g, bf, pl = files
    assert run("recompute", rc, g, bf, pl)[0] == 64                                      # the profile is never defaulted
    pf = tmp_path / "default.profile.ison"
    pf.write_bytes(Profile.default().to_ison().encode("utf-8"))
    code, o, err = run("recompute", rc, g, bf, pl, "--profile", pf)
    row = _row(o, "recomputation")
    assert code == 0 and err == b"" and row["reproduced"] is True and row["steps_passed"] == "R0,R1,R2,R6"
    assert b"trusted" not in o.lower() and b"authenticat" not in o.lower()


def test_recompute_with_a_different_profile_is_exit_2_recompute_unavailable(tmp_path, files):
    rc, _ = _issued(tmp_path, files)
    g, bf, pl = files
    other = tmp_path / "other.profile.ison"
    other.write_bytes(dataclasses.replace(Profile.default(), limits=Limits(max_group_depth=3)).to_ison().encode("utf-8"))
    code, o, _ = run("recompute", rc, g, bf, pl, "--profile", other)
    assert code == 2 and _row(o, "error")["code"] == "RECOMPUTE_UNAVAILABLE" and _row(o, "error")["step"] == "R6"


def test_recompute_with_garbage_for_a_profile_is_unavailable_not_a_verdict_on_the_receipt(tmp_path, files):
    rc, _ = _issued(tmp_path, files)
    g, bf, pl = files
    bad = tmp_path / "bad.profile.ison"
    bad.write_bytes(b"garbage")
    code, o, _ = run("recompute", rc, g, bf, pl, "--profile", bad)
    assert code == 2 and _row(o, "error")["code"] == "RECOMPUTE_UNAVAILABLE"            # the digest of the supplied bytes is not the one the receipt names


# ---- usage and budgets --------------------------------------------------------------------------------------------------------------
def test_usage_errors_exit_64(tmp_path, files):
    g, bf, pl = files
    assert run()[0] == 64 and run("bogus")[0] == 64 and run("issue")[0] == 64 and run("issue", g, bf)[0] == 64
    assert run("issue", g, bf, tmp_path / "missing")[0] == 64 and run("inspect")[0] == 64
    assert run("issue", g, bf, pl, "--profile", tmp_path / "missing")[0] == 64


def test_an_oversized_input_is_refused_before_it_is_fully_read(tmp_path, files, monkeypatch, capsys):
    import isongraph_ext.igar.__main__ as m
    rc, _ = _issued(tmp_path, files)
    g, bf, pl = files
    monkeypatch.setattr(m, "DEFAULT_LIMITS", Limits(max_payload_bytes=5, max_graph_bytes=5))
    seen = []
    real = _cli.read_capped
    monkeypatch.setattr(m, "read_capped", lambda p, n: (seen.append((p.name, n)), real(p, n))[1])
    assert igar_main(["inspect", str(rc)]) == 1
    assert "RECEIPT_LIMIT_EXCEEDED" in capsys.readouterr().out and ("g.igar.ison", 5) in seen
    seen.clear()
    assert igar_main(["issue", str(g), str(bf), str(pl)]) == 1                         # never a receipt about a truncated file
    out = capsys.readouterr().out
    assert "RECEIPT_LIMIT_EXCEEDED" in out and "<" not in out and all(n == 5 for _, n in seen) and seen
    seen.clear()
    assert igar_main(["subject", str(rc), "--target", str(g), "--binding", str(bf), "--payload", str(pl)]) == 1
    assert "RECEIPT_LIMIT_EXCEEDED" in capsys.readouterr().out and all(n == 5 for _, n in seen)


def test_the_cli_never_reads_more_than_budget_plus_one_byte(tmp_path, monkeypatch):
    import isongraph_ext.igar.__main__ as m
    big = tmp_path / "big.igar.ison"
    big.write_bytes(b"x" * 10_000)
    monkeypatch.setattr(m, "DEFAULT_LIMITS", Limits(max_payload_bytes=7))
    lens = []
    real = _cli.read_capped
    monkeypatch.setattr(m, "read_capped", lambda p, n: (lambda d: (lens.append(len(d)), d)[1])(real(p, n)))
    assert igar_main(["inspect", str(big)]) == 1 and lens == [8]


# ---- issue --igdc OUT never overwrites an input of the same invocation (or a directory) ------------------------------------------------
def _issue_args(files, tmp_path, out, *, with_profile=True):
    g, bf, pl = files
    pf = tmp_path / "p.profile.ison"
    pf.write_bytes(Profile.default().to_ison().encode("utf-8"))
    return ["issue", g, bf, pl, *(["--profile", pf] if with_profile else []), "--igdc", out], {"graph": g, "binding": bf, "payload": pl, "profile": pf}


@pytest.mark.parametrize("which", ["graph", "binding", "payload", "profile"])
def test_issue_igdc_out_equal_to_an_input_is_refused_with_64_and_the_input_is_untouched(tmp_path, files, which):
    _, inputs = _issue_args(files, tmp_path, "unused")
    before = {k: v.read_bytes() for k, v in inputs.items()}
    args, _ = _issue_args(files, tmp_path, inputs[which])
    code, out, err = run(*args)
    assert code == 64 and out == b"" and which.encode() in err and b"refusing" in err
    assert {k: v.read_bytes() for k, v in inputs.items()} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["g.ison", "g.igx.ison", "g.igdm.ison", "p.profile.ison"])      # no temp file left behind


def test_issue_igdc_out_spelled_differently_is_still_the_input(tmp_path, files):
    g = files[0]
    before = g.read_bytes()
    code, out, err = run("issue", g, files[1], files[2], "--igdc", tmp_path / "." / "g.ison")
    assert code == 64 and out == b"" and g.read_bytes() == before
    code, out, err = run("issue", g, files[1], files[2], "--igdc", tmp_path / "sub" / ".." / "g.ison")
    assert code == 64 and out == b"" and g.read_bytes() == before


def test_issue_igdc_out_that_is_a_directory_is_refused_with_64(tmp_path, files):
    d = tmp_path / "outdir"
    d.mkdir()
    code, out, err = run("issue", *files, "--igdc", d)
    assert code == 64 and out == b"" and b"directory" in err and list(d.iterdir()) == []


def test_issue_igdc_still_overwrites_an_existing_unrelated_regular_file(tmp_path, files):
    hints = tmp_path / "old.igdc.ison"
    hints.write_bytes(b"stale")
    code, out, err = run("issue", *files, "--igdc", hints)
    assert code == 0 and err == b"" and hints.read_bytes() != b"stale" and _row(out, "subject")["igdc_sha256"] == sha(hints.read_bytes())


# ---- strict flags, pin-file shape ---------------------------------------------------------------------------------------------------
def test_the_root_parser_does_not_abbreviate_options():
    assert run("--help")[0] == 0
    code, out, err = run("--he")
    assert code == 64 and out == b"" and b"error:" in err


@pytest.mark.parametrize("flag, short", [("--profile", "--prof"), ("--igdc", "--igd"), ("--trust-policy", "--trust"), ("--pins", "--pin"), ("--target", "--tar")])
def test_abbreviated_options_are_usage_errors_in_every_subcommand_that_has_them(tmp_path, files, flag, short):
    rc, out, hints = _with_hints(tmp_path, files)
    g, bf, pl = files
    pf = tmp_path / "p.profile.ison"
    pf.write_bytes(Profile.default().to_ison().encode("utf-8"))
    auth = _auth_args(tmp_path, files, hints)
    pol = auth[auth.index("--trust-policy") + 1]
    pins = auth[auth.index("--pins") + 1]
    cases = {"issue": ["issue", g, bf, pl, "--profile", pf, "--igdc", tmp_path / "o.igdc.ison"],
             "subject": ["subject", rc, "--target", g, "--binding", bf, "--payload", pl, "--igdc", hints],
             "policy": ["policy", rc, "--trust-policy", pol], "authorize": auth, "recompute": ["recompute", rc, g, bf, pl, "--profile", pf]}
    tried = 0
    for cmd, args in cases.items():
        if flag not in args:
            continue
        assert run(*args)[0] != 64, (cmd, flag)                                              # the full spelling works ...
        short_args = [short if x == flag else x for x in args]
        code, o, err = run(*short_args)
        assert code == 64 and o == b"" and b"error:" in err, (cmd, short)                    # ... the abbreviation is a usage error
        tried += 1
    assert tried >= 1


def test_authorize_pin_file_path_qualified_name_never_matches(tmp_path, files):
    rc, out, hints = _with_hints(tmp_path, files)
    for name in ("sub/g.igar.ison", "./g.igar.ison", "sub\\g.igar.ison"):
        code, o, _ = run(*_auth_args(tmp_path, files, hints, pins_text=f"{sha(out)}  {name}\n"))
        assert code == 2 and _row(o, "error")["code"] == "RECEIPT_NOT_PINNED", name
    code, o, _ = run(*_auth_args(tmp_path, files, hints, pins_text=f"{sha(out).upper()}  g.igar.ison\n"))
    assert code == 1 and _row(o, "error")["code"] == "MALFORMED_PINS"                  # uppercase hex is not accepted either

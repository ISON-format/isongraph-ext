"""CLI hardening found by the 0.4.0 audit: undecodable arguments exit 64, input files are read within the byte budgets."""
import io
import pytest

from igp_helpers import graph_bytes, pol
from igpv_helpers import sha
from test_igpv_cli import T as TARGET
from test_igpv_cli import _files

from isongraph_ext import _cli
from isongraph_ext.igp import Limits
from isongraph_ext.igp import policy as P
from isongraph_ext.igp.__main__ import main as igp_main
from isongraph_ext.igpv.__main__ import main as igpv_main


def test_read_capped_returns_at_most_limit_plus_one_bytes(tmp_path):
    f = tmp_path / "f.bin"
    f.write_bytes(b"x" * 100)
    assert _cli.read_capped(f, 10) == b"x" * 11            # one byte past the budget is enough for the library to refuse it
    assert _cli.read_capped(f, 100) == b"x" * 100
    assert _cli.read_capped(f, 1000) == b"x" * 100


def test_read_capped_does_not_read_the_whole_file(tmp_path, monkeypatch):
    f = tmp_path / "f.bin"
    f.write_bytes(b"x" * 100)
    seen = []
    real_open = open

    def spying_open(path, mode="r", *a, **k):
        fh = real_open(path, mode, *a, **k)
        orig = fh.read
        fh.read = lambda n=-1: (seen.append(n), orig(n))[1]
        return fh

    monkeypatch.setattr(_cli, "open", spying_open, raising=False)
    _cli.read_capped(f, 10)
    assert seen == [11]


def test_igp_cli_refuses_an_oversized_source_without_reading_it_whole(tmp_path, monkeypatch, capsys):
    src = tmp_path / "s.ison"
    src.write_bytes(graph_bytes([("n", "a")], []))
    pol_file = tmp_path / "p.igp.ison"
    pol_file.write_text(P.to_ison(pol(("n", "a"))), encoding="utf-8", newline="")
    import isongraph_ext.igp.__main__ as m
    monkeypatch.setattr(m, "DEFAULT_LIMITS", Limits(max_source_bytes=5))
    seen = []
    real = _cli.read_capped
    monkeypatch.setattr(m, "read_capped", lambda p, n: (seen.append((p.name, n)), real(p, n))[1])
    code = igp_main(["project", str(src), str(pol_file), "--out", str(tmp_path / "out")])
    assert code == 1 and "PROJECTION_LIMIT_EXCEEDED" in capsys.readouterr().out
    assert ("s.ison", 5) in seen


def test_igpv_origins_with_an_undecodable_argument_exits_64_not_a_traceback(tmp_path, capsys):
    g, b, pl = _files(tmp_path)
    for extra in (["--node", "p", "\udc80"], ["--edge", "p", "1", "knows", "p", "\udc80"]):
        assert igpv_main(["origins", sha(TARGET), str(pl), *extra]) == 64
        assert "UTF-8" in capsys.readouterr().err


def test_write_atomic_replaces_whole_file_and_leaves_no_temp(tmp_path):
    from isongraph_ext._cli import write_atomic
    target = tmp_path / "out.ison"
    target.write_bytes(b"old")
    write_atomic(target, b"new")
    assert target.read_bytes() == b"new" and [p.name for p in tmp_path.iterdir()] == ["out.ison"]


def test_write_atomic_failure_keeps_the_old_file_and_cleans_up(tmp_path, monkeypatch):
    import os
    from isongraph_ext._cli import write_atomic
    target = tmp_path / "out.ison"
    target.write_bytes(b"old")
    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_atomic(target, b"new")
    assert target.read_bytes() == b"old" and [p.name for p in tmp_path.iterdir()] == ["out.ison"]

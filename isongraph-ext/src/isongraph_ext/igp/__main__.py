"""CLI (21 §5): project / verify -> 0, 1 (meta.error), 64 on usage. Output is one canonical ISON document."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical

from .._cli import read_capped, write_atomic
from ..igx.digest import sha256_hex
from .errors import IGPError
from .records import DEFAULT_LIMITS
from .project import project, verify_projection

EX_USAGE = 64


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        sys.stderr.write(f"error: {message}\n")
        raise SystemExit(EX_USAGE)


def _emit(block: Block) -> None:
    for stream in (sys.stdout,):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict", newline="\n")
    sys.stdout.write(dumps_canonical(Document(blocks=[block])) + "\n")


def _meta(name: str, row: dict) -> Block:
    return Block("meta", name, list(row), [row])


def main(argv: list[str]) -> int:
    ap = _Parser(prog="python -m isongraph_ext.igp")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pj = sub.add_parser("project")
    pj.add_argument("source", type=Path)
    pj.add_argument("policy", type=Path)
    pj.add_argument("--out", type=Path, required=True)
    vf = sub.add_parser("verify")
    for name in ("source", "policy", "result", "payload"):
        vf.add_argument(name, type=Path)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "project":
            source, policy = read_capped(a.source, DEFAULT_LIMITS.max_source_bytes), read_capped(a.policy, DEFAULT_LIMITS.max_policy_bytes)
        else:
            source, policy = read_capped(a.source, DEFAULT_LIMITS.max_source_bytes), read_capped(a.policy, DEFAULT_LIMITS.max_policy_bytes)
            result, payload = read_capped(a.result, DEFAULT_LIMITS.max_source_bytes), read_capped(a.payload, DEFAULT_LIMITS.lineage.max_payload_bytes)
    except OSError as e:
        sys.stderr.write(f"error: {e}\n")
        return EX_USAGE
    try:
        proj = (project(source, policy, limits=DEFAULT_LIMITS) if a.cmd == "project"
                else verify_projection(source, policy, result, payload, limits=DEFAULT_LIMITS))
    except IGPError as e:
        _emit(_meta("error", {"code": e.code, "field": e.field, "detail": e.detail, "step": e.step}))
        return 1
    payload_text = proj.payload.to_ison()
    if a.cmd == "project":
        try:
            a.out.mkdir(parents=True, exist_ok=True)
            write_atomic(a.out / "result.ison", proj.result_bytes)
            write_atomic(a.out / "result.igpv.ison", payload_text.encode("utf-8"))
        except OSError as e:
            sys.stderr.write(f"error: {e}\n")
            return EX_USAGE
    row = {"source_sha256": sha256_hex(source), "policy_sha256": proj.policy_sha256, "result_sha256": sha256_hex(proj.result_bytes),
           "payload_sha256": sha256_hex(payload_text.encode("utf-8"))}
    row.update({k: v for k, v in proj.stats.items()})
    _emit(_meta("projection", row))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

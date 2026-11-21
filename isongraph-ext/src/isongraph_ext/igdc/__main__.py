"""CLI (26): derive -> hint document on stdout; verify -> C0-C3 (C4 with the three inputs); exit 0 / 1 / 64 on usage.

Success output of `derive` is the hint document byte for byte (no added newline: the canonical document has none, and a saved
copy must pass C0). Every other response is one canonical ISON document followed by LF.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical

from .._cli import read_capped
from ..igdm.errors import IGDMError
from ..igdm.records import DEFAULT_LIMITS
from ..igx.binding import ExtensionBinding
from ..igx.errors import IGXError
from .derive import consume
from .errors import IGDCError
from .verify import verify_derivation, verify_hints

EX_USAGE = 64   # BSD sysexits: never collides with 1 (a refused input)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        sys.stderr.write(f"error: {message}\n")
        raise SystemExit(EX_USAGE)


def _utf8_streams() -> None:
    """Output is UTF-8, LF-terminated regardless of console locale or platform (same rule as the igx and igdm CLIs)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict", newline="\n")


def _meta(name: str, row: dict) -> Block:
    return Block("meta", name, list(row), [row])


def _emit(blocks: list[Block]) -> None:
    sys.stdout.write(dumps_canonical(Document(blocks=blocks)) + "\n")


def _usage(ap: argparse.ArgumentParser, message: str) -> int:
    ap.print_usage(sys.stderr)
    sys.stderr.write(f"error: {message}\n")
    return EX_USAGE


def main(argv: list[str]) -> int:
    _utf8_streams()
    ap = _Parser(prog="python -m isongraph_ext.igdc")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("derive")
    d.add_argument("graph", type=Path)
    d.add_argument("binding", type=Path)
    d.add_argument("payload", type=Path)
    v = sub.add_parser("verify")
    v.add_argument("hints", type=Path)
    v.add_argument("target", nargs="*", type=Path, metavar="graph binding payload")
    a = ap.parse_args(argv)
    if a.cmd == "verify" and len(a.target) not in (0, 3):
        return _usage(ap, "verify takes the hint document alone (C0-C3) or with graph, binding and payload (C0-C4)")
    limits = DEFAULT_LIMITS   # a binding has no budget of its own: it is read within the (larger) graph budget
    try:
        if a.cmd == "derive":
            graph, binding_bytes = read_capped(a.graph, limits.max_graph_bytes), read_capped(a.binding, limits.max_graph_bytes)
            payload = read_capped(a.payload, limits.max_payload_bytes)
        else:
            hints = read_capped(a.hints, limits.max_payload_bytes)
            if a.target:
                graph, binding_bytes = read_capped(a.target[0], limits.max_graph_bytes), read_capped(a.target[1], limits.max_graph_bytes)
                payload = read_capped(a.target[2], limits.max_payload_bytes)
    except OSError as e:
        return _usage(ap, str(e))
    try:
        if a.cmd == "derive":
            h = consume(payload, ExtensionBinding.from_ison(binding_bytes), graph, limits=limits)
            sys.stdout.write(h.to_ison())
            return 0
        if a.target:
            h = verify_derivation(hints, payload, ExtensionBinding.from_ison(binding_bytes), graph, limits=limits)
            steps = "C0,C1,C2,C3,C4"
        else:
            h = verify_hints(hints, limits=limits)
            steps = "C0,C1,C2,C3"
    except (IGDCError, IGDMError, IGXError) as e:
        _emit([_meta("error", {"code": e.code, "field": e.field, "detail": e.detail, "step": e.step})])
        return 1
    # well-formed is not verified: a document that passed C0-C3 only has `derivation_checked` false
    _emit([_meta("verification", {"consumption_spec": h.meta["consumption_spec"], "hints_sha256": h.digest,
                                  "steps_passed": steps, "derivation_checked": bool(a.target)})])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

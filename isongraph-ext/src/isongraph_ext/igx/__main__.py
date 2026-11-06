"""CLI (17 §3): verify -> 0/1, admit -> 0/2 (1 on invalid), 64 on usage. Output is ISON so receipts can quote it verbatim."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical

from .admit import AdmissionPolicy, admit
from .binding import ExtensionBinding
from .errors import IGXError
from .verify import verify

EX_USAGE = 64   # BSD sysexits: never collides with 2 (admission denied) or 1 (invalid binding)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        sys.stderr.write(f"error: {message}\n")
        raise SystemExit(EX_USAGE)


def _emit(name: str, row: dict) -> None:
    sys.stdout.write(dumps_canonical(Document(blocks=[Block("meta", name, list(row), [row])])) + "\n")


def _error(e: IGXError) -> int:
    _emit("error", {"code": e.code, "field": e.field, "detail": e.detail, "step": e.step})
    return 1


def _joined(items) -> str | None:
    items = list(items)
    return ",".join(items) if items else None


def main(argv: list[str]) -> int:
    ap = _Parser(prog="python -m isongraph_ext.igx")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("verify", "admit"):
        p = sub.add_parser(name)
        p.add_argument("graph", type=Path)
        p.add_argument("binding", type=Path)
        if name == "admit":
            p.add_argument("--allow-retired", action="store_true")
    a = ap.parse_args(argv)
    try:
        source = a.graph.read_bytes()
        binding_bytes = a.binding.read_bytes()
    except OSError as e:
        sys.stderr.write(f"error: {e}\n")
        return EX_USAGE
    try:
        binding = ExtensionBinding.from_ison(binding_bytes)
        result = verify(binding, source)
    except IGXError as e:
        return _error(e)
    if a.cmd == "verify":
        _emit("verification", {
            "binding_digest": result.binding_digest, "semantic_verification": result.semantic_verification,
            "source_canonical": result.source_canonical,
            "source_semantic_eligibility": result.source_semantic_eligibility, "source_semantic_reason": result.source_semantic_reason,
            "steps_passed": _joined(result.steps_passed),
            "unrecognized_optional": _joined(c.extension for c in result.unrecognized_optional)})
        return 0
    decision = admit(binding, result, policy=AdmissionPolicy(allow_retired_baselines=a.allow_retired))
    _emit("admission", {"admitted": decision.admitted, "code": decision.code, "step": decision.step,
                        "receipt_posture": decision.receipt_posture, "reasons": _joined(decision.reasons)})
    return 0 if decision.admitted else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

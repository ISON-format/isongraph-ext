"""CLI (19 §4): verify -> 0/1/2, 64 on usage; one canonical ISON document per response."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical

from .._cli import read_capped
from ..igx.admit import AdmissionPolicy
from ..igx.binding import ExtensionBinding
from ..igx.errors import IGXError
from .bind import verify_and_admit
from .errors import IGDMError
from .records import DEFAULT_LIMITS

EX_USAGE = 64   # BSD sysexits: never collides with 2 (admission denied) or 1 (invalid binding/payload)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        sys.stderr.write(f"error: {message}\n")
        raise SystemExit(EX_USAGE)


def _utf8_streams() -> None:
    """Output is UTF-8, LF-terminated ISON regardless of console locale or platform (same rule as the igx CLI)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict", newline="\n")


def _meta(name: str, row: dict) -> Block:
    return Block("meta", name, list(row), [row])


def _emit(blocks: list[Block]) -> None:
    sys.stdout.write(dumps_canonical(Document(blocks=blocks)) + "\n")


def _joined(items) -> str | None:
    items = list(items)
    return ",".join(items) if items else None


def _kv(m: Mapping) -> str | None:
    return _joined(f"{k}={v}" for k, v in m.items())


def main(argv: list[str]) -> int:
    _utf8_streams()
    ap = _Parser(prog="python -m isongraph_ext.igdm")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("graph", type=Path)
    v.add_argument("binding", type=Path)
    v.add_argument("payload", type=Path)
    v.add_argument("--allow-retired", action="store_true")
    a = ap.parse_args(argv)
    try:
        graph, binding_bytes = read_capped(a.graph, DEFAULT_LIMITS.max_graph_bytes), a.binding.read_bytes()
        payload_bytes = read_capped(a.payload, DEFAULT_LIMITS.max_payload_bytes)
    except OSError as e:
        ap.print_usage(sys.stderr)
        sys.stderr.write(f"error: {e}\n")
        return EX_USAGE
    try:
        binding = ExtensionBinding.from_ison(binding_bytes)
        result, dm, decision = verify_and_admit(payload_bytes, binding, graph, policy=AdmissionPolicy(allow_retired_baselines=a.allow_retired))
    except (IGXError, IGDMError) as e:
        _emit([_meta("error", {"code": e.code, "field": e.field, "detail": e.detail, "step": e.step})])
        return 1
    _emit([
        _meta("verification", {
            "binding_digest": result.binding_digest, "semantic_verification": result.semantic_verification,
            "source_canonical": result.source_canonical, "source_semantic_eligibility": result.source_semantic_eligibility,
            "source_semantic_reason": result.source_semantic_reason, "steps_passed": _joined(result.steps_passed),
            "unrecognized_optional": _joined(c.extension for c in result.unrecognized_optional)}),
        _meta("datamatics", {
            "payload_sha256": dm.payload_sha256, "binding_digest": dm.binding_digest, "target_artifact_sha256": dm.target_artifact_sha256,
            "object_resolution": dm.object_resolution, "unrecognized_roles": _joined(dm.unrecognized_roles),
            "counts": _kv(dm.counts), "steps_passed": _joined(dm.steps_passed)}),
        _meta("admission", {"admitted": decision.admitted, "code": decision.code, "step": decision.step,
                            "receipt_posture": decision.receipt_posture, "reasons": _joined(decision.reasons)}),
    ])
    return 0 if decision.admitted else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

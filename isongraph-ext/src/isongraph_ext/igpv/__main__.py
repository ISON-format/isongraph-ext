"""CLI (18 §5.3): verify -> 0/1/2, origins -> 0/1, 64 on usage. Output is ISON so receipts can quote it verbatim."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical

from ..igx.admit import AdmissionPolicy
from ..igx.binding import ExtensionBinding
from ..igx.errors import IGXError
from .._cli import read_capped
from . import records as R
from .records import DEFAULT_LIMITS
from .bind import verify_and_admit
from .errors import IGPVError
from .lineage import Lineage
from .payload import ProvenancePayload

EX_USAGE = 64   # BSD sysexits: never collides with 2 (admission denied) or 1 (invalid binding/payload)
# `id` is the zero-padded DFS preorder index: the canonical writer hoists `id` first and sorts rows by it, so the printed
# table keeps the resolver's order (the writer would otherwise reorder rows by depth, digest, kind, ...).
LINEAGE_FIELDS = ("id", "depth", "graph_sha256", "object_kind", "node_type", "node_id", "source_type", "source_id", "relation",
                  "target_type", "target_id", "ordinal", "derivation_kind", "producer_implementation", "producer_version", "terminal")
_DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)")


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
    """One response = one canonical ISON document, written once (block separation and order are the writer's)."""
    sys.stdout.write(dumps_canonical(Document(blocks=blocks)) + "\n")


def _error(e: IGXError | IGPVError) -> int:
    _emit([_meta("error", {"code": e.code, "field": e.field, "detail": e.detail, "step": e.step})])
    return 1


def _joined(items) -> str | None:
    items = list(items)
    return ",".join(items) if items else None


def _kv(m: Mapping) -> str | None:
    return _joined(f"{k}={v}" for k, v in m.items())


def _usage(ap: _Parser, message: str) -> int:
    ap.print_usage(sys.stderr)
    sys.stderr.write(f"error: {message}\n")
    return EX_USAGE


def _id_token(s: str) -> int | str:
    """`1` is INT64, `"1"` is STRING, anything else is a STRING as typed (shell quoting is the caller's)."""
    if _DECIMAL.fullmatch(s):
        v = int(s)
        if not (R.INT64_MIN <= v <= R.INT64_MAX):
            raise ValueError(f"integer id outside INT64: {s}")
        return v
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return s[1:-1]
    return s


def _address_row(obj) -> dict:
    row: dict = {k: None for k in LINEAGE_FIELDS}
    if obj is None:
        row["object_kind"] = "graph"
    elif isinstance(obj, R.NodeRef):
        row.update({"object_kind": "node", "node_type": obj.node_type, "node_id": obj.node_id})
    else:
        row.update({"object_kind": "edge", "source_type": obj.source.node_type, "source_id": obj.source.node_id, "relation": obj.relation,
                    "target_type": obj.target.node_type, "target_id": obj.target.node_id, "ordinal": obj.ordinal})
    return row


def main(argv: list[str]) -> int:
    _utf8_streams()
    ap = _Parser(prog="python -m isongraph_ext.igpv")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("graph", type=Path)
    v.add_argument("binding", type=Path)
    v.add_argument("payload", type=Path)
    v.add_argument("--source", action="append", default=[], metavar="SHA256=PATH")
    v.add_argument("--allow-retired", action="store_true")
    o = sub.add_parser("origins")
    o.add_argument("graph_sha256")
    o.add_argument("payloads", nargs="+", type=Path)
    o.add_argument("--node", nargs=2, metavar=("TYPE", "ID"))
    o.add_argument("--edge", nargs="+", metavar="PART")
    a = ap.parse_args(argv)
    if a.cmd == "verify":
        return _verify(ap, a)
    return _origins(ap, a)


def _verify(ap: _Parser, a) -> int:
    sources: dict[str, bytes] = {}
    try:
        graph, binding_bytes = read_capped(a.graph, DEFAULT_LIMITS.max_graph_bytes), a.binding.read_bytes()
        payload_bytes = read_capped(a.payload, DEFAULT_LIMITS.max_payload_bytes)
        for item in a.source:
            key, sep, path = item.partition("=")
            if not sep or R.HEX64.fullmatch(key) is None:
                return _usage(ap, f"--source needs SHA256=PATH with lowercase hex: {item!r}")
            sources[key] = read_capped(Path(path), DEFAULT_LIMITS.max_graph_bytes)
    except OSError as e:
        return _usage(ap, str(e))
    try:
        binding = ExtensionBinding.from_ison(binding_bytes)
        result, prov, decision = verify_and_admit(payload_bytes, binding, graph, sources=sources,
                                                  policy=AdmissionPolicy(allow_retired_baselines=a.allow_retired))
    except (IGXError, IGPVError) as e:
        return _error(e)
    _emit([
        _meta("verification", {
            "binding_digest": result.binding_digest, "semantic_verification": result.semantic_verification,
            "source_canonical": result.source_canonical, "source_semantic_eligibility": result.source_semantic_eligibility,
            "source_semantic_reason": result.source_semantic_reason, "steps_passed": _joined(result.steps_passed),
            "unrecognized_optional": _joined(c.extension for c in result.unrecognized_optional)}),
        _meta("provenance", {
            "payload_sha256": prov.payload_sha256, "binding_digest": prov.binding_digest, "target_artifact_sha256": prov.target_artifact_sha256,
            "object_resolution": prov.object_resolution, "origin_resolution": _kv(prov.origin_resolution), "locators": _kv(prov.locators),
            "counts": _kv(prov.counts), "steps_passed": _joined(prov.steps_passed)}),
        _meta("admission", {"admitted": decision.admitted, "code": decision.code, "step": decision.step,
                            "receipt_posture": decision.receipt_posture, "reasons": _joined(decision.reasons)}),
    ])
    return 0 if decision.admitted else 2


def _origins(ap: _Parser, a) -> int:
    if R.HEX64.fullmatch(a.graph_sha256) is None:
        return _usage(ap, "graph_sha256 must be 64 lowercase hex")
    if a.node and a.edge:
        return _usage(ap, "--node and --edge are exclusive")
    try:
        for part in (a.node or []) + (a.edge or []):
            try:
                part.encode("utf-8")
            except UnicodeEncodeError:
                return _usage(ap, "arguments must be valid UTF-8 text")
        if a.node:
            obj = R.NodeRef(a.node[0], _id_token(a.node[1]))
        elif a.edge:
            if len(a.edge) not in (5, 6):
                return _usage(ap, "--edge needs STYPE SID REL TTYPE TID [ORDINAL]")
            st, sid, rel, tt, tid = a.edge[:5]
            obj = R.EdgeAddress(R.NodeRef(st, _id_token(sid)), rel, R.NodeRef(tt, _id_token(tid)), a.edge[5] if len(a.edge) == 6 else "0")
        else:
            obj = None
        texts = [read_capped(p, DEFAULT_LIMITS.max_payload_bytes) for p in a.payloads]
    except (OSError, ValueError) as e:
        return _usage(ap, str(e))
    try:
        steps = Lineage([ProvenancePayload.from_ison(t) for t in texts]).origins_of(a.graph_sha256, obj)
    except IGPVError as e:
        return _error(e)
    rows = []
    for i, s in enumerate(steps):
        row = _address_row(s.obj)
        row.update({"id": f"{i:07d}", "depth": s.depth, "graph_sha256": s.graph_sha256, "derivation_kind": s.kind, "terminal": s.terminal,
                    "producer_implementation": None if s.producer is None else s.producer.implementation,
                    "producer_version": None if s.producer is None else s.producer.version})
        rows.append(row)
    _emit([Block("table", "lineage", list(LINEAGE_FIELDS), rows)])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

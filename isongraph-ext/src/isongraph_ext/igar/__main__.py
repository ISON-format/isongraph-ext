"""CLI (25 §5): issue | inspect | subject | policy | authorize | recompute. Exit 0 / 1 / 2 / 64 on usage.

`issue` prints the receipt byte for byte (no added newline: the canonical document has none, and a saved copy must pass R0). Every other
response is one canonical ISON document followed by LF. Only a successful `authorize` ever says a receipt was authorized, and then it names
the exact digests it admitted; `inspect`, `subject`, `policy` and `recompute` each state only the narrow thing they checked.

Exit 2 means "refused": the input was well-formed but did not earn what was asked (policy, pin, bytes, or a re-run that cannot be made).
Exit 1 means the input itself is malformed or over budget. A rejection receipt is content, so `issue` exits 0 for it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ison_parser import Block, Document, dumps_canonical

from .._cli import read_capped, write_atomic
from ..igdc.derive import consume
from ..igdm.records import DEFAULT_LIMITS, Limits
from ..igx.binding import ExtensionBinding
from ..igx.digest import sha256_hex
from .check import check_subject, inspect_receipt, recompute
from .errors import IGARError
from .issue import issue
from .profile import Profile
from .trust import DeliveryPins, TrustPolicy, authorize_hints, qualify_policy

EX_USAGE = 64   # BSD sysexits: never collides with 1 (malformed input) or 2 (refused)
REFUSED = frozenset({"RECEIPT_POLICY_UNSATISFIED", "RECEIPT_NOT_PINNED", "RECEIPT_SUBJECT_MISMATCH", "RECOMPUTE_UNAVAILABLE"})


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        sys.stderr.write(f"error: {message}\n")
        raise SystemExit(EX_USAGE)


def _utf8_streams() -> None:
    """Output is UTF-8, LF-terminated regardless of console locale or platform (same rule as the igx, igdm and igdc CLIs)."""
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


def _exact(path: Path, budget: int, what: str) -> bytes:
    """A file whose BYTES are hashed or re-verified: read at most budget + 1, and refuse an over-budget file instead of using the truncated prefix
    (a receipt about the first budget + 1 bytes of a file would be a receipt about bytes that do not exist)."""
    data = read_capped(path, budget)
    if len(data) > budget:
        raise IGARError("RECEIPT_LIMIT_EXCEEDED", what, f"input is larger than the {budget}-byte budget", "R0")
    return data


def _wider(profile_bytes: bytes | None, base: Limits) -> Limits:
    """Read budgets for inputs a profile governs: the larger of the default budget and the profile's own, so a file that is over only the PROFILE's
    limit still reaches the verifier and becomes a rejection receipt, while a file over both is refused here. A profile that does not parse changes nothing."""
    if profile_bytes is None:
        return base
    try:
        lim = Profile.from_ison(profile_bytes).limits
    except IGARError:
        return base
    return Limits(max_payload_bytes=max(base.max_payload_bytes, lim.max_payload_bytes), max_graph_bytes=max(base.max_graph_bytes, lim.max_graph_bytes))


def _pins(text: bytes, name: str, limits: Limits) -> DeliveryPins:
    """Pin ONLY the receipt file named on the command line (its final path component). A pin file that is well formed but does not list it pins nothing."""
    try:
        return DeliveryPins.from_sha256sums(text, names=frozenset({name}), limits=limits)
    except IGARError as e:
        if e.code != "MALFORMED_PINS":
            raise
        DeliveryPins.from_sha256sums(text, names=frozenset(), limits=limits)     # still malformed on its own: that error stands (exit 1)
        raise IGARError("RECEIPT_NOT_PINNED", "receipt", f"the pin file does not list {name!r}", "R5") from None


def _build() -> argparse.ArgumentParser:
    ap = _Parser(prog="python -m isongraph_ext.igar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("issue")
    i.add_argument("graph", type=Path)
    i.add_argument("binding", type=Path)
    i.add_argument("payload", type=Path)
    i.add_argument("--profile", type=Path)
    i.add_argument("--igdc", type=Path, metavar="OUT")
    sub.add_parser("inspect").add_argument("receipt", type=Path)
    s = sub.add_parser("subject")
    s.add_argument("receipt", type=Path)
    for f in ("target", "binding", "payload"):
        s.add_argument(f"--{f}", type=Path, required=True)
    s.add_argument("--igdc", type=Path)
    p = sub.add_parser("policy")
    p.add_argument("receipt", type=Path)
    p.add_argument("--trust-policy", type=Path, required=True)
    a = sub.add_parser("authorize")
    a.add_argument("receipt", type=Path)
    for f in ("pins", "target", "binding", "payload", "igdc", "trust-policy"):
        a.add_argument(f"--{f}", type=Path, required=True)
    r = sub.add_parser("recompute")
    for f in ("receipt", "graph", "binding", "payload"):
        r.add_argument(f, type=Path)
    r.add_argument("--profile", type=Path, required=True)
    return ap


def _run(a: argparse.Namespace, limits: Limits) -> list[Block] | str:
    """The response: a list of blocks (one canonical document), or the receipt text for `issue`."""
    pay, gra = limits.max_payload_bytes, limits.max_graph_bytes
    if a.cmd == "issue":
        profile_bytes = read_capped(a.profile, pay) if a.profile else None
        prof = Profile.from_ison(profile_bytes, max_bytes=pay) if profile_bytes is not None else None
        wide = _wider(profile_bytes, limits)
        graph, binding = _exact(a.graph, wide.max_graph_bytes, "graph"), _exact(a.binding, wide.max_graph_bytes, "binding")
        payload = _exact(a.payload, wide.max_payload_bytes, "payload")
        r = issue(binding, payload, graph, igdc=a.igdc is not None, profile=prof)
        if a.igdc is not None and r.subject["igdc_sha256"] is not None:
            use = prof or Profile.default()
            hints = consume(payload, ExtensionBinding.from_ison(binding), graph, limits=use.limits, baselines=use.baselines, registry=use.registry)
            if hints.digest != r.subject["igdc_sha256"]:
                raise RuntimeError("the hint document re-derived for --igdc differs from the one the receipt names")
            write_atomic(a.igdc, hints.to_ison().encode("utf-8"))
        return r.to_ison()
    receipt = read_capped(a.receipt, pay)                      # the library refuses it by its own budget; the receipt is never hashed by a prefix
    if a.cmd == "inspect":
        r = inspect_receipt(receipt, limits=limits)
        return [_meta("inspection", {
            "receipt_sha256": sha256_hex(receipt), "steps_passed": "R0,R1,R2", "claimed_verification": r.result["verification"],
            "claimed_admission": r.result["admission"], "claimed_consumption": r.result["consumption"], "profile_sha256": r.verifier["profile_sha256"],
            "scope": "well-formed and self-consistent claim only; not matched to any bytes, delivery or policy"})]
    if a.cmd == "subject":
        r = inspect_receipt(receipt, limits=limits)
        hints = _exact(a.igdc, pay, "igdc") if a.igdc else None
        check_subject(r, target=_exact(a.target, gra, "target"), binding=_exact(a.binding, gra, "binding"), payload=_exact(a.payload, pay, "payload"), igdc=hints)
        return [_meta("subject_check", {
            "receipt_sha256": sha256_hex(receipt), "steps_passed": "R0,R1,R2,R3", "igdc_checked": hints is not None,
            "scope": "the receipt names exactly these bytes; this says nothing about who produced it or how it was delivered"})]
    if a.cmd == "policy":
        r = inspect_receipt(receipt, limits=limits)
        qualify_policy(r, TrustPolicy.from_ison(read_capped(a.trust_policy, pay), limits=limits))
        return [_meta("policy_check", {
            "receipt_sha256": sha256_hex(receipt), "steps_passed": "R0,R1,R2,R4", "policy_satisfied": True, "authorized": False,
            "note": "policy match only; not an authorization and says nothing about provenance"})]
    if a.cmd == "authorize":
        pins = _pins(read_capped(a.pins, pay), a.receipt.name, limits)
        policy = TrustPolicy.from_ison(read_capped(a.trust_policy, pay), limits=limits)
        t = authorize_hints(receipt, pins=pins, target=_exact(a.target, gra, "target"), binding=_exact(a.binding, gra, "binding"),
                            payload=_exact(a.payload, pay, "payload"), igdc=_exact(a.igdc, pay, "igdc"), policy=policy, limits=limits)
        return [_meta("authorization", {
            "authorized": True, "receipt_sha256": t.receipt_sha256, "target_artifact_sha256": t.target_artifact_sha256, "binding_sha256": t.binding_sha256,
            "igdm_payload_sha256": t.igdm_payload_sha256, "igdc_sha256": t.igdc_sha256, "profile_sha256": t.profile_sha256, "verifier": t.verifier,
            "verifier_version": t.verifier_version, "core_commit": t.core_commit,
            "note": "pinned, bound to these bytes, policy-fit and passed; no signature, freshness or authorship is checked"})]
    profile = read_capped(a.profile, pay)                       # recompute: the profile is the one the receipt names, never defaulted
    wide = _wider(profile, limits)
    recompute(receipt, _exact(a.binding, wide.max_graph_bytes, "binding"), _exact(a.payload, wide.max_payload_bytes, "payload"),
              _exact(a.graph, wide.max_graph_bytes, "graph"), profile=profile)
    return [_meta("recomputation", {
        "receipt_sha256": sha256_hex(receipt), "steps_passed": "R0,R1,R2,R6", "reproduced": True,
        "scope": "a Python verifier under the named profile reproduces this receipt byte for byte; nothing about delivery or provenance"})]


def main(argv: list[str]) -> int:
    _utf8_streams()
    ap = _build()
    a = ap.parse_args(argv)
    limits = DEFAULT_LIMITS     # one limits object for reading and for the library (as the igp CLI)
    try:
        out = _run(a, limits)
    except OSError as e:
        return _usage(ap, str(e))
    except IGARError as e:
        _emit([_meta("error", {"code": e.code, "field": e.field, "detail": e.detail, "step": e.step})])
        return 2 if e.code in REFUSED else 1
    if isinstance(out, str):
        sys.stdout.write(out)
    else:
        _emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

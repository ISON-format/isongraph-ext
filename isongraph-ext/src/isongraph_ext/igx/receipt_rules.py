"""Core Conformance Receipt content rules (17 §6), dependency-free so the baseline generator can use them
before any baseline exists. Mirrors Core's scripts/corpus_receipt.py posture() at ce9d3b7."""

from __future__ import annotations

POSTURES = ("FULL", "LOSSY_KNOWN", "KNOWN_DEFECT", "PARTIAL", "INCONCLUSIVE", "NONCONFORMANT")
COUNTERS = ("pass", "canonicalized", "lossy", "defect", "rejected_as_expected", "todo")


class ReceiptContentError(ValueError):
    """A hash-valid receipt that is internally inconsistent."""


def validate_receipt_row(where: str, port: str, r: dict) -> None:
    if r.get("port") != port:
        raise ReceiptContentError(f"{where}: port {r.get('port')!r} != expected {port!r}")
    if r.get("posture") not in POSTURES:
        raise ReceiptContentError(f"{where}: posture {r.get('posture')!r}")
    counts = {k: r.get(k) for k in COUNTERS + ("total",)}
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in counts.values()):
        raise ReceiptContentError(f"{where}: counters must be non-negative integers: {counts}")
    if sum(counts[k] for k in COUNTERS) != counts["total"]:
        raise ReceiptContentError(f"{where}: counters do not sum to total: {counts}")
    p, todo, lossy, defect, total = r["posture"], counts["todo"], counts["lossy"], counts["defect"], counts["total"]
    ok = {
        "FULL": todo == 0 and lossy == 0 and defect == 0,
        "LOSSY_KNOWN": todo == 0 and defect == 0 and lossy > 0,
        "KNOWN_DEFECT": todo == 0 and defect > 0,
        "PARTIAL": todo == total,
        "INCONCLUSIVE": todo > 0,
        "NONCONFORMANT": True,
    }[p]
    if not ok:
        raise ReceiptContentError(f"{where}: posture {p} inconsistent with counters {counts}")

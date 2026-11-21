# isongraph-ext/src/isongraph_ext/igdc/verify.py   (C4 is added in Task 5)
"""IGDC/1 verification of a hint document: C0-C3 need no target and no Core; C4 re-derives (Python reference only)."""
from __future__ import annotations

from ..igdm import records as R
from .errors import IGDCError
from .hints import HintSet


def verify_hints(data: bytes | str, *, limits: R.Limits = R.DEFAULT_LIMITS) -> HintSet:
    """C0-C3. A document that passes is well-formed, NOT verified: C4 or a trusted IGAR/1 receipt ties it to a verified payload."""
    h = HintSet.from_ison(data, limits=limits)
    h.check(limits=limits)
    return h

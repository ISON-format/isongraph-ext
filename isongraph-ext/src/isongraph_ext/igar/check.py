# isongraph-ext/src/isongraph_ext/igar/check.py
"""The receipt operations that need no trust decision (25 §3, §4): inspect (R0-R2), subject (R3), recompute (R6, Python only).

Nothing here says a receipt is TRUSTED. `inspect_receipt` says it is well-formed and consistent; `check_subject` says it is about
exactly these bytes; `recompute` says a Python verifier reproduces it. Authorizing use of hints is `trust.authorize_hints`.
"""
from __future__ import annotations

from importlib import metadata

from .. import __version__
from ..igdm.records import DEFAULT_LIMITS, Limits
from ..igx.digest import sha256_hex
from .errors import IGARError
from .issue import issue
from .profile import Profile
from .receipt import Receipt


def inspect_receipt(data: bytes | str, *, limits: Limits = DEFAULT_LIMITS) -> Receipt:
    """R0 (bytes, budget, canonical form), R1 (shape), R2 (consistency). Needs no target, no binding, no payload, no policy.

    A receipt that passes is a well-formed, self-consistent CLAIM. It is not evidence that the claim is true or that anyone
    trustworthy made it.
    """
    r = Receipt.from_ison(data, limits=limits)
    r.check_consistency()
    return r


def _digest_of(name: str, data: object) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"{name} must be bytes, got {type(data).__name__}")
    return sha256_hex(bytes(data))


def check_subject(receipt: Receipt, *, target: bytes, binding: bytes, payload: bytes, igdc: bytes | None) -> None:
    """R3: the receipt is about EXACTLY these bytes. Every input is a required keyword: an omitted one is a TypeError, never a skipped check.

    `igdc` is `None` only for "I hold no hint document"; then the receipt must name none either. A receipt that names a hint
    document the caller did not supply, or a caller who supplies one the receipt does not name, is a mismatch in both directions.
    """
    if type(receipt) is not Receipt:
        raise TypeError(f"receipt must be Receipt, got {type(receipt).__name__}")
    for name, data in (("target", target), ("binding", binding), ("payload", payload)):      # every input is type-checked before any comparison
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError(f"{name} must be bytes, got {type(data).__name__}")
    if igdc is not None and not isinstance(igdc, (bytes, bytearray)):
        raise TypeError(f"igdc must be bytes or None, got {type(igdc).__name__}")
    s = receipt.subject
    for field, name, data in (("target_artifact_sha256", "target", target), ("binding_sha256", "binding", binding), ("igdm_payload_sha256", "payload", payload)):
        if _digest_of(name, data) != s[field]:
            raise IGARError("RECEIPT_SUBJECT_MISMATCH", f"meta.subject.{field}", f"the receipt is not about the {name} bytes supplied", "R3")
    if igdc is None:
        if s["igdc_sha256"] is not None:
            raise IGARError("RECEIPT_SUBJECT_MISMATCH", "meta.subject.igdc_sha256", "the receipt names a hint document the caller did not supply", "R3")
    elif s["igdc_sha256"] is None or _digest_of("igdc", igdc) != s["igdc_sha256"]:
        raise IGARError("RECEIPT_SUBJECT_MISMATCH", "meta.subject.igdc_sha256", "the receipt does not name the hint document supplied", "R3")


def _unavailable(field: str, detail: str) -> IGARError:
    return IGARError("RECOMPUTE_UNAVAILABLE", field, detail, "R6")


def recompute(receipt: bytes | str, binding: bytes, payload: bytes, target: bytes, *, profile: bytes | None, verifier_version: str | None = None) -> None:
    """R6 (Python reference only): re-run the verification path under the profile the receipt NAMES and require identical bytes.

    A receipt that cannot be re-run here (profile not supplied, profile differs, other verifier version, other runtime) raises
    `RECOMPUTE_UNAVAILABLE`: that says nothing against the receipt. Only `RECEIPT_RECOMPUTE_MISMATCH`, raised after every
    precondition holds, says the receipt is not what the verifier computes. The profile is never defaulted from the installed package.
    """
    r = inspect_receipt(receipt)
    v = r.verifier
    if profile is None:
        raise _unavailable("profile", f"the receipt was issued under profile {v['profile_sha256']}; supply that profile document")
    if _digest_of("profile", profile) != v["profile_sha256"]:
        raise _unavailable("meta.verifier.profile_sha256", "the supplied profile is not the one the receipt names")
    if v["verifier_version"] != (verifier_version or __version__):
        raise _unavailable("meta.verifier.verifier_version", f"issued by isongraph-ext {v['verifier_version']}; this is {verifier_version or __version__}")
    for field, dist in (("runtime_ison_graph", "ison-graph"), ("runtime_ison_py", "ison-py")):
        if v[field] != metadata.version(dist):
            raise _unavailable(f"meta.verifier.{field}", f"issued under {dist} {v[field]}; installed {metadata.version(dist)}")
    prof = Profile.from_ison(profile)       # only now: a profile this reader refuses cannot make a receipt from another verifier or runtime anything but unavailable
    again = issue(binding, payload, target, igdc=(r.subject["igdc_sha256"] is not None or r.consumption["code"] is not None), profile=prof,
                  verifier_version=v["verifier_version"])
    if again.to_ison() != r.to_ison():
        raise IGARError("RECEIPT_RECOMPUTE_MISMATCH", "document", "re-running the verification path under the named profile does not reproduce this receipt", "R6")

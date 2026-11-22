# isongraph-ext/src/isongraph_ext/igar/trust.py
"""Policy qualification (R4), delivery pins (R5) and the ONE operation that authorizes use of hints (25 §4).

Vocabulary, kept apart on purpose:
  well-formed  R0-R2   `check.inspect_receipt`   the receipt is a consistent claim
  bound        R3      `check.check_subject`     the claim is about exactly these bytes
  policy-fit   R4      `qualify_policy`          the claimed verifier / profile / baseline / posture is acceptable - says NOTHING about provenance
  pinned       R5      `DeliveryPins`            these receipt bytes came through the consumer's controlled, digest-pinned channel
  authorized   all     `authorize_hints`         pinned AND bound AND policy-fit AND passed, together, for the hints actually held
A rejection receipt can be well-formed, bound and pinned - delivered evidence of a rejection - and can never be authorized.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..igdm.records import DEFAULT_LIMITS, Limits
from ..igx.digest import sha256_hex
from ..strict_ison import BlockShape, StrictError, read_canonical
from .check import check_subject, inspect_receipt
from .errors import IGARError
from .receipt import Receipt, passed

POLICY_SPEC = "IGAR-POLICY/1"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX40 = re.compile(r"[0-9a-f]{40}")
_SEPARATORS = re.compile("[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")     # str.splitlines separators other than CR / LF


def _need(v: object, cls: type, name: str) -> None:
    """Trust inputs are checked by exact type: a duck-typed or None stand-in must never reach a membership test."""
    if not isinstance(v, cls):
        raise TypeError(f"{name} must be {cls.__name__}, got {type(v).__name__}")


def _frozen(name: str, v: object) -> frozenset:
    """An owned immutable copy. A bare string would give substring membership, so it is refused rather than iterated."""
    if isinstance(v, (str, bytes, bytearray)) or not hasattr(v, "__iter__"):
        raise TypeError(f"{name} must be a collection, got {type(v).__name__}")
    return frozenset(v)  # type: ignore[call-overload]
POLICY_SHAPES = (BlockShape("meta", "policy", ("policy_spec", "require_admission", "require_full_resolution"), True),
                 BlockShape("table", "verifiers", ("verifier", "verifier_version")), BlockShape("table", "core_commits", ("core_commit",)),
                 BlockShape("table", "profiles", ("profile_sha256",)), BlockShape("table", "runtime", ("runtime_ison_graph", "runtime_ison_py")))


@dataclass(frozen=True)
class TrustPolicy:
    verifiers: frozenset[tuple[str, str]]       # accepted (verifier, verifier_version); empty accepts none
    core_commits: frozenset[str]                # accepted baseline core_commit values; empty accepts none
    profiles: frozenset[str]                    # accepted verifier-profile digests (25 §2.4); empty accepts none
    runtime: frozenset[tuple[str, str]] = frozenset()   # accepted (runtime_ison_graph, runtime_ison_py); empty = do not constrain
    require_admission: bool = True
    require_full_resolution: bool = True

    def __post_init__(self) -> None:
        """Own immutable copies of every collection (a caller's live set cannot change the policy) and validate element shapes."""
        for name, arity in (("verifiers", 2), ("runtime", 2), ("core_commits", 1), ("profiles", 1)):
            items = _frozen(name, getattr(self, name))
            for x in items:
                cells = x if arity == 2 else (x,)
                if (arity == 2 and not (isinstance(x, tuple) and len(x) == 2)) or not all(isinstance(c, str) and c for c in cells):
                    raise IGARError("MALFORMED_POLICY", f"table.{name}", "non-empty strings" + (" in 2-tuples" if arity == 2 else ""), "R4")
            if name == "core_commits" and not all(_HEX40.fullmatch(c) for c in items):
                raise IGARError("MALFORMED_POLICY", "table.core_commits", "core_commit is 40 lowercase hex", "R4")
            if name == "profiles" and not all(_HEX64.fullmatch(p) for p in items):
                raise IGARError("MALFORMED_POLICY", "table.profiles", "profile_sha256 is 64 lowercase hex", "R4")
            object.__setattr__(self, name, items)
        for name in ("require_admission", "require_full_resolution"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool, got {type(getattr(self, name)).__name__}")

    @classmethod
    def from_ison(cls, data: bytes | str, *, limits: Limits = DEFAULT_LIMITS) -> "TrustPolicy":
        """The policy file (docs/igar-policy-format.md). Canonical ISON, byte budget first; an empty table accepts nothing."""
        _need(limits, Limits, "limits")

        def bad(field_: str, detail: str) -> IGARError:
            return IGARError("MALFORMED_POLICY", field_, detail, "R4")
        try:
            _text, b = read_canonical(data, POLICY_SHAPES, max_bytes=limits.max_payload_bytes, max_rows=limits.max_rows_per_table)
        except StrictError as e:
            raise bad(e.field, e.detail) from None
        m = b[("meta", "policy")][0]
        if m["policy_spec"] != POLICY_SPEC:
            raise bad("meta.policy.policy_spec", f"must be {POLICY_SPEC}")
        for c in ("require_admission", "require_full_resolution"):
            if m[c] not in ("true", "false"):
                raise bad(f"meta.policy.{c}", 'the string token "true" or "false"')
        def strs(table: str, *cols: str) -> list[tuple]:
            out = []
            for r in b[("table", table)]:
                if not all(isinstance(r[c], str) and r[c] for c in cols):
                    raise bad(f"table.{table}", "non-empty strings")
                out.append(tuple(r[c] for c in cols))
            if len(set(out)) != len(out):
                raise bad(f"table.{table}", "duplicate row")
            return out
        commits = [x[0] for x in strs("core_commits", "core_commit")]
        profiles = [x[0] for x in strs("profiles", "profile_sha256")]
        if not all(_HEX40.fullmatch(c) for c in commits):
            raise bad("table.core_commits", "core_commit is 40 lowercase hex")
        if not all(_HEX64.fullmatch(p) for p in profiles):
            raise bad("table.profiles", "profile_sha256 is 64 lowercase hex")
        return cls(frozenset(strs("verifiers", "verifier", "verifier_version")), frozenset(commits), frozenset(profiles),
                   frozenset(strs("runtime", "runtime_ison_graph", "runtime_ison_py")), m["require_admission"] == "true", m["require_full_resolution"] == "true")


def qualify_policy(r: Receipt, policy: TrustPolicy) -> None:
    """R4: is the verifier this receipt CLAIMS acceptable to `policy`? Raises RECEIPT_POLICY_UNSATISFIED naming the first unsatisfied dimension.

    This is NOT a trust decision. It looks only at the receipt's own claims: it does not check delivery, it does not check any bytes,
    and a receipt that satisfies it may be forged. Use `authorize_hints` to authorize use. Order: verification, verifier, profile,
    core_commit, runtime, admission, resolution.
    """
    _need(r, Receipt, "r")
    _need(policy, TrustPolicy, "policy")
    v = r.verifier

    def no(field_: str, detail: str) -> IGARError:
        return IGARError("RECEIPT_POLICY_UNSATISFIED", field_, detail, "R4")
    if not passed(r):
        raise no("verification", "a rejection receipt is evidence of rejection, never of approval")
    if (v["verifier"], v["verifier_version"]) not in policy.verifiers:
        raise no("verifier", f"{v['verifier']!r} {v['verifier_version']!r} is not an accepted verifier")
    if v["profile_sha256"] not in policy.profiles:
        raise no("profile", f"verifier profile {v['profile_sha256']!r} is not accepted")
    if v["core_commit"] not in policy.core_commits:
        raise no("core_commit", f"baseline {v['core_commit']!r} is not accepted")
    if policy.runtime and (v["runtime_ison_graph"], v["runtime_ison_py"]) not in policy.runtime:
        raise no("runtime", "runtime versions are not accepted")
    if policy.require_admission and r.result["admission"] != "admitted":
        raise no("admission", f"admission is {r.result['admission']!r}")
    if policy.require_full_resolution and (v["semantic_verification"], v["object_resolution"]) != ("full", "full"):
        raise no("resolution", "verification was not full")


@dataclass(frozen=True)
class DeliveryPins:
    """The consumer's own statement of which receipt files its controlled channel delivers: sha256 digests, e.g. from a vendoring pin file.

    This module cannot know HOW the pin file was protected; that is the consumer's boundary (25 §4.3). A pin set that an
    attacker can edit pins nothing.
    """
    receipts: frozenset[str]

    def __post_init__(self) -> None:
        receipts = _frozen("receipts", self.receipts)                       # an owned copy: the caller's live set cannot change the pins
        if not all(isinstance(d, str) and _HEX64.fullmatch(d) for d in receipts):
            raise IGARError("MALFORMED_PINS", "receipts", "every pin is 64 lowercase hex", "R5")
        object.__setattr__(self, "receipts", receipts)

    @classmethod
    def of(cls, *digests: str) -> "DeliveryPins":
        return cls(frozenset(digests))

    @classmethod
    def from_sha256sums(cls, text: bytes | str, *, names: frozenset[str], limits: Limits = DEFAULT_LIMITS) -> "DeliveryPins":
        """Read `sha256sum` lines (`<64 hex><two spaces><name>`) and pin ONLY the files named in `names`; every name must be present exactly once.

        Byte budget first (before decoding), then strict UTF-8. Lines end at LF, CRLF or a lone CR only: the other Unicode line
        separators that `str.splitlines` honours (VT, FF, FS, GS, RS, NEL, LS, PS) make the line malformed instead of splitting it,
        so a file name can never smuggle in a second, forged pin line. A name that appears twice, identically or not, is refused.
        """
        _need(limits, Limits, "limits")
        wanted = _frozen("names", names)
        if isinstance(text, (bytes, bytearray)):
            if len(text) > limits.max_payload_bytes:
                raise IGARError("RECEIPT_LIMIT_EXCEEDED", "max_payload_bytes", f"{len(text)} bytes > {limits.max_payload_bytes}", "R5")
            try:
                data = bytes(text).decode("utf-8")
            except UnicodeDecodeError:
                raise IGARError("MALFORMED_PINS", "sha256sums", "not valid UTF-8", "R5") from None
        elif isinstance(text, str):
            try:
                size = len(text.encode("utf-8"))
            except UnicodeEncodeError:
                raise IGARError("MALFORMED_PINS", "sha256sums", "not valid UTF-8", "R5") from None
            if size > limits.max_payload_bytes:
                raise IGARError("RECEIPT_LIMIT_EXCEEDED", "max_payload_bytes", f"{size} bytes > {limits.max_payload_bytes}", "R5")
            data = text
        else:
            raise TypeError(f"text must be bytes or str, got {type(text).__name__}")
        lines = re.split(r"\r\n|\n|\r", data)
        if lines and lines[-1] == "":
            lines.pop()                                                    # the final line terminator, exactly one
        found: dict[str, str] = {}
        for line in lines:
            m = re.fullmatch(r"([0-9a-f]{64})  (\S.*)", line)
            if m is None or _SEPARATORS.search(line):
                raise IGARError("MALFORMED_PINS", "sha256sums", f"not a sha256sum line: {line!r}", "R5")
            if m.group(2) in found:
                raise IGARError("MALFORMED_PINS", "sha256sums", f"{m.group(2)!r} is pinned more than once", "R5")
            found[m.group(2)] = m.group(1)
        missing = sorted(wanted - set(found))
        if missing:
            raise IGARError("MALFORMED_PINS", "sha256sums", f"no pin for {missing}", "R5")
        return cls(frozenset(found[n] for n in wanted))


_MINT = object()


@dataclass(frozen=True)
class TrustedAdmission:
    """In-process evidence that `authorize_hints` established every condition for THESE bytes. Not serializable, not a file format.

    Constructed only by `authorize_hints`. (Same-process code can always forge a Python object; this is a guard against accident,
    not against a hostile caller in your own process.)
    """
    receipt_sha256: str
    target_artifact_sha256: str
    binding_sha256: str
    igdm_payload_sha256: str
    igdc_sha256: str
    profile_sha256: str
    verifier: str
    verifier_version: str
    core_commit: str
    _mint: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._mint is not _MINT:
            raise TypeError("TrustedAdmission is issued only by authorize_hints")
        object.__setattr__(self, "_mint", None)                            # single use: dataclasses.replace() re-runs __init__ with None and is refused

    def __copy__(self) -> "TrustedAdmission":
        return self

    def __deepcopy__(self, memo: dict) -> "TrustedAdmission":
        return self

    def __reduce__(self):
        raise TypeError("TrustedAdmission has no serialization")

    def __reduce_ex__(self, protocol: int):
        raise TypeError("TrustedAdmission has no serialization")


def _bytes(name: str, v: object) -> bytes:
    if not isinstance(v, (bytes, bytearray)):
        raise TypeError(f"{name} must be bytes, got {type(v).__name__}")
    return bytes(v)


def authorize_hints(receipt: bytes, *, pins: DeliveryPins, target: bytes, binding: bytes, payload: bytes, igdc: bytes, policy: TrustPolicy,
                    limits: Limits = DEFAULT_LIMITS) -> TrustedAdmission:
    """The ONLY operation that authorizes use of a hint set. All inputs are required keywords; `igdc` must be the hint document held.

    First failure wins, in this order (nothing unpinned is ever parsed): size budget, R5 delivery pin, R0-R2 well-formed and consistent,
    R3 subject (target, binding, payload AND the hint document), R4 policy (a rejection receipt always fails here). A receipt that names
    no hint document cannot authorize one. There is no partial success.
    """
    _need(pins, DeliveryPins, "pins")
    _need(policy, TrustPolicy, "policy")
    _need(limits, Limits, "limits")
    raw = _bytes("receipt", receipt)
    target, binding, payload, igdc = _bytes("target", target), _bytes("binding", binding), _bytes("payload", payload), _bytes("igdc", igdc)
    if len(raw) > limits.max_payload_bytes:
        raise IGARError("RECEIPT_LIMIT_EXCEEDED", "max_payload_bytes", f"{len(raw)} bytes > {limits.max_payload_bytes}", "R0")
    digest = sha256_hex(raw)
    if digest not in pins.receipts:                                        # R5 delivery
        raise IGARError("RECEIPT_NOT_PINNED", "receipt", "these receipt bytes are not in the consumer's pinned delivery set", "R5")
    r = inspect_receipt(raw, limits=limits)                                # R0-R2
    check_subject(r, target=target, binding=binding, payload=payload, igdc=igdc)   # R3
    qualify_policy(r, policy)                                              # R4 (passed, verifier, profile, baseline, runtime, admission, resolution)
    s, v = r.subject, r.verifier
    return TrustedAdmission(digest, s["target_artifact_sha256"], s["binding_sha256"], s["igdm_payload_sha256"], s["igdc_sha256"], v["profile_sha256"],
                            v["verifier"], v["verifier_version"], v["core_commit"], _MINT)

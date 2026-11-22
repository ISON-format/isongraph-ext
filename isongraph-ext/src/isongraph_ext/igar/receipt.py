# isongraph-ext/src/isongraph_ext/igar/receipt.py
"""IGAR/1 receipt model, canonical wire and checks R0-R2 (25 §2-§3). The receipt digest is external to the bytes (25 §2).

Reading goes through `strict_ison.read_canonical`: byte budget before parsing, canonical form, exact blocks, unique columns, no
summary / typed columns, scalar cells. Passing R0-R2 means a receipt is well-formed and self-consistent. It does NOT mean it is true,
bound to any bytes, delivered by a trusted channel, or acceptable to any policy: those are R3, R5 and R4 (`check.py`, `trust.py`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ison_parser import Block, Document, dumps_canonical

from ..igdm.records import DEFAULT_LIMITS, Limits
from ..igx.digest import sha256_hex
from ..strict_ison import BlockShape, StrictError, read_canonical
from .errors import IGARError

RECEIPT_SPEC = "IGAR/1"
HEX64, HEX40 = re.compile(r"[0-9a-f]{64}"), re.compile(r"[0-9a-f]{40}")
FIELDS: dict[tuple[str, str], tuple[str, ...]] = {
    ("meta", "igar"): ("receipt_spec",),
    ("meta", "subject"): ("binding_sha256", "igdc_sha256", "igdm_payload_sha256", "target_artifact_sha256"),
    ("meta", "verifier"): ("verifier", "verifier_version", "igx_spec", "igdm_spec", "igdc_spec", "profile_sha256", "core_commit", "runtime_ison_graph",
                           "runtime_ison_py", "semantic_verification", "object_resolution"),
    ("meta", "result"): ("binding_schema", "payload_schema", "verification", "admission", "consumption"),
    ("meta", "failure"): ("check", "code", "field"),
    ("meta", "admission"): ("code", "step", "receipt_posture"),
    ("meta", "consumption"): ("code", "step", "field"),
    ("table", "reasons"): ("reason",),
    ("table", "unrecognized"): ("entry",),
}
SHAPES = tuple(BlockShape(k, n, f, k == "meta") for (k, n), f in FIELDS.items())
CHECKS = ("V0", "V1", "V2", "V3", "V4", "V5", "D0", "D1", "D2", "D3", "D4")
# failing check -> (binding_schema, payload_schema, verification)   (25 §2.2; written out, not computed)
STATUS: dict[str | None, tuple[str, str, str]] = {
    None: ("valid", "valid", "verified"),
    "V1": ("invalid", "not_evaluated", "not_evaluated"),
    "D1": ("valid", "invalid", "not_evaluated"),
    **{c: ("valid", "not_evaluated", "rejected") for c in ("V0", "V2", "V3", "V4", "V5", "D0")},
    **{c: ("valid", "valid", "rejected") for c in ("D2", "D3", "D4")},
}
ADMISSION_STEP = {"STALE_BINDING": "A1", "IDENTITY_CLAIM_INADMISSIBLE": "A2"}
POSTURES = ("OK", "CORE_LOSSY", "CORE_BLOCKING_DIVERGENCE", "INADMISSIBLE")
_V = {"binding_schema": ("valid", "invalid", "not_evaluated"), "payload_schema": ("valid", "invalid", "not_evaluated"),
      "verification": ("verified", "rejected", "not_evaluated"), "admission": ("admitted", "denied", "not_evaluated"),
      "consumption": ("derived", "failed", "absent")}


def _r1(field: str, detail: str) -> IGARError:
    return IGARError("MALFORMED_RECEIPT", field, detail, "R1")


def _r2(field: str, detail: str) -> IGARError:
    return IGARError("INCONSISTENT_RECEIPT", field, detail, "R2")


@dataclass(frozen=True)
class Receipt:
    subject: dict
    verifier: dict
    result: dict
    failure: dict
    admission: dict
    consumption: dict
    reasons: tuple[str, ...] = ()
    unrecognized: tuple[str, ...] = ()

    def to_document(self) -> Document:
        rows = {"igar": {"receipt_spec": RECEIPT_SPEC}, "subject": self.subject, "verifier": self.verifier, "result": self.result,
                "failure": self.failure, "admission": self.admission, "consumption": self.consumption}
        blocks = [Block("meta", n, list(FIELDS[("meta", n)]), [{f: r[f] for f in FIELDS[("meta", n)]}]) for n, r in rows.items()]
        blocks.append(Block("table", "reasons", ["reason"], [{"reason": x} for x in self.reasons]))
        blocks.append(Block("table", "unrecognized", ["entry"], [{"entry": x} for x in self.unrecognized]))
        return Document(blocks=blocks)

    def to_ison(self) -> str:
        return dumps_canonical(self.to_document())

    @property
    def digest(self) -> str:
        return sha256_hex(self.to_ison())

    @classmethod
    def from_ison(cls, data: bytes | str, *, limits: Limits = DEFAULT_LIMITS) -> "Receipt":
        """R0 and R1. The byte budget is `limits.max_payload_bytes`, applied before any parsing."""
        try:
            text, b = read_canonical(data, SHAPES, max_bytes=limits.max_payload_bytes, max_rows=limits.max_rows_per_table)
        except StrictError as e:
            step = "R0" if e.stage == "bytes" else "R1"
            if e.kind == "limit":
                raise IGARError("RECEIPT_LIMIT_EXCEEDED", "max_payload_bytes" if e.field == "size" else e.field, e.detail, step) from None
            raise IGARError("MALFORMED_RECEIPT", e.field, e.detail, step) from None
        one = lambda n: dict(b[("meta", n)][0])  # noqa: E731
        if one("igar")["receipt_spec"] != RECEIPT_SPEC:
            raise _r1("meta.igar.receipt_spec", f"must be {RECEIPT_SPEC}")
        r = cls(one("subject"), one("verifier"), one("result"), one("failure"), one("admission"), one("consumption"),
                tuple(x["reason"] for x in b[("table", "reasons")]), tuple(x["entry"] for x in b[("table", "unrecognized")]))
        r._check_shape()
        if r.to_ison() != text:                                  # a second, independent canonical check over the typed model
            raise IGARError("MALFORMED_RECEIPT", "canonical_form", "document is not the canonical writer's output for this receipt", "R0")
        return r

    def _check_shape(self) -> None:
        s, v, res, f, a = self.subject, self.verifier, self.result, self.failure, self.admission
        for col in ("binding_sha256", "igdm_payload_sha256", "target_artifact_sha256"):
            if not (isinstance(s[col], str) and HEX64.fullmatch(s[col])):
                raise _r1(f"meta.subject.{col}", "64 lowercase hex")
        if not (s["igdc_sha256"] is None or (isinstance(s["igdc_sha256"], str) and HEX64.fullmatch(s["igdc_sha256"]))):
            raise _r1("meta.subject.igdc_sha256", "null or 64 lowercase hex")
        for col, lit in (("verifier", "isongraph-ext"), ("igx_spec", "IGX/1"), ("igdm_spec", "IGDM/1"), ("igdc_spec", "IGDC/1")):
            if v[col] != lit:
                raise _r1(f"meta.verifier.{col}", f"must be {lit}")
        if not (isinstance(v["profile_sha256"], str) and HEX64.fullmatch(v["profile_sha256"])):
            raise _r1("meta.verifier.profile_sha256", "64 lowercase hex (never null: the issuer always ran under some profile)")
        for col in ("verifier_version", "runtime_ison_graph", "runtime_ison_py"):
            if not (isinstance(v[col], str) and v[col]):
                raise _r1(f"meta.verifier.{col}", "non-empty string")
        if not (v["core_commit"] is None or (isinstance(v["core_commit"], str) and HEX40.fullmatch(v["core_commit"]))):
            raise _r1("meta.verifier.core_commit", "null or 40 lowercase hex")
        if v["semantic_verification"] not in ("full", "limited", None) or v["object_resolution"] not in ("full", "skipped", None):
            raise _r1("meta.verifier", "semantic_verification/object_resolution outside vocabulary")
        for col, allowed in _V.items():
            if res[col] not in allowed:
                raise _r1(f"meta.result.{col}", f"not one of {allowed}")
        if f["check"] is not None and f["check"] not in CHECKS:
            raise _r1("meta.failure.check", f"not one of {CHECKS}")
        for blk, cols in (("failure", ("code", "field")), ("consumption", ("code", "step", "field")), ("admission", ("code",))):
            for col in cols:
                x = getattr(self, blk)[col]
                if not (x is None or (isinstance(x, str) and x)):
                    raise _r1(f"meta.{blk}.{col}", "null or non-empty string")
        if a["step"] not in ("A1", "A2", None) or a["receipt_posture"] not in (*POSTURES, None):
            raise _r1("meta.admission", "step/receipt_posture outside vocabulary")
        if a["code"] is not None and a["code"] not in ADMISSION_STEP:
            raise _r1("meta.admission.code", f"not one of {tuple(ADMISSION_STEP)}")
        for x in (*self.reasons, *self.unrecognized):
            if not (isinstance(x, str) and x):
                raise _r1("table", "rows must be non-empty strings")

    def check_consistency(self) -> None:
        """R2: the statuses are exactly what the failure record implies (25 §2.2)."""
        res, f, a, c, v, s = self.result, self.failure, self.admission, self.consumption, self.verifier, self.subject
        chk = f["check"]
        if chk not in STATUS:
            raise _r2("meta.failure.check", "unknown check")
        if (res["binding_schema"], res["payload_schema"], res["verification"]) != STATUS[chk]:
            raise _r2("meta.result", f"statuses do not match failure.check={chk!r}: expected {STATUS[chk]}")
        if (f["code"] is None) != (chk is None) or (f["field"] is None) != (chk is None):
            raise _r2("meta.failure", "code and field are non-null exactly when check is non-null")
        verified = chk is None
        if (v["core_commit"] is None) != (chk == "V1"):
            raise _r2("meta.verifier.core_commit", "null exactly when the binding failed to parse (check V1)")
        if (v["semantic_verification"] is None) == verified or (v["object_resolution"] is None) == verified:
            raise _r2("meta.verifier", "semantic_verification/object_resolution are non-null exactly when verification passed")
        if not verified:
            if res["admission"] != "not_evaluated" or any(a[k] is not None for k in a) or self.reasons or self.unrecognized:
                raise _r2("meta.admission", "admission, reasons and unrecognized are empty unless verification passed")
        else:
            if (a["code"] is None) != (a["step"] is None) or (a["code"] is not None and ADMISSION_STEP[a["code"]] != a["step"]):
                raise _r2("meta.admission", "code and step must be a matching pair or both null")
            denied = a["code"] is not None
            if res["admission"] != ("denied" if denied else "admitted"):
                raise _r2("meta.result.admission", "must be denied exactly when meta.admission.code is set")
            if a["receipt_posture"] is None or (denied != (a["receipt_posture"] == "INADMISSIBLE")):
                raise _r2("meta.admission.receipt_posture", "INADMISSIBLE exactly when denied")
        igdc, ccode = s["igdc_sha256"], c["code"]
        if (c["step"] is None) != (ccode is None) or (c["field"] is None) != (ccode is None):
            raise _r2("meta.consumption", "code, step and field are all null or all set")
        expected = "derived" if igdc is not None else "failed" if ccode is not None else "absent"
        if igdc is not None and ccode is not None:
            raise _r2("meta.consumption", "a hint set cannot be both derived and failed")
        if res["consumption"] != expected:
            raise _r2("meta.result.consumption", f"expected {expected}")
        if expected != "absent" and not verified:
            raise _r2("meta.result.consumption", "derivation needs a passed verification")
        if expected == "derived" and v["object_resolution"] != "full":
            raise _r2("meta.verifier.object_resolution", "an IGDC/1 hint set needs full object resolution")


def passed(r: Receipt) -> bool:
    return (r.result["binding_schema"], r.result["payload_schema"], r.result["verification"]) == ("valid", "valid", "verified")

# isongraph-ext/tests/test_vectors_igar.py
"""Runner for vectors/igar1 (25 §7). `op` (never the presence of a column) selects what runs; an unknown op FAILS; every `reject` row must raise
exactly its (code, step); the per-(op, expect) counts are pinned so no row can be silently dropped."""
import hashlib

import pytest
from conftest import ROOT
from ison_parser import loads

from isongraph_ext.igar.check import check_subject, inspect_receipt, recompute
from isongraph_ext.igar.errors import IGARError
from isongraph_ext.igar.issue import issue
from isongraph_ext.igar.profile import Profile
from isongraph_ext.igar.trust import DeliveryPins, TrustPolicy, authorize_hints, qualify_policy
from isongraph_ext.igdm.records import Limits

VEC = ROOT / "vectors" / "igar1"
COUNTS = {"issue:ok": 14, "inspect:ok": 5, "inspect:reject": 38, "subject:ok": 2, "subject:reject": 6, "policy:ok": 1, "policy:reject": 8,
          "authorize:ok": 1, "authorize:reject": 10, "recompute:ok": 3, "recompute:reject": 7, "profile:ok": 3, "profile:reject": 14,
          "policyfile:ok": 2, "policyfile:reject": 8}


def rows():
    doc = loads((VEC / "manifest.ison").read_text(encoding="utf-8"))
    return [r for b in doc.blocks if (b.kind, b.name) == ("table", "vectors") for r in b.rows]


def rd(rel):
    return (VEC / rel).read_bytes() if rel else None


def detail(row):
    out = {"flags": set()}
    for item in (row["detail"] or "").split(";"):
        item = item.strip()
        if item.split(":", 1)[0] in ("limits", "pins") and ":" in item:
            k, _, v = item.partition(":")
            out[k] = v
        elif "=" in item:
            k, _, v = item.partition("=")
            out[k] = v
        elif item == "igdc":
            out["flags"].add("igdc")
    return out


def limits_of(d):
    if "limits" not in d:
        return Limits()
    name, _, num = d["limits"].partition("=")
    return Limits(**{**Limits().__dict__, name: int(num)})


def test_manifest_counts_and_checksums():
    got = {}
    for r in rows():
        got[f"{r['op']}:{r['expect']}"] = got.get(f"{r['op']}:{r['expect']}", 0) + 1
    assert got == COUNTS
    ids = [r["id"] for r in rows()]
    assert len(ids) == len(set(ids))
    for line in (VEC / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        assert hashlib.sha256((VEC / name).read_bytes()).hexdigest() == digest, name


def run(row):
    op, d = row["op"], detail(row)
    vv = d.get("verifier_version", "vectors")
    lim = limits_of(d)
    if op == "issue":
        prof = Profile.from_ison(rd(row["profile"]))
        got = issue(rd(row["binding"]), rd(row["payload"]), rd(row["target"]), igdc="igdc" in d["flags"] or (d.get("igdc_state") is not None), profile=prof, verifier_version=vv)
        return got.to_ison().encode("utf-8"), ("issue", row, prof)
    if op == "inspect":
        inspect_receipt(rd(row["receipt"]), limits=lim)
    elif op == "subject":
        check_subject(inspect_receipt(rd(row["receipt"])), target=rd(row["target"]), binding=rd(row["binding"]), payload=rd(row["payload"]), igdc=rd(row["igdc"]))
    elif op == "policy":
        qualify_policy(inspect_receipt(rd(row["receipt"])), TrustPolicy.from_ison(rd(row["policy"])))
    elif op == "authorize":
        raw = rd(row["receipt"])
        pins = {"receipt": DeliveryPins.of(hashlib.sha256(raw).hexdigest()), "other": DeliveryPins.of("a" * 64), "empty": DeliveryPins(frozenset())}[d["pins"]]
        authorize_hints(receipt=raw, pins=pins, target=rd(row["target"]), binding=rd(row["binding"]), payload=rd(row["payload"]), igdc=rd(row["igdc"]),
                        policy=TrustPolicy.from_ison(rd(row["policy"])), limits=lim)
    elif op == "recompute":
        recompute(rd(row["receipt"]), rd(row["binding"]), rd(row["payload"]), rd(row["target"]), profile=rd(row["profile"]), verifier_version=vv)
    elif op == "profile":
        Profile.from_ison(rd(row["profile"]), max_bytes=lim.max_payload_bytes)
    elif op == "policyfile":
        TrustPolicy.from_ison(rd(row["policy"]), limits=lim)
    else:
        pytest.fail(f"unknown op {op!r}")
    return None, None


@pytest.mark.parametrize("row", rows(), ids=lambda r: r["id"])
def test_vector(row):
    if row["expect"] == "reject":
        with pytest.raises(IGARError) as e:
            run(row)
        assert (e.value.code, e.value.step) == (row["code"], row["step"]), e.value
        return
    got, ctx = run(row)
    if row["op"] == "issue":                                           # byte-exact with the INDEPENDENT reference builder
        assert got == rd(row["receipt"]), row["id"]
        r = inspect_receipt(rd(row["receipt"]))                         # the expected file passes R0-R2 ...
        d = detail(row)
        check_subject(r, target=rd(row["target"]), binding=rd(row["binding"]), payload=rd(row["payload"]), igdc=rd(row["igdc"]))        # ... R3 ...
        recompute(rd(row["receipt"]), rd(row["binding"]), rd(row["payload"]), rd(row["target"]), profile=rd(row["profile"]), verifier_version=d.get("verifier_version", "vectors"))   # ... R6
        assert r.verifier["profile_sha256"] == hashlib.sha256(rd(row["profile"])).hexdigest()         # the profile file IS what the receipt names


def test_every_profile_in_the_vectors_equals_production_default_where_it_claims_to():
    assert rd("profiles/default.igar-profile.ison") == Profile.default().to_ison().encode("utf-8")   # reference builder == production writer, byte for byte

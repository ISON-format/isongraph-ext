"""IGDM/1 conformance vector runner — Python is the reference. Replays vectors/igdm1/manifest.ison."""
import hashlib

import pytest
from conftest import ROOT, all_baselines
from ison_parser import loads

from isongraph_ext.igdm.bind import verify_and_admit
from isongraph_ext.igdm.errors import IGDMError
from isongraph_ext.igdm.payload import DatamaticsPayload
from isongraph_ext.igdm.records import Limits
from isongraph_ext.igx.admit import AdmissionPolicy
from isongraph_ext.igx.binding import ExtensionBinding
from isongraph_ext.igx.errors import IGXError

VEC = ROOT / "vectors" / "igdm1"
B = all_baselines()
EXPECT_IDS = {
    "ok/node-hints-full-row", "ok/edge-hints", "ok/multigraph-edge-ordinal", "ok/undirected-edge-canonical",
    "ok/groups-nested-hull-and-collapse", "ok/empty-hull-group", "ok/hierarchy-chain", "ok/x-roles-preserved", "ok/layout-only",
    "ok/empty-datamatics", "ok/optional-igdm-row", "ok/limited-runtime-skips-resolution", "ok/reserialize-stable", "ok/igpv-and-igdm-same-binding",
    "reject/not-bound", "reject/version-range-excludes", "reject/payload-digest-mismatch", "reject/binding-fails-igx",
    "reject/oversized-payload", "reject/oversized-target",
    "reject/noncanonical-text", "reject/rows-not-sorted", "reject/unexpected-block", "reject/role-outside-vocabulary",
    "reject/magnitude-out-of-range", "reject/magnitude-nan", "reject/lod-negative", "reject/boolean-not-token", "reject/badge-too-long",
    "reject/all-null-hint-row", "reject/duplicate-node-row", "reject/twin-ids", "reject/collapse-exclusivity", "reject/hierarchy-not-chain",
    "reject/group-self-parent", "reject/group-unreachable", "reject/direction-without-family", "reject/node-id-outside-int64",
    "reject/target-sha-mismatch", "reject/target-profile-mismatch", "reject/unknown-parent-group", "reject/member-unknown-group",
    "reject/group-cycle", "reject/group-depth-budget", "reject/unresolved-node", "reject/unresolved-edge", "reject/unresolved-member",
    "reject/undirected-noncanonical-endpoints", "reject/two-faults-first-wins", "reject/magnitude-exponent-form",
}


def _rows():
    doc = loads((VEC / "manifest.ison").read_bytes().decode("utf-8"))
    return [r for b in doc.blocks if (b.kind, b.name) == ("table", "vectors") for r in b.rows]


ROWS = _rows()


def _details(row):
    out = {}
    for item in (row["detail"] or "").split(";"):
        if ":" in item:
            k, v = item.split(":", 1)
            out.setdefault(k.strip(), []).append(v.strip())
    return out


def _limits(d):
    return Limits(**{k: int(v) for item in d.get("limits", []) for k, v in [item.split("=")]})


def test_manifest_integrity():
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids)) and set(ids) == EXPECT_IDS
    for r in ROWS:
        assert (VEC / "graphs" / r["target"]).is_file() and (VEC / "bindings" / r["binding"]).is_file() and (VEC / "payloads" / r["payload"]).is_file(), r["id"]
        tokens = r["expect"].split("+")
        assert all(t in ("verify_ok", "admit_ok") or t.startswith(("reject:", "admit:")) for t in tokens), r["id"]
        if any(t.startswith("reject:") for t in tokens):
            assert r["step"].startswith("D"), r["id"]


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_vector(row):
    target = (VEC / "graphs" / row["target"]).read_bytes()
    binding_text = (VEC / "bindings" / row["binding"]).read_bytes()
    payload_bytes = (VEC / "payloads" / row["payload"]).read_bytes()
    d = _details(row)
    tokens = row["expect"].split("+")
    rejects = [t for t in tokens if t.startswith("reject:")]

    def go():
        return verify_and_admit(payload_bytes, ExtensionBinding.from_ison(binding_text), target, limits=_limits(d), baselines=B,
                                policy=AdmissionPolicy(allow_retired_baselines="allow_retired" in d))

    if rejects:
        with pytest.raises((IGXError, IGDMError)) as info:
            go()
        step = "D0" if isinstance(info.value, IGXError) else info.value.step
        assert (info.value.code, step) == (rejects[0][len("reject:"):], row["step"]), info.value
        return
    result, dm, decision = go()
    assert "verify_ok" in tokens and dm.steps_passed == ("D0", "D1", "D2", "D3", "D4")
    for csv in d.get("roles", []):
        assert dm.unrecognized_roles == tuple(csv.split(",")), (row["id"], dm.unrecognized_roles)
    assert dm.object_resolution == ("skipped" if "skipped" in d.get("resolution", []) else "full")
    for t in tokens:
        if t == "admit_ok":
            assert decision.admitted, decision
        elif t.startswith("admit:"):
            assert (decision.admitted, decision.code, decision.step) == (False, t[len("admit:"):], row["step"]), decision
    assert go()[1] == dm


def test_reserialize_stable_over_ok_payloads():
    for row in ROWS:
        if row["id"].startswith("ok/"):
            text = (VEC / "payloads" / row["payload"]).read_bytes().decode("utf-8")
            p = DatamaticsPayload.from_ison(text)
            assert DatamaticsPayload.from_ison(p.to_ison()).to_ison() == text == p.to_ison() and p.digest == hashlib.sha256(text.encode()).hexdigest(), row["id"]

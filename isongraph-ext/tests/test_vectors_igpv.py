"""IGPV/1 conformance vector runner — Python is the reference. Replays vectors/igpv1/manifest.ison."""
import hashlib

import pytest
from conftest import ROOT, all_baselines
from ison_parser import loads

from isongraph_ext.igpv.bind import verify_and_admit
from isongraph_ext.igpv.errors import IGPVError
from isongraph_ext.igpv.lineage import Lineage
from isongraph_ext.igpv.payload import ProvenancePayload
from isongraph_ext.igpv.records import Limits
from isongraph_ext.igx.admit import AdmissionPolicy
from isongraph_ext.igx.binding import ExtensionBinding
from isongraph_ext.igx.errors import IGXError

VEC = ROOT / "vectors" / "igpv1"
B = all_baselines()
EXPECT_IDS = {
    "ok/attribution-whole-artifact", "ok/attribution-bytes-locator-unverified", "ok/attribution-bytes-locator-verified",
    "ok/attribution-lines-locator-verified", "ok/attribution-x-locator-stays-unverified", "ok/multiple-sources-one-object",
    "ok/typed-ids-distinct-across-graphs", "ok/edge-int-and-string-endpoints", "ok/multigraph-ordinals", "ok/undirected-logical-edge",
    "ok/graph-scope-attribution", "ok/derivation-identity", "ok/derivation-collapse-many-to-one", "ok/derivation-rewrite-edge",
    "ok/derivation-origin-unverified", "ok/limited-runtime-skips-resolution", "ok/optional-igpv-row", "ok/reserialize-stable",
    "ok/empty-provenance", "ok/origin-artifact-reached-via-objects-graph", "ok/locator-lines-counting",
    "reject/not-bound", "reject/payload-digest-null", "reject/version-range-excludes", "reject/payload-digest-mismatch",
    "reject/binding-fails-igx", "reject/oversized-payload", "reject/oversized-target", "reject/oversized-target-and-bad-binding",
    "reject/oversized-sources", "reject/noncanonical-payload-text", "reject/rows-not-sorted", "reject/duplicate-artifact-digest",
    "reject/node-id-outside-int64", "reject/twin-ids-in-one-graph", "reject/duplicate-block", "reject/unexpected-block",
    "reject/semantic-digest-set", "reject/object-null-pattern", "reject/float-node-id", "reject/ordinal-not-decimal",
    "reject/identifier-unrepresentable", "reject/locator-past-size", "reject/locator-shape", "reject/dangling-artifact-row",
    "reject/self-artifact-document-kind",
    "reject/extractor-with-policy", "reject/target-sha-mismatch", "reject/target-profile-mismatch", "reject/unresolved-producer",
    "reject/origin-not-isongraph", "reject/self-derivation", "reject/origin-graph-is-target", "reject/derivation-kind-mismatch",
    "reject/identity-with-two-origins", "reject/identity-address-differs", "reject/unresolved-node", "reject/unresolved-edge-ordinal",
    "reject/undirected-noncanonical-endpoints", "reject/origin-object-missing",
    "reject/document-size-wrong", "reject/origin-size-wrong", "reject/locator-lines-past-end", "reject/two-faults-first-wins",
    "lineage/chain-two-hops", "lineage/cycle-detected", "lineage/graph-revisited-different-object", "lineage/ambiguous-target",
    "lineage/depth-budget", "lineage/payload-unavailable-terminal", "lineage/no-derivation-record-terminal",
}


def _rows():
    doc = loads((VEC / "manifest.ison").read_bytes().decode("utf-8"))
    return [r for b in doc.blocks if (b.kind, b.name) == ("table", "vectors") for r in b.rows]


ROWS = _rows()


def _details(row) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for item in (row["detail"] or "").split(";"):
        if ":" in item:
            k, v = item.split(":", 1)
            out.setdefault(k.strip(), []).append(v.strip())
    return out


def _limits(d) -> Limits:
    kw = {}
    for item in d.get("limits", []):
        name, value = item.split("=")
        kw[name] = int(value)
    return Limits(**kw)


def _sources(row) -> dict[str, bytes]:
    if row["sources"] == "none":
        return {}
    return {name: (VEC / "sources" / name).read_bytes() for name in row["sources"].split("+")}


def test_manifest_integrity():
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids)) and set(ids) == EXPECT_IDS
    for r in ROWS:
        for name in r["payload"].split("+"):
            assert (VEC / "payloads" / name).is_file(), r["id"]
        if r["id"].startswith("lineage/"):
            assert r["target"] == "none" and r["binding"] == "none", r["id"]
        else:
            assert (VEC / "graphs" / r["target"]).is_file() and (VEC / "bindings" / r["binding"]).is_file(), r["id"]
        for name, data in _sources(r).items():
            assert hashlib.sha256(data).hexdigest() == name, r["id"]
        tokens = r["expect"].split("+")
        assert all(t in ("verify_ok", "admit_ok", "lineage_ok") or t.startswith(("reject:", "admit:", "lineage:")) for t in tokens), r["id"]
        if any(t.startswith("reject:") for t in tokens):
            assert r["step"].startswith("P"), r["id"]
        if any(t.startswith("lineage:") for t in tokens):
            assert r["step"] == "L", r["id"]


@pytest.mark.parametrize("row", [r for r in ROWS if not r["id"].startswith("lineage/")], ids=[r["id"] for r in ROWS if not r["id"].startswith("lineage/")])
def test_verify_vector(row):
    target = (VEC / "graphs" / row["target"]).read_bytes()
    binding_text = (VEC / "bindings" / row["binding"]).read_bytes()
    payload_bytes = (VEC / "payloads" / row["payload"]).read_bytes()
    d = _details(row)
    tokens = row["expect"].split("+")
    rejects = [t for t in tokens if t.startswith("reject:")]
    policy = AdmissionPolicy(allow_retired_baselines="allow_retired" in d)

    def go():
        return verify_and_admit(payload_bytes, ExtensionBinding.from_ison(binding_text), target, sources=_sources(row),
                                limits=_limits(d), baselines=B, policy=policy)

    if rejects:
        with pytest.raises((IGXError, IGPVError)) as info:
            go()
        step = "P0" if isinstance(info.value, IGXError) else info.value.step
        assert (info.value.code, step) == (rejects[0][len("reject:"):], row["step"]), info.value
        return
    result, prov, decision = go()
    assert "verify_ok" in tokens and prov.steps_passed == ("P0", "P1", "P2", "P3", "P4", "P5")
    for item in d.get("locator", []):
        aid, posture = item.split("=")
        assert prov.locators[aid] == posture, (row["id"], prov.locators)
    for item in d.get("origin", []):
        aid, status = item.split("=")
        assert prov.origin_resolution[aid] == status, (row["id"], prov.origin_resolution)
    assert prov.object_resolution == ("skipped" if "skipped" in d.get("resolution", []) else "full")
    assert result.semantic_verification == ("limited" if prov.object_resolution == "skipped" else "full")
    for t in tokens:
        if t == "admit_ok":
            assert decision.admitted, decision
        elif t.startswith("admit:"):
            assert (decision.admitted, decision.code, decision.step) == (False, t[len("admit:"):], row["step"]), decision
    # determinism: a second run in the same process is identical
    assert go()[1] == prov


@pytest.mark.parametrize("row", [r for r in ROWS if r["id"].startswith("lineage/")], ids=[r["id"] for r in ROWS if r["id"].startswith("lineage/")])
def test_lineage_vector(row):
    d = _details(row)
    payloads = [ProvenancePayload.from_ison((VEC / "payloads" / name).read_bytes()) for name in row["payload"].split("+")]
    tokens = row["expect"].split("+")
    first = payloads[0]
    obj = next(o for o in first.objects if o.object_id == d["query"][0])
    address = obj.node if obj.kind == "node" else obj.edge if obj.kind == "edge" else None

    def go():
        return Lineage(payloads, limits=_limits(d)).origins_of(first.target_artifact_sha256, address)

    fails = [t for t in tokens if t.startswith("lineage:")]
    if fails:
        with pytest.raises(IGPVError) as info:
            go()
        assert (info.value.code, info.value.step) == (fails[0][len("lineage:"):], "L"), info.value
        return
    steps = go()
    assert "lineage_ok" in tokens
    for n in d.get("origins", []):
        assert sum(1 for s in steps if s.kind) == int(n), steps
    for name in d.get("terminal", []):
        assert steps[-1].terminal == name, steps
    assert Lineage(list(reversed(payloads)), limits=_limits(d)).origins_of(first.target_artifact_sha256, address) == steps


def test_reserialize_stable_over_ok_payloads():
    for row in ROWS:
        if not row["id"].startswith("ok/"):
            continue
        text = (VEC / "payloads" / row["payload"]).read_bytes().decode("utf-8")
        p = ProvenancePayload.from_ison(text)
        assert ProvenancePayload.from_ison(p.to_ison()).to_ison() == text == p.to_ison(), row["id"]
        assert p.digest == hashlib.sha256(text.encode("utf-8")).hexdigest()

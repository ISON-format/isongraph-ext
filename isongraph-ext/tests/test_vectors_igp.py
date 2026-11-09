"""IGP/1 conformance vector runner - Python is the reference. Replays vectors/igp1/manifest.ison."""
import hashlib

import pytest
from conftest import ROOT
from ison_parser import loads

from isongraph_ext import igpv
from isongraph_ext.igp import IGPError, Limits, project, verify_projection

VEC = ROOT / "vectors" / "igp1"
EXPECT_IDS = {
    "ok/anchor-outside-node-type-allow-list", "ok/anchors-only", "ok/both-allow-lists", "ok/depth-1-out", "ok/depth-2-both",
    "ok/direction-in", "ok/edge-budget-by-distance", "ok/edge-budget-tie-break-greatest-edge-order",
    "ok/edge-budget-untraversed-mandatory-first", "ok/induced-sibling-edge", "ok/institutional-context", "ok/int-and-string-ids",
    "ok/mandatory-also-anchor", "ok/mandatory-inside-traversal", "ok/mandatory-outside-traversal-induced-edge",
    "ok/mandatory-survives-without-edge", "ok/node-budget-distance-before-address", "ok/node-budget-farthest-first",
    "ok/node-type-allow-list", "ok/out-projection-holds-incoming-edge", "ok/property-carry-over", "ok/protected-equals-max-nodes",
    "ok/relation-allow-list", "ok/same-id-different-types", "ok/stats-exclude-never-selected", "ok/supply-chain-impact",
    "ok/trailing-lf-source-identity-rows", "ok/unrestricted-empty-lists", "ok/whole-graph-identity", "reject/anchor-not-found",
    "reject/budget-unsatisfiable", "reject/lineage-byte-limit", "reject/lineage-row-limit", "reject/mandatory-not-found",
    "reject/policy-bad-direction", "reject/policy-depth-out-of-range", "reject/policy-duplicate-anchor", "reject/policy-duplicate-block",
    "reject/policy-id-beyond-int64", "reject/policy-noncanonical", "reject/policy-oversized", "reject/policy-twin-ids",
    "reject/policy-unexpected-block", "reject/policy-unknown-identifier", "reject/policy-wrong-spec", "reject/policy-zero-anchors",
    "reject/source-id-beyond-int64", "reject/source-isonl", "reject/source-multigraph", "reject/source-node-type-column",
    "reject/source-noncanonical", "reject/source-not-utf8", "reject/source-oversized", "reject/source-undirected",
    "reject/two-faults-first-wins", "reject/typed-id-mismatch", "reject/verify-implementation-version", "reject/verify-policy-changed",
    "reject/verify-tampered-payload", "reject/verify-tampered-result", "reject/verify-version-before-result"
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
    kw, lin = {}, {}
    for item in d.get("limits", []):
        name, value = item.split("=")
        (lin if name.startswith("lineage.") else kw)[name.removeprefix("lineage.")] = int(value)
    return Limits(**kw, **({"lineage": igpv.Limits(**lin)} if lin else {}))


def test_manifest_integrity():
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids)) and set(ids) == EXPECT_IDS
    for r in ROWS:
        assert (VEC / "sources" / r["source"]).is_file() and (VEC / "policies" / r["policy"]).is_file(), r["id"]
        for col in ("result", "payload"):
            assert r[col] == "none" or (VEC / "expected" / r[col]).is_file(), r["id"]
        assert r["expect"] == "ok" or (r["expect"].startswith("reject:") and r["step"] in ("Q0", "Q1", "Q2", "Q3", "Q4")), r["id"]
        assert (r["expect"] == "ok") == (r["step"] is None), r["id"]


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_vector(row):
    source = (VEC / "sources" / row["source"]).read_bytes()
    policy = (VEC / "policies" / row["policy"]).read_bytes()
    d = _details(row)
    limits = _limits(d)
    verifying = "verify" in d
    result = None if row["result"] == "none" else (VEC / "expected" / row["result"]).read_bytes()
    payload = None if row["payload"] == "none" else (VEC / "expected" / row["payload"]).read_bytes()

    def go():
        return verify_projection(source, policy, result, payload, limits=limits) if verifying else project(source, policy, limits=limits)

    if row["expect"].startswith("reject:"):
        with pytest.raises(IGPError) as info:
            go()
        assert (info.value.code, info.value.step) == (row["expect"][len("reject:"):], row["step"]), info.value
        return
    proj = go()
    assert proj.result_bytes == result and proj.payload.to_ison().encode("utf-8") == payload          # byte-exact expected outputs
    assert go().result_bytes == proj.result_bytes                                                      # deterministic
    verify_projection(source, policy, result, payload, limits=limits)                                  # and recomputation accepts them
    sources = {hashlib.sha256(source).hexdigest(): source}                                             # and IGPV/1 itself admits the lineage
    binding = igpv.bind(proj.result_bytes, proj.payload, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact", sources=sources)
    assert igpv.verify_and_admit(proj.payload, binding, proj.result_bytes, sources=sources)[2].admitted
    if "source" in d.get("result", []):
        assert proj.result_bytes == source
    for spec in d.get("stats", []):
        for kv in spec.split(","):
            k, v = kv.split("=")
            assert str(proj.stats[k]).lower() == v, (k, dict(proj.stats))

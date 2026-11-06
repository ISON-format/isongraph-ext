"""IGX/1 conformance vector runner - Python is the reference. Replays vectors/igx1/manifest.ison."""

import pytest
from conftest import ROOT, TEST_REGISTRY, all_baselines
from ison_parser import loads

from isongraph_ext.igx.admit import AdmissionPolicy, admit
from isongraph_ext.igx.binding import ExtensionBinding
from isongraph_ext.igx.digest import sha256_hex
from isongraph_ext.igx.errors import IGXError
from isongraph_ext.igx.verify import EMPTY_REGISTRY, verify

VEC = ROOT / "vectors" / "igx1"
B = all_baselines()
REGISTRIES = {"empty": EMPTY_REGISTRY, "test": TEST_REGISTRY}
EXPECT_IDS = {
    "ok/python-full-producer-bound", "ok/python-full-artifact-claim", "ok/claim-none", "ok/ineligible-source-artifact-claim",
    "ok/optional-unknown-preserved", "ok/empty-capabilities", "ok/known-test-capability-required", "ok/retired-baseline-verifies",
    "reject/noncanonical-binding-text", "reject/duplicate-igx-block", "reject/unexpected-block", "reject/semantic-digest-set",
    "reject/writer-port-mismatch", "reject/source-canonical-token-disallowed", "reject/wrong-core-commit", "reject/wrong-corpus-digest",
    "reject/wrong-receipt-digest", "reject/posture-not-in-receipt", "reject/receipt-crossfield-mismatch", "reject/wrong-artifact-sha",
    "reject/python-writer-noncanonical-bytes", "reject/python-claim-crlf-bytes", "reject/eligibility-stored-mismatch",
    "reject/unknown-required", "reject/required-range-excludes-registered", "reject/two-faults-first-wins",
    "admit/known-defect-producer-bound", "admit/ineligible-source-producer-bound", "admit/multigraph-source-producer-bound",
    "admit/cross-port-reserved", "admit/lossy-producer-bound-reserved", "admit/lossy-policy-field-ignored", "admit/consumer-known-defect-reported",
    "admit/retired-limited-producer-bound", "reject/trailing-newline-in-hex-field",
}


def _rows():
    doc = loads((VEC / "manifest.ison").read_bytes().decode("utf-8"))
    return [r for b in doc.blocks if (b.kind, b.name) == ("table", "vectors") for r in b.rows]


ROWS = _rows()


def test_manifest_integrity():
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids)) and set(ids) == EXPECT_IDS
    sources = {r["path"]: r["sha256"] for b in loads((VEC / "SOURCES.ison").read_bytes().decode("utf-8")).blocks for r in b.rows}
    for r in ROWS:
        assert (VEC / "graphs" / r["graph"]).is_file() and (VEC / "bindings" / r["binding"]).is_file(), r["id"]
        if not r["graph"].startswith("synthetic/"):   # synthetic/ graphs are generator-made mutations, not Core copies
            assert sha256_hex((VEC / "graphs" / r["graph"]).read_bytes()) == sources[r["graph"]], r["id"]
        assert r["registry"] in REGISTRIES, r["id"]
        tokens = r["expect"].split("+")
        assert all(t in ("verify_ok", "admit_ok", "retired_ok") or t.startswith(("reject:", "admit:", "admit_posture:", "retired:")) for t in tokens), r["id"]
        if any(t.startswith("reject:") for t in tokens):
            assert r["step"].startswith("V"), r["id"]
        elif any(t.startswith(("admit:", "retired:")) for t in tokens):
            assert r["step"].startswith("A"), r["id"]


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_vector(row):
    source = (VEC / "graphs" / row["graph"]).read_bytes()
    text = (VEC / "bindings" / row["binding"]).read_bytes()
    tokens = row["expect"].split("+")
    registry = REGISTRIES[row["registry"]]
    rejects = [t for t in tokens if t.startswith("reject:")]
    if rejects:
        with pytest.raises(IGXError) as info:
            verify(ExtensionBinding.from_ison(text), source, baselines=B, registry=registry)
        assert (info.value.code, info.value.step) == (rejects[0][len("reject:"):], row["step"]), info.value
        return
    binding = ExtensionBinding.from_ison(text)
    assert binding.digest == sha256_hex(text)
    result = verify(binding, source, baselines=B, registry=registry)
    assert "verify_ok" in tokens
    if row["id"] == "ok/optional-unknown-preserved":
        assert len(result.unrecognized_optional) == 1
    if row["detail"] and "limited" in row["detail"]:
        assert result.semantic_verification == "limited" and result.source_canonical is None
    else:
        assert result.semantic_verification == "full"
    decision = admit(binding, result, baselines=B)
    retired_policy = AdmissionPolicy(allow_retired_baselines=True)
    for t in tokens:
        if t == "admit_ok":
            assert decision.admitted, decision
        elif t.startswith("admit:"):
            assert (decision.admitted, decision.code, decision.step) == (False, t[len("admit:"):], row["step"]), decision
        elif t.startswith("admit_posture:"):
            assert decision.receipt_posture == t[len("admit_posture:"):], decision
        elif t == "retired_ok":
            assert admit(binding, result, policy=retired_policy, baselines=B).admitted
        elif t.startswith("retired:"):      # with allow_retired_baselines, denied with this code at row["step"]
            d = admit(binding, result, policy=retired_policy, baselines=B)
            assert (d.admitted, d.code, d.step) == (False, t[len("retired:"):], row["step"]), d
            decision = d
    if row["id"] == "admit/lossy-policy-field-ignored":
        d2 = admit(binding, result, policy=AdmissionPolicy(accept_lossy_domains=frozenset({"binary64-inexact-int"})), baselines=B)
        assert not d2.admitted and "POLICY_FIELD_RESERVED" in d2.reasons
    if row["detail"] and "reason:" in row["detail"]:
        assert row["detail"].split("reason:", 1)[1].strip() in decision.reasons, decision


def test_reserialize_stable_over_ok_bindings():
    for row in ROWS:
        if not row["id"].startswith("ok/"):
            continue
        text = (VEC / "bindings" / row["binding"]).read_bytes().decode("utf-8")
        b = ExtensionBinding.from_ison(text)
        assert ExtensionBinding.from_ison(b.to_ison()).to_ison() == text == b.to_ison(), row["id"]


# Implementation-independent oracle: this literal was produced from the spec's field list with ison-py alone
# (no isongraph_ext code) before the implementation existed. If the generator and this literal ever disagree,
# the implementation moved, not the spec.
REFERENCE_BINDING = (
    "meta.core_baseline\n"
    "core_commit core_conformance_receipt core_format core_semantic_spec core_vector_corpus_commit core_vector_corpus_digest "
    "core_vector_corpus_version core_version producer_core_posture producer_port producer_port_version\n"
    "ce9d3b78afd79cbdffdd67546bcb5278dc38be70 cece1259ac61172a1d519b5ad31cef8b29ff3e466f629f4cb72b4f34fdda9ac0 isongraph "
    "ISONGraph-Semantic/2-draft f88af8bd29680e7b6e7716585be936d5738eb55f 1d1a6648abeeadece24b43a163949d02241911706866236cc32bd6b61745bcb0 "
    "1 1.4.1 FULL python 1.4.1\n"
    "\n"
    "meta.igx\n"
    "binding_spec identity_claim\n"
    "IGX/1 producer_bound\n"
    "\n"
    "meta.source\n"
    "artifact_sha256 core_writer_implementation core_writer_version semantic_digest semantic_digest_algorithm serialization_profile "
    "source_canonical source_semantic_eligibility source_semantic_reason\n"
    "582f02bb713e197a7d52f28bbb30271f541ca04a35c0e30d67771e9da3c29ebc isongraph-python 1.4.1 null null ison-v1 \"true\" eligible null\n"
    "\n"
    "table.capabilities\n"
    "extension payload_sha256 requirement version_range"
)
REFERENCE_DIGEST = "23c11aa5c61e89aa121564468cdaa9653f2a982bac2e6c94ed7079732c588c89"


def test_reference_binding_matches_spec_literal():
    text = (VEC / "bindings" / "ok--python-full-producer-bound.igx.ison").read_bytes()
    assert text == REFERENCE_BINDING.encode("utf-8")
    assert sha256_hex(text) == REFERENCE_DIGEST
    assert ExtensionBinding.from_ison(text).digest == REFERENCE_DIGEST

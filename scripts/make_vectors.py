#!/usr/bin/env python3
"""Generate vectors/igx1 (bindings + manifest) from the public API plus deliberate mutations (17 §5).

Each row is asserted against the runtime before it is written: the manifest records observed behaviour.
Run from the repo root with the venv:  .venv/Scripts/python.exe scripts/make_vectors.py
"""

from __future__ import annotations

import dataclasses
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "isongraph-ext" / "src"))
sys.path.insert(0, str(ROOT / "isongraph-ext" / "tests"))

from conftest import FOREIGN, LOSSY, RECEIPT_SHA, RETIRED, TEST_REGISTRY, all_baselines  # noqa: E402
from ison_parser import Block, Document, dumps_canonical, loads  # noqa: E402

from isongraph_ext.igx.admit import AdmissionPolicy, admit  # noqa: E402
from isongraph_ext.igx.bind import bind  # noqa: E402
from isongraph_ext.igx.binding import Capability, Consumer, ExtensionBinding  # noqa: E402
from isongraph_ext.igx.errors import IGXError  # noqa: E402
from isongraph_ext.igx.verify import EMPTY_REGISTRY, verify  # noqa: E402

VEC = ROOT / "vectors" / "igx1"
B = all_baselines()
REG = {"empty": EMPTY_REGISTRY, "test": TEST_REGISTRY}
POS, BIG, MULTI, NONCANON, UNDIR = ("ids/positive-int.ison", "values/int-beyond-int64.ison", "structure/multigraph-document.ison",
                                    "serialization/non-canonical-order.ison", "structure/undirected-basic.ison")
POSCRLF = "synthetic/positive-int-crlf.ison"   # generator-made: Core copy with LF -> CRLF; not listed in SOURCES.ison


def graph(rel: str) -> bytes:
    return (VEC / "graphs" / rel).read_bytes()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


(VEC / "graphs" / "synthetic").mkdir(parents=True, exist_ok=True)
(VEC / "graphs" / POSCRLF).write_bytes(graph(POS).replace(b"\n", b"\r\n"))


def produce(rel: str, claim="producer_bound", port="python", **kw) -> ExtensionBinding:
    return bind(graph(rel), serialization_profile="ison-v1", producer_port=port, identity_claim=claim, **kw)


def ts(rel: str, claim: str) -> ExtensionBinding:
    return produce(rel, claim=claim, port="ts")


def rep(b: ExtensionBinding, **changes) -> str:
    return dataclasses.replace(b, **changes).to_ison()


def add_block(text: str, block: Block) -> str:
    doc = loads(text)
    doc.blocks.append(block)
    return dumps_canonical(doc)


base = produce(POS)
caps_opt = produce(POS, capabilities=(Capability("x-unknown", "^3", "OPTIONAL", None),))
caps_req = produce(POS, capabilities=(Capability("x-igx-test", "^1", "REQUIRED", None),), registry=TEST_REGISTRY)
big_artifact = produce(BIG, claim="artifact")
multi_artifact = produce(MULTI, claim="artifact")
# The retired fixture's runtime is not installed, so bind() refuses it (CORE_RUNTIME_MISMATCH): historical bindings are
# re-pinned by field replacement, exactly as a binding produced long ago would arrive.
retired_sha = B[RETIRED].receipts["python"].sha256
retired_artifact_text = rep(base, core_commit=RETIRED, core_conformance_receipt=retired_sha, identity_claim="artifact")
retired_pb_text = rep(base, core_commit=RETIRED, core_conformance_receipt=retired_sha)
lossy_artifact = produce(POS, claim="artifact", baseline=B[LOSSY])
foreign_artifact_text = rep(base, core_commit=FOREIGN, core_conformance_receipt=B[FOREIGN].receipts["python"].sha256)
ts_artifact = ts(POS, "artifact")
consumer_ts = produce(POS, consumer=Consumer("ts", "1.4.1", "KNOWN_DEFECT", RECEIPT_SHA["ts"]))

# id, graph, text, registry, expect, step, detail
VECTORS = [
    ("ok/python-full-producer-bound", POS, base.to_ison(), "empty", "verify_ok+admit_ok+admit_posture:OK", None, None),
    ("ok/python-full-artifact-claim", POS, produce(POS, claim="artifact").to_ison(), "empty", "verify_ok+admit_ok", None, None),
    ("ok/claim-none", POS, produce(POS, claim="none").to_ison(), "empty", "verify_ok+admit_ok", None, None),
    ("ok/ineligible-source-artifact-claim", BIG, big_artifact.to_ison(), "empty", "verify_ok+admit_ok", None, "eligibility ineligible INTEGER_OUT_OF_INT64 stored and re-derived"),
    ("ok/optional-unknown-preserved", POS, caps_opt.to_ison(), "empty", "verify_ok+admit_ok", None, "unrecognized_optional has one entry"),
    ("ok/empty-capabilities", POS, base.to_ison(), "empty", "verify_ok+admit_ok", None, "table.capabilities header only"),
    ("ok/known-test-capability-required", POS, caps_req.to_ison(), "test", "verify_ok+admit_ok", None, None),
    ("ok/retired-baseline-verifies", POS, retired_artifact_text, "empty", "verify_ok+admit:STALE_BINDING+retired_ok", "A1", "limited: retired baseline runtime not installed"),
    ("admit/retired-limited-producer-bound", POS, retired_pb_text, "empty", "verify_ok+retired:IDENTITY_CLAIM_INADMISSIBLE", "A2", "limited; reason:SEMANTIC_REVERIFICATION_UNAVAILABLE"),
    ("reject/noncanonical-binding-text", POS, base.to_ison() + "\n", "empty", "reject:MALFORMED_BINDING", "V1", "trailing newline"),
    ("reject/duplicate-igx-block", POS, add_block(base.to_ison(), Block("meta", "igx", ["binding_spec", "identity_claim"], [{"binding_spec": "IGX/1", "identity_claim": "none"}])), "empty", "reject:MALFORMED_BINDING", "V1", None),
    ("reject/unexpected-block", POS, add_block(base.to_ison(), Block("meta", "extra", ["a"], [{"a": 1}])), "empty", "reject:MALFORMED_BINDING", "V1", None),
    ("reject/semantic-digest-set", POS, rep(base, semantic_digest="ab" * 32, semantic_digest_algorithm="sha256"), "empty", "reject:MALFORMED_BINDING", "V1", None),
    ("reject/writer-port-mismatch", POS, rep(base, core_writer_implementation="isongraph-ts"), "empty", "reject:MALFORMED_BINDING", "V1", None),
    ("reject/source-canonical-token-disallowed", POS, rep(ts_artifact, source_canonical="true"), "empty", "reject:MALFORMED_BINDING", "V1", None),
    ("reject/wrong-core-commit", POS, rep(base, core_commit="a" * 40), "empty", "reject:CORE_BASELINE_UNSUPPORTED", "V2", None),
    ("reject/wrong-corpus-digest", POS, rep(base, core_vector_corpus_digest="c" * 64), "empty", "reject:CORPUS_DIGEST_MISMATCH", "V2", None),
    ("reject/wrong-receipt-digest", POS, rep(base, core_conformance_receipt="d" * 64), "empty", "reject:RECEIPT_REFERENCE_INVALID", "V3", None),
    ("reject/posture-not-in-receipt", POS, rep(ts_artifact, producer_core_posture="FULL"), "empty", "reject:RECEIPT_REFERENCE_INVALID", "V3", "binding says FULL, ts receipt says KNOWN_DEFECT"),
    ("reject/receipt-crossfield-mismatch", POS, foreign_artifact_text, "empty", "reject:RECEIPT_REFERENCE_INVALID", "V3", "receipt.core_commit"),
    ("reject/wrong-artifact-sha", POS, rep(base, artifact_sha256="e" * 64), "empty", "reject:SOURCE_BINDING_MISMATCH", "V4", None),
    ("reject/python-writer-noncanonical-bytes", NONCANON, rep(base, artifact_sha256=sha(graph(NONCANON))), "empty", "reject:SOURCE_WRITER_MISMATCH", "V4", None),
    ("reject/python-claim-crlf-bytes", POSCRLF, rep(base, artifact_sha256=sha(graph(POSCRLF))), "empty", "reject:SOURCE_WRITER_MISMATCH", "V4", "CRLF-rewritten artifact; sha matches, writer does not"),
    ("reject/eligibility-stored-mismatch", BIG, rep(big_artifact, source_semantic_eligibility="eligible", source_semantic_reason=None), "empty", "reject:SOURCE_ELIGIBILITY_MISMATCH", "V4", None),
    ("reject/unknown-required", POS, rep(base, capabilities=(Capability("x-igx-test", "^1", "REQUIRED", None),)), "empty", "reject:UNSUPPORTED_CAPABILITY", "V5", None),
    ("reject/required-range-excludes-registered", POS, rep(base, capabilities=(Capability("x-igx-test", "=2.0.0", "REQUIRED", None),)), "test", "reject:UNSUPPORTED_CAPABILITY", "V5", None),
    ("reject/two-faults-first-wins", POS, rep(base, core_vector_corpus_digest="c" * 64, capabilities=(Capability("x-nope", "^1", "REQUIRED", None),)), "empty", "reject:CORPUS_DIGEST_MISMATCH", "V2", None),
    ("admit/known-defect-producer-bound", POS, rep(ts_artifact, identity_claim="producer_bound"), "empty", "verify_ok+admit:IDENTITY_CLAIM_INADMISSIBLE", "A2", "reason:CORE_BLOCKING_DIVERGENCE"),
    ("admit/ineligible-source-producer-bound", BIG, rep(big_artifact, identity_claim="producer_bound"), "empty", "verify_ok+admit:IDENTITY_CLAIM_INADMISSIBLE", "A2", "reason:SOURCE_NOT_ELIGIBLE:INTEGER_OUT_OF_INT64"),
    ("admit/multigraph-source-producer-bound", MULTI, rep(multi_artifact, identity_claim="producer_bound"), "empty", "verify_ok+admit:IDENTITY_CLAIM_INADMISSIBLE", "A2", "reason:SOURCE_NOT_ELIGIBLE:MULTIGRAPH_DOCUMENT"),
    ("admit/cross-port-reserved", POS, rep(consumer_ts, identity_claim="cross_port"), "empty", "verify_ok+admit:IDENTITY_CLAIM_INADMISSIBLE", "A2", "reason:SEMANTIC2_NOT_FROZEN"),
    ("admit/lossy-producer-bound-reserved", POS, rep(lossy_artifact, identity_claim="producer_bound"), "empty", "verify_ok+admit:IDENTITY_CLAIM_INADMISSIBLE", "A2", "reason:LOSSY_PRODUCER_BOUND_RESERVED"),
    ("admit/lossy-policy-field-ignored", POS, rep(lossy_artifact, identity_claim="producer_bound"), "empty", "verify_ok+admit:IDENTITY_CLAIM_INADMISSIBLE", "A2", "reason:LOSSY_PRODUCER_BOUND_RESERVED"),
    ("admit/consumer-known-defect-reported", POS, consumer_ts.to_ison(), "empty", "verify_ok+admit_ok+admit_posture:CORE_BLOCKING_DIVERGENCE", "A3", None),
]


def check(graph_rel: str, text: str, registry: str, expect: str, step: str | None) -> None:
    source, tokens = graph(graph_rel), expect.split("+")
    rejects = [t for t in tokens if t.startswith("reject:")]
    try:
        binding = ExtensionBinding.from_ison(text)
        result = verify(binding, source, baselines=B, registry=REG[registry])
    except IGXError as e:
        assert rejects and (e.code, e.step) == (rejects[0][7:], step), (expect, e)
        return
    assert not rejects, expect
    decision = admit(binding, result, baselines=B)
    for t in tokens:
        if t == "admit_ok":
            assert decision.admitted, decision
        elif t.startswith("admit:"):
            assert (decision.code, decision.step) == (t[6:], step), decision
        elif t.startswith("admit_posture:"):
            assert decision.receipt_posture == t[14:], decision
        elif t.startswith("retired:"):
            d = admit(binding, result, policy=AdmissionPolicy(allow_retired_baselines=True), baselines=B)
            assert (d.code, d.step) == (t[8:], step), d
        elif t == "retired_ok":
            assert admit(binding, result, policy=AdmissionPolicy(allow_retired_baselines=True), baselines=B).admitted


def main() -> int:
    (VEC / "bindings").mkdir(parents=True, exist_ok=True)
    rows = []
    for vid, graph_rel, text, registry, expect, step, detail in VECTORS:
        check(graph_rel, text, registry, expect, step)
        fname = vid.replace("/", "--") + ".igx.ison"
        (VEC / "bindings" / fname).write_bytes(text.encode("utf-8"))
        rows.append({"id": vid, "graph": graph_rel, "binding": fname, "registry": registry, "expect": expect, "step": step, "detail": detail})
    doc = Document(blocks=[
        Block("meta", "corpus", ["version", "binding_spec"], [{"version": 1, "binding_spec": "IGX/1"}]),
        Block("table", "vectors", ["id", "graph", "binding", "registry", "expect", "step", "detail"], rows),
    ])
    (VEC / "manifest.ison").write_bytes((dumps_canonical(doc) + "\n").encode("utf-8"))
    print(f"{len(rows)} vectors written")
    return 0


if __name__ == "__main__":
    sys.exit(main())

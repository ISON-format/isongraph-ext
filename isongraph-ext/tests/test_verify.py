import pytest
from conftest import FOREIGN, LOSSY, RECEIPT_SHA, RETIRED, TEST_REGISTRY, all_baselines, graph_bytes, make_binding

from isongraph_ext.igx.binding import Capability, Consumer
from isongraph_ext.igx.digest import sha256_hex
from isongraph_ext.igx.errors import IGXError
from isongraph_ext.igx.verify import EMPTY_REGISTRY, VerificationResult, verify

B = all_baselines()
SRC = graph_bytes("ids/positive-int.ison")


def _fails(binding, source, code, step, field=None, **kw):
    with pytest.raises(IGXError) as info:
        verify(binding, source, baselines=B, **kw)
    assert (info.value.code, info.value.step) == (code, step), info.value
    if field:
        assert info.value.field == field, info.value
    return info.value


def test_verify_ok_producer_bound():
    r = verify(make_binding(), SRC, baselines=B)
    assert isinstance(r, VerificationResult)
    assert r.binding_digest == make_binding().digest
    assert (r.source_canonical, r.source_semantic_eligibility, r.source_semantic_reason) == ("true", "eligible", None)
    assert r.semantic_verification == "full"
    assert r.unrecognized_optional == () and r.steps_passed == ("V0", "V1", "V2", "V3", "V4", "V5")


def test_source_may_be_str():
    assert verify(make_binding(), SRC.decode("utf-8"), baselines=B).source_canonical == "true"


def test_v1_runs_on_programmatic_bindings():
    _fails(make_binding(identity_claim="bogus"), SRC, "MALFORMED_BINDING", "V1", "meta.igx.identity_claim")


def test_v2_unknown_commit():
    _fails(make_binding(core_commit="a" * 40), SRC, "CORE_BASELINE_UNSUPPORTED", "V2", "meta.core_baseline.core_commit")


@pytest.mark.parametrize("field", ["core_format", "core_version", "core_semantic_spec"])
def test_v2_baseline_pins(field):
    _fails(make_binding(**{field: "other"}), SRC, "CORE_BASELINE_UNSUPPORTED", "V2", f"meta.core_baseline.{field}")


@pytest.mark.parametrize("field,value", [("core_vector_corpus_version", 2), ("core_vector_corpus_commit", "b" * 40), ("core_vector_corpus_digest", "c" * 64)])
def test_v2_corpus_pins(field, value):
    _fails(make_binding(**{field: value}), SRC, "CORPUS_DIGEST_MISMATCH", "V2", f"meta.core_baseline.{field}")


def test_v3_wrong_receipt_digest():
    _fails(make_binding(core_conformance_receipt="d" * 64), SRC, "RECEIPT_REFERENCE_INVALID", "V3", "meta.core_baseline.core_conformance_receipt")


def test_v3_posture_not_in_receipt():
    b = make_binding(producer_port="ts", core_writer_implementation="isongraph-ts", source_canonical="unverified",
                     producer_core_posture="FULL", core_conformance_receipt=RECEIPT_SHA["ts"])
    _fails(b, SRC, "RECEIPT_REFERENCE_INVALID", "V3", "meta.core_baseline.producer_core_posture")


def test_v3_port_version_not_in_receipt():
    _fails(make_binding(producer_port_version="1.4.0", core_writer_version="1.4.0"), SRC, "RECEIPT_REFERENCE_INVALID", "V3", "meta.core_baseline.producer_port_version")


def test_v3_receipt_crossfield_mismatch():
    foreign = B[FOREIGN]
    b = make_binding(core_commit=FOREIGN, core_conformance_receipt=foreign.receipts["python"].sha256)
    _fails(b, SRC, "RECEIPT_REFERENCE_INVALID", "V3", "receipt.core_commit")


def test_v3_consumer_checked_too():
    b = make_binding(consumer=Consumer("ts", "1.4.1", "FULL", RECEIPT_SHA["ts"]))
    _fails(b, SRC, "RECEIPT_REFERENCE_INVALID", "V3", "meta.consumer.consumer_core_posture")


def test_v4_wrong_artifact_sha():
    _fails(make_binding(artifact_sha256="e" * 64), SRC, "SOURCE_BINDING_MISMATCH", "V4", "meta.source.artifact_sha256")


def test_v4_python_writer_noncanonical_bytes():
    src = graph_bytes("serialization/non-canonical-order.ison")
    _fails(make_binding(artifact_sha256=sha256_hex(src)), src, "SOURCE_WRITER_MISMATCH", "V4", "meta.source.source_canonical")


def test_v4_non_python_stored_unverified_is_ok():
    b = make_binding(producer_port="ts", core_writer_implementation="isongraph-ts", source_canonical="unverified",
                     producer_core_posture="KNOWN_DEFECT", core_conformance_receipt=RECEIPT_SHA["ts"])
    assert verify(b, SRC, baselines=B).source_canonical == "unverified"


def test_v4_eligibility_stored_mismatch():
    src = graph_bytes("values/int-beyond-int64.ison")
    b = make_binding(artifact_sha256=sha256_hex(src))  # stored eligible, derived ineligible
    e = _fails(b, src, "SOURCE_ELIGIBILITY_MISMATCH", "V4", "meta.source.source_semantic_eligibility")
    assert "INTEGER_OUT_OF_INT64" in e.detail


def test_v4_ineligible_source_verifies_when_stored_correctly():
    src = graph_bytes("values/int-beyond-int64.ison")
    b = make_binding(artifact_sha256=sha256_hex(src), source_semantic_eligibility="ineligible", source_semantic_reason="INTEGER_OUT_OF_INT64")
    r = verify(b, src, baselines=B)
    assert (r.source_semantic_eligibility, r.source_semantic_reason) == ("ineligible", "INTEGER_OUT_OF_INT64")


def test_v5_unknown_required():
    b = make_binding(capabilities=(Capability("x-igx-test", "^1", "REQUIRED", None),))
    _fails(b, SRC, "UNSUPPORTED_CAPABILITY", "V5", "table.capabilities.x-igx-test", registry=EMPTY_REGISTRY)
    assert verify(b, SRC, baselines=B, registry=TEST_REGISTRY).unrecognized_optional == ()


def test_v5_required_range_excludes_registered():
    b = make_binding(capabilities=(Capability("x-igx-test", "=2.0.0", "REQUIRED", None),))
    _fails(b, SRC, "UNSUPPORTED_CAPABILITY", "V5", "table.capabilities.x-igx-test", registry=TEST_REGISTRY)


def test_v5_optional_unknown_preserved():
    cap = Capability("x-unknown", "^3", "OPTIONAL", None)
    r = verify(make_binding(capabilities=(cap,)), SRC, baselines=B)
    assert r.unrecognized_optional == (cap,)


def test_two_faults_first_wins():
    b = make_binding(core_vector_corpus_digest="c" * 64, capabilities=(Capability("x-nope", "^1", "REQUIRED", None),))
    _fails(b, SRC, "CORPUS_DIGEST_MISMATCH", "V2")


def test_retired_baseline_with_missing_runtime_verifies_limited():
    # The retired fixture records runtime hashes the installed Core does not have: evidence still verifies,
    # semantic re-derivation does not happen, and the result says so (17 §4 V0).
    b = make_binding(core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256, identity_claim="artifact")
    r = verify(b, SRC, baselines=B)
    assert r.semantic_verification == "limited"
    assert (r.source_canonical, r.source_semantic_eligibility, r.source_semantic_reason) == (None, None, None)
    assert r.steps_passed == ("V0", "V1", "V2", "V3", "V4", "V5")
    # the byte check still runs in limited mode
    _fails(make_binding(core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256, artifact_sha256="f" * 64),
           SRC, "SOURCE_BINDING_MISMATCH", "V4")
    # stored derived fields are NOT compared in limited mode (nothing to compare against)
    b2 = make_binding(core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256,
                      source_semantic_eligibility="ineligible", source_semantic_reason="MULTIGRAPH_DOCUMENT")
    assert verify(b2, SRC, baselines=B).semantic_verification == "limited"


def test_lossy_baseline_verifies():
    b = make_binding(core_commit=LOSSY, producer_core_posture="LOSSY_KNOWN", core_conformance_receipt=B[LOSSY].receipts["python"].sha256)
    assert verify(b, SRC, baselines=B).source_canonical == "true"


def test_v0_runtime_mismatch_on_current_baseline(monkeypatch):
    import importlib
    v = importlib.import_module("isongraph_ext.igx.verify")   # the package re-exports verify() under the same name
    real = B[make_binding().core_commit]
    good_hashes = dict(real.core_runtime)
    monkeypatch.setattr(v, "installed_core_runtime", lambda modules: (("ison-graph", "1.4.1"), {**good_hashes, "ison_graph/__init__.py": "0" * 64}, ("ison-py", "1.2.0")))
    _fails(make_binding(), SRC, "CORE_RUNTIME_MISMATCH", "V0", "ison_graph/__init__.py")
    monkeypatch.setattr(v, "installed_core_runtime", lambda modules: (("ison-graph", "1.4.0"), good_hashes, ("ison-py", "1.2.0")))
    _fails(make_binding(), SRC, "CORE_RUNTIME_MISMATCH", "V0", "ison-graph")
    # ison-py implements the canonical writer both canonicality verdicts depend on: it is part of the runtime identity
    monkeypatch.setattr(v, "installed_core_runtime", lambda modules: (("ison-graph", "1.4.1"), good_hashes, ("ison-py", "1.1.0")))
    _fails(make_binding(), SRC, "CORE_RUNTIME_MISMATCH", "V0", "ison-py")


def test_v0_probe_classifies_instead_of_raising():
    # A baseline that lists a module the installed Core does not have (a future or older Core) must be a
    # mismatch, not a FileNotFoundError traceback - that is exactly the retired-baseline case (reviewer finding).
    import dataclasses
    from isongraph_ext.igx.verify import _runtime_mismatch
    odd = dataclasses.replace(B[make_binding().core_commit], core_runtime={"ison_graph/does_not_exist.py": "0" * 64})
    assert _runtime_mismatch(odd) is not None and _runtime_mismatch(odd)[0] == "ison_graph/does_not_exist.py"


def test_source_str_without_utf8_encoding_is_an_igxerror():
    e = _fails(make_binding(), "\ud800", "SOURCE_BINDING_MISMATCH", "V4")
    assert "UTF-8" in e.detail

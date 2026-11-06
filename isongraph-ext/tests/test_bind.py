import pytest
from conftest import LOSSY, RECEIPT_SHA, RETIRED, TEST_REGISTRY, all_baselines, graph_bytes

from isongraph_ext.igx.admit import AdmissionPolicy, admit
from isongraph_ext.igx.bind import bind
from isongraph_ext.igx.binding import Capability, Consumer, ExtensionBinding
from isongraph_ext.igx.errors import IGXError
from isongraph_ext.igx.verify import verify

B = all_baselines()
SRC = graph_bytes("ids/positive-int.ison")


def _raises(code, step, **kw):
    source = kw.pop("source", SRC)
    args = {"serialization_profile": "ison-v1", "producer_port": "python", "identity_claim": "producer_bound", **kw}
    with pytest.raises(IGXError) as info:
        bind(source, **args)
    assert (info.value.code, info.value.step) == (code, step), info.value
    return info.value


def test_bind_produces_verifiable_admissible_binding():
    b = bind(SRC, serialization_profile="ison-v1", producer_port="python", identity_claim="producer_bound")
    assert isinstance(b, ExtensionBinding)
    assert (b.source_canonical, b.source_semantic_eligibility, b.producer_core_posture) == ("true", "eligible", "FULL")
    assert b.core_conformance_receipt == RECEIPT_SHA["python"]
    r = verify(b, SRC)
    assert admit(b, r).admitted
    assert ExtensionBinding.from_ison(b.to_ison()) == b


def test_bind_is_deterministic():
    kw = dict(serialization_profile="ison-v1", producer_port="python", identity_claim="producer_bound")
    assert bind(SRC, **kw).digest == bind(SRC, **kw).digest


def test_bind_accepts_str_source_and_isonl():
    b = bind(graph_bytes("serialization/negative-int.isonl").decode("utf-8"), serialization_profile="isonl-v1", producer_port="python", identity_claim="artifact")
    assert b.source_canonical == "true"


def test_bind_refuses_noncanonical_python_claim():
    e = _raises("SOURCE_WRITER_MISMATCH", "V4", source=graph_bytes("serialization/non-canonical-order.ison"))
    assert e.field == "meta.source.source_canonical"


def test_bind_refuses_producer_bound_on_ineligible_source_but_allows_artifact():
    src = graph_bytes("values/int-beyond-int64.ison")
    e = _raises("IDENTITY_CLAIM_INADMISSIBLE", "A2", source=src)
    assert "SOURCE_NOT_ELIGIBLE:INTEGER_OUT_OF_INT64" in e.detail
    b = bind(src, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")
    assert (b.source_semantic_eligibility, b.source_semantic_reason) == ("ineligible", "INTEGER_OUT_OF_INT64")


def test_bind_refuses_known_defect_producer_bound():
    _raises("IDENTITY_CLAIM_INADMISSIBLE", "A2", producer_port="ts")
    b = bind(SRC, serialization_profile="ison-v1", producer_port="ts", identity_claim="artifact")
    assert (b.source_canonical, b.producer_core_posture) == ("unverified", "KNOWN_DEFECT")


def test_bind_refuses_cross_port():
    _raises("IDENTITY_CLAIM_INADMISSIBLE", "A2", identity_claim="cross_port", consumer=Consumer("ts", "1.4.1", "KNOWN_DEFECT", RECEIPT_SHA["ts"]))


def test_bind_refuses_baseline_whose_runtime_is_not_installed():
    # The retired fixture records a historical runtime; producing a binding needs the pinned implementation,
    # so bind() refuses even with allow_retired_baselines - only verify() tolerates the absence (limited mode).
    e = _raises("CORE_RUNTIME_MISMATCH", "V0", baseline=B[RETIRED], policy=AdmissionPolicy(allow_retired_baselines=True))
    assert e.field in ("ison-graph", "ison_graph/__init__.py")


def test_bind_lossy_baseline_producer_bound_reserved():
    _raises("IDENTITY_CLAIM_INADMISSIBLE", "A2", baseline=B[LOSSY])


def test_bind_unknown_required_capability():
    _raises("UNSUPPORTED_CAPABILITY", "V5", capabilities=(Capability("x-igx-test", "^1", "REQUIRED", None),))
    b = bind(SRC, serialization_profile="ison-v1", producer_port="python", identity_claim="producer_bound",
             capabilities=(Capability("x-igx-test", "^1", "REQUIRED", None),), registry=TEST_REGISTRY)
    assert b.capabilities[0].extension == "x-igx-test"


def test_bind_bad_port_is_a_shape_error():
    # Argument shape fails V1, like the same field in a parsed binding - never "missing receipt".
    e = _raises("MALFORMED_BINDING", "V1", producer_port="go")
    assert e.field == "meta.core_baseline.producer_port"
    assert _raises("MALFORMED_BINDING", "V1", identity_claim="unconditional").field == "meta.igx.identity_claim"


def test_bind_consumer_reported():
    b = bind(SRC, serialization_profile="ison-v1", producer_port="python", identity_claim="producer_bound", consumer=Consumer("ts", "1.4.1", "KNOWN_DEFECT", RECEIPT_SHA["ts"]))
    assert admit(b, verify(b, SRC)).receipt_posture == "CORE_BLOCKING_DIVERGENCE"

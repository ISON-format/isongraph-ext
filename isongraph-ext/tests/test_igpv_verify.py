import dataclasses

import pytest
from conftest import RETIRED, all_baselines
from igpv_helpers import bound, doc_bytes, origin_graph, real_payload, sha, target_graph

from isongraph_ext.igpv.errors import IGPVError
from isongraph_ext.igpv.records import Artifact, Attribution, GraphObject, Limits, Locator, NodeRef
from isongraph_ext.igpv.verify import ProvenanceVerification, verify
from isongraph_ext.igx.binding import Capability
from isongraph_ext.igx.errors import IGXError

T, O, D = target_graph(), origin_graph(), doc_bytes()
B = all_baselines()


def _ok(p=None, sources=None, **kw):
    p = p or real_payload(T, O, D)
    b = bound(p, T)
    return verify(p, b, T, sources=sources or {}, baselines=B, **kw)


def _fails(code, step, field=None, p=None, b=None, target=T, sources=None, **kw):
    p = p or real_payload(T, O, D)
    b = b or bound(p, T)
    with pytest.raises(IGPVError) as info:
        verify(p, b, target, sources=sources or {}, baselines=B, **kw)
    assert (info.value.code, info.value.step) == (code, step), info.value
    if field:
        assert info.value.field == field, info.value
    return info.value


def test_verify_ok_without_sources():
    igx, prov = _ok()
    assert igx.semantic_verification == "full" and isinstance(prov, ProvenanceVerification)
    assert prov.object_resolution == "full" and prov.origin_resolution == {"g0": "unverified"}
    assert prov.locators == {"a0": "UNVERIFIED", "a2": "UNVERIFIED"}
    assert prov.counts == {"artifacts": 2, "producers": 2, "objects": 6, "attributions": 4, "derivations": 2}
    assert prov.steps_passed == ("P0", "P1", "P2", "P3", "P4", "P5")
    assert prov.payload_sha256 == real_payload(T, O, D).digest and prov.target_artifact_sha256 == sha(T)


def test_verify_ok_with_sources_verifies_origin_and_locators():
    _igx, prov = _ok(sources={sha(O): O, sha(D): D})
    assert prov.origin_resolution == {"g0": "verified"} and prov.locators == {"a0": "VERIFIED", "a2": "VERIFIED"}


def test_payload_as_bytes_or_text_is_accepted():
    p = real_payload(T, O, D)
    b = bound(p, T)
    assert verify(p.to_ison().encode("utf-8"), b, T, baselines=B)[1].payload_sha256 == p.digest
    assert verify(p.to_ison(), b, T, baselines=B)[1].payload_sha256 == p.digest


def test_sources_keys_must_be_lowercase_hex():
    # Review Focus 2: an uppercase key is "not supplied", never a crash or a case-insensitive hit.
    _igx, prov = _ok(sources={sha(O).upper(): O, "not-hex": D})
    assert prov.origin_resolution == {"g0": "unverified"} and prov.locators["a0"] == "UNVERIFIED"


def test_origin_size_mismatch():
    # Review Focus 5: digest matches, declared size lies -> P4 SOURCE_ARTIFACT_MISMATCH on size.
    p = real_payload(T, O, D, artifacts=(Artifact("src0", sha(D), "document", len(D)), Artifact("g0", sha(O), "isongraph", len(O) + 1, serialization_profile="ison-v1")))
    _fails("SOURCE_ARTIFACT_MISMATCH", "P4", "table.artifacts.g0.size", p=p, sources={sha(O): O})


def test_p0_rules():
    p = real_payload(T, O, D)
    from isongraph_ext.igx.bind import bind as igx_bind
    no_row = igx_bind(T, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")
    _fails("PROVENANCE_NOT_BOUND", "P0", "table.capabilities.igpv", p=p, b=no_row)
    null_digest = igx_bind(T, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact", capabilities=(Capability("igpv", "^1", "OPTIONAL", None),))
    _fails("PROVENANCE_NOT_BOUND", "P0", p=p, b=null_digest)
    excl = igx_bind(T, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact", capabilities=(Capability("igpv", "=2.0.0", "OPTIONAL", p.digest),))
    _fails("PROVENANCE_VERSION_UNSUPPORTED", "P0", "table.capabilities.igpv.version_range", p=p, b=excl)
    # a different but valid payload (every row still reachable, so P1 cannot fire first)
    other = real_payload(T, O, D, attributions=real_payload(T, O, D).attributions[:3] + (Attribution("a3", "G", "src0", "x0", Locator("bytes/1", 0, 1)),))
    _fails("PAYLOAD_DIGEST_MISMATCH", "P0", "table.capabilities.igpv.payload_sha256", p=other, b=bound(p, T))
    bad = dataclasses.replace(bound(p, T), core_vector_corpus_digest="c" * 64)
    with pytest.raises(IGXError) as info:
        verify(p, bad, T, baselines=B)
    assert info.value.code == "CORPUS_DIGEST_MISMATCH"


def test_preflight_wins_over_a_bad_binding():
    p = real_payload(T, O, D)
    bad = dataclasses.replace(bound(p, T), core_vector_corpus_digest="c" * 64)
    e = _fails("PROVENANCE_LIMIT_EXCEEDED", "P1", "max_graph_bytes", p=p, b=bad, limits=Limits(max_graph_bytes=10))
    _fails("PROVENANCE_LIMIT_EXCEEDED", "P1", "max_sources_bytes", p=p, sources={sha(O): O, sha(D): D}, limits=Limits(max_sources_bytes=len(O)))
    _fails("PROVENANCE_LIMIT_EXCEEDED", "P1", "max_payload_bytes", p=p, limits=Limits(max_payload_bytes=1))
    _fails("PROVENANCE_LIMIT_EXCEEDED", "P1", "max_rows_per_table", p=p, limits=Limits(max_rows_per_table=2))
    assert "target" in e.detail


def test_preflight_precedes_programmatic_payload_shape_checks():
    # Review correction 5: the target budget is evaluated before an in-memory payload is serialized (and hence before check()).
    malformed = real_payload(T, O, D, target_artifact_sha256="AB" * 32)
    e = _fails("PROVENANCE_LIMIT_EXCEEDED", "P1", "max_graph_bytes", p=malformed, b=bound(real_payload(T, O, D), T), limits=Limits(max_graph_bytes=10))
    assert "target" in e.detail
    _fails("MALFORMED_PROVENANCE", "P1", "meta.igpv.target_artifact_sha256", p=malformed, b=bound(real_payload(T, O, D), T))


def test_graph_byte_budget_applies_to_origin_graphs_not_documents():
    # Review correction 6: max_graph_bytes bounds the target and identified origin graphs; documents are bounded only in aggregate.
    from ison_graph import ISONGraph
    g = ISONGraph()
    g.add_node("p", 7); g.add_node("p", 8); g.add_node("p", "x" * 80)      # an origin graph larger than the target
    bo = g.to_ison().encode("utf-8")
    big = D + b"#" * 400
    p = real_payload(T, bo, D, artifacts=(Artifact("src0", sha(big), "document", len(big), media_type="text/markdown"),
                                          Artifact("g0", sha(bo), "isongraph", len(bo), serialization_profile="ison-v1")))
    assert len(T) < len(big) and len(T) < len(bo)
    _igx, prov = _ok(p, sources={sha(big): big}, limits=Limits(max_graph_bytes=len(T)))
    assert prov.locators["a0"] == "VERIFIED"
    e = _fails("PROVENANCE_LIMIT_EXCEEDED", "P1", "max_graph_bytes", p=p, sources={sha(bo): bo}, limits=Limits(max_graph_bytes=len(T)))
    assert "g0" in e.detail


def test_p2_target_rules():
    p = real_payload(T, O, D)
    b = bound(p, T)
    other = T + b"\n"
    b2 = dataclasses.replace(b, artifact_sha256=sha(other))     # binding for other bytes; igx V4 passes on `other`
    _fails("TARGET_BINDING_MISMATCH", "P2", "meta.igpv.target_artifact_sha256", p=p, b=b2, target=other)
    p3 = real_payload(T, O, D, target_serialization_profile="isonl-v1")
    _fails("TARGET_BINDING_MISMATCH", "P2", "meta.igpv.target_serialization_profile", p=p3, b=bound(p3, T))


def test_p3_and_p4_and_p5_codes():
    p = real_payload(T, O, D, objects=real_payload(T, O, D).objects + (GraphObject("n9", "node", node=NodeRef("p", 9)),),
                     attributions=real_payload(T, O, D).attributions + (Attribution("a9", "n9", "src0", "x0"),))
    _fails("UNRESOLVED_OBJECT", "P4", "table.objects.n9.node_id", p=p)
    p = real_payload(T, O, D, objects=tuple(o if o.object_id != "o7" else GraphObject("o7", "node", graph="g0", node=NodeRef("p", 70)) for o in real_payload(T, O, D).objects))
    assert _ok(p)[1].origin_resolution == {"g0": "unverified"}          # not supplied: cannot be checked, reported as such
    _fails("UNRESOLVED_OBJECT", "P4", "table.objects.o7.node_id", p=p, sources={sha(O): O})
    p = real_payload(T, O, D, attributions=(Attribution("a2", "e1", "src0", "x0", Locator("lines/1", 2, 5)),) + real_payload(T, O, D).attributions[:2] + (real_payload(T, O, D).attributions[3],))
    _fails("LOCATOR_INVALID", "P5", "table.attributions.a2.locator_end", p=p, sources={sha(D): D})     # 5 <= size 35, but the document has 4 lines
    _fails("SOURCE_ARTIFACT_MISMATCH", "P5", "table.artifacts.src0.artifact_sha256", sources={sha(D): D + b"x"})
    bad_ref = real_payload(T, O, D, attributions=real_payload(T, O, D).attributions[:3] + (Attribution("a3", "G", "src0", "xX"),))
    _fails("UNRESOLVED_REFERENCE", "P3", "table.attributions.a3.producer_id", p=bad_ref)


def test_limited_mode_skips_object_resolution():
    p = real_payload(T, O, D)
    b = bound(p, T)
    retired = dataclasses.replace(b, core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256)
    igx, prov = verify(p, retired, T, sources={sha(O): O}, baselines=B)
    assert igx.semantic_verification == "limited" and prov.object_resolution == "skipped"
    assert prov.origin_resolution == {"g0": "unverified"} and prov.steps_passed == ("P0", "P1", "P2", "P3", "P4", "P5")

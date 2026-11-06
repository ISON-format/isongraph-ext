import dataclasses

import pytest
from igpv_helpers import REFERENCE_TEXT, SHA_T, payload

from isongraph_ext.igpv.errors import IGPVError
from isongraph_ext.igpv.payload import ProvenancePayload
from isongraph_ext.igpv.records import Artifact, GraphObject, Limits, NodeRef, Producer
from isongraph_ext.igx.digest import sha256_hex


def test_to_ison_matches_spec_literal_oracle():
    assert payload().to_ison() == REFERENCE_TEXT


def test_digest_is_sha256_of_bytes_and_roundtrip_is_stable():
    p = payload()
    text = p.to_ison()
    assert p.digest == sha256_hex(text.encode("utf-8"))
    q = ProvenancePayload.from_ison(text)
    assert q == p and q.to_ison() == text
    assert ProvenancePayload.from_ison(text.encode("utf-8")) == p


def test_rows_are_sorted_by_key_regardless_of_construction_order():
    p = payload()
    shuffled = dataclasses.replace(p, attributions=tuple(reversed(p.attributions)), objects=tuple(reversed(p.objects)))
    assert shuffled.to_ison() == p.to_ison()


def _rejects(text, field=None, code="MALFORMED_PROVENANCE", limits=None):
    with pytest.raises(IGPVError) as info:
        ProvenancePayload.from_ison(text, **({"limits": limits} if limits else {}))
    assert (info.value.code, info.value.step) == (code, "P1"), info.value
    if field:
        assert info.value.field == field, info.value
    return info.value


def test_noncanonical_text_rejected():
    text = payload().to_ison()
    _rejects(text + "\n", "canonical_form")
    _rejects(text.replace("\n", "\r\n"), "canonical_form")
    unsorted = text.replace("src0 a0 20 10 null bytes/1 n1 x0\nsrc0 a1 null null null null n2 x0",
                            "src0 a1 null null null null n2 x0\nsrc0 a0 20 10 null bytes/1 n1 x0")
    assert unsorted != text
    _rejects(unsorted, "canonical_form")


def test_block_rules():
    text = payload().to_ison()
    _rejects(text + "\n\nmeta.extra\na\n1", "meta.extra")
    _rejects(text.replace("table.derivations", "table.derivationz"), "table.derivationz")
    _rejects(text + "\n\nmeta.igpv\nprovenance_spec\nIGPV/1", "meta.igpv")
    _rejects(text.replace("IGPV/1", "IGPV/2"), "meta.igpv.provenance_spec")
    _rejects(text.replace(f"IGPV/1 {SHA_T} null null", f"IGPV/1 {SHA_T} {'a' * 64} sha256"), "meta.igpv.target_semantic_digest")
    _rejects(text.replace("ison-v1\n\ntable.artifacts", "ison-v9\n\ntable.artifacts"), "meta.igpv.target_serialization_profile")
    _rejects(b"\xff\xfe", "document")


def test_field_rules_programmatic():
    def bad(field, **kw):
        with pytest.raises(IGPVError) as info:
            payload(**kw).check()
        assert (info.value.code, info.value.step, info.value.field) == ("MALFORMED_PROVENANCE", "P1", field), info.value

    bad("meta.igpv.target_artifact_sha256", target_artifact_sha256="AB" * 32)
    bad("table.artifacts.src0.size", artifacts=(Artifact("src0", "1" * 64, "document", -1),))
    bad("table.artifacts.src0.size", artifacts=(Artifact("src0", "1" * 64, "document", 2**63),))
    bad("table.artifacts.src0.media_type", artifacts=(Artifact("src0", "1" * 64, "document", 1, media_type="text"),))
    bad("table.artifacts.src0.serialization_profile", artifacts=(Artifact("src0", "1" * 64, "document", 1, serialization_profile="ison-v1"),))
    bad("table.artifacts.g0.serialization_profile", artifacts=(Artifact("g0", "1" * 64, "isongraph", 1),))
    bad("table.artifacts.-x.artifact_id", artifacts=(Artifact("-x", "1" * 64, "document", 1),))
    bad("table.producers.x0.policy_sha256", producers=(Producer("x0", "extractor", "ext", "1", policy_sha256="3" * 64),))
    bad("table.producers.x0.version", producers=(Producer("x0", "extractor", "ext", ""),))
    bad("table.objects.n1.node_type", objects=(GraphObject("n1", "node", node=NodeRef("a:b", 1)),))
    bad("table.objects.n1.node_id", objects=(GraphObject("n1", "node", node=NodeRef("p", 2**63)),))
    bad("table.objects.n1.node_id", objects=(GraphObject("n1", "node", node=NodeRef("p", -(2**63) - 1)),))
    bad("table.objects.n1.node", objects=(GraphObject("n1", "node"),))
    bad("table.objects.e1.edge", objects=(GraphObject("e1", "edge", node=NodeRef("p", 1)),))
    bad("table.objects.G.node", objects=(GraphObject("G", "graph", node=NodeRef("p", 1)),))
    bad("table.derivations.d0.kind", derivations=(dataclasses.replace(payload().derivations[0], kind="merge"),))


def test_float_and_bool_ids_rejected():
    # Review Focus 1: 1.0 and true are not ids and are never coerced.
    text = payload().to_ison()
    _rejects(text.replace("null node 1 p n1", "null node 1.0 p n1"), "table.objects.n1.node_id")
    _rejects(text.replace("null node 1 p n1", "null node true p n1"), "table.objects.n1.node_id")


def test_object_null_pattern_and_locator_columns_checked_on_the_wire():
    text = payload().to_ison()
    _rejects(text.replace("null node 1 p n1 null null null null null null", "null node 1 p n1 null knows null null null null"),
             "table.objects.n1.relation")
    _rejects(text.replace("src0 a1 null null null null n2 x0", "src0 a1 5 null null null n2 x0"), "table.attributions.a1.locator_end")


def test_budgets_before_parse_and_after():
    text = payload().to_ison()
    e = _rejects(text, code="PROVENANCE_LIMIT_EXCEEDED", limits=Limits(max_payload_bytes=10))
    assert e.field == "max_payload_bytes"
    e = _rejects(text, code="PROVENANCE_LIMIT_EXCEEDED", limits=Limits(max_rows_per_table=3))
    assert e.field == "max_rows_per_table"

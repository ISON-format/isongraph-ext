import hashlib

import pytest
from conftest import RECEIPT_SHA, make_binding
from ison_parser import Block, dumps_canonical, loads

from isongraph_ext.igx.binding import Capability, Consumer, ExtensionBinding
from isongraph_ext.igx.errors import IGXError


def _malformed(text, field):
    with pytest.raises(IGXError) as info:
        ExtensionBinding.from_ison(text)
    assert (info.value.code, info.value.step) == ("MALFORMED_BINDING", "V1")
    assert info.value.field == field, info.value


def _mutate(binding, fn):
    """Apply fn(document) to the parsed canonical document and return the re-canonicalised text."""
    doc = loads(binding.to_ison())
    fn(doc)
    return dumps_canonical(doc)


def test_roundtrip_and_digest():
    b = make_binding(capabilities=(Capability("x-igx-test", "^1", "OPTIONAL", None),))
    text = b.to_ison()
    assert not text.endswith("\n")
    assert ExtensionBinding.from_ison(text) == b
    assert ExtensionBinding.from_ison(text.encode("utf-8")) == b
    assert b.digest == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_block_order_and_quoting_are_the_writers():
    text = make_binding().to_ison()
    assert text.startswith("meta.core_baseline\n")
    assert '"true"' in text and "IGX/1 producer_bound" in text


def test_consumer_block_roundtrip():
    b = make_binding(consumer=Consumer("ts", "1.4.1", "KNOWN_DEFECT", RECEIPT_SHA["ts"]))
    assert "meta.consumer\n" in b.to_ison()
    assert ExtensionBinding.from_ison(b.to_ison()) == b


def test_trailing_newline_rejected():
    _malformed(make_binding().to_ison() + "\n", "canonical_form")


def test_from_ison_rejects_crlf_text():
    # Review Focus 1
    _malformed(make_binding().to_ison().replace("\n", "\r\n"), "canonical_form")


def test_invalid_utf8_rejected():
    _malformed(b"\xff\xfe" + make_binding().to_ison().encode("utf-8"), "document")


def test_not_ison_rejected():
    # ison-py may either raise or parse garbage into some block; both paths must end in MALFORMED_BINDING/V1.
    with pytest.raises(IGXError) as info:
        ExtensionBinding.from_ison("this is not ison\n\n\n:::")
    assert (info.value.code, info.value.step) == ("MALFORMED_BINDING", "V1")


def test_duplicate_block_rejected():
    b = make_binding()
    text = _mutate(b, lambda d: d.blocks.append(Block("meta", "igx", ["binding_spec", "identity_claim"], [{"binding_spec": "IGX/1", "identity_claim": "none"}])))
    _malformed(text, "meta.igx")


def test_unexpected_block_rejected():
    text = _mutate(make_binding(), lambda d: d.blocks.append(Block("meta", "extra", ["a"], [{"a": 1}])))
    _malformed(text, "meta.extra")


def test_missing_block_rejected():
    text = _mutate(make_binding(), lambda d: d.blocks.__delitem__([i for i, x in enumerate(d.blocks) if x.name == "source"][0]))
    _malformed(text, "meta.source")


def test_missing_field_rejected():
    def drop(d):
        blk = next(x for x in d.blocks if x.name == "igx")
        blk.fields.remove("identity_claim"); blk.rows[0].pop("identity_claim")
    _malformed(_mutate(make_binding(), drop), "meta.igx.identity_claim")


def test_extra_field_rejected():
    def add(d):
        blk = next(x for x in d.blocks if x.name == "igx")
        blk.fields.append("extra"); blk.rows[0]["extra"] = 1
    _malformed(_mutate(make_binding(), add), "meta.igx.extra")


def test_two_rows_in_meta_rejected():
    def dup(d):
        blk = next(x for x in d.blocks if x.name == "igx")
        blk.rows.append(dict(blk.rows[0]))
    _malformed(_mutate(make_binding(), dup), "meta.igx")


@pytest.mark.parametrize("field,value,path", [
    ("binding_spec", "IGX/2", "meta.igx.binding_spec"),
    ("identity_claim", "unconditional", "meta.igx.identity_claim"),
    ("serialization_profile", "json", "meta.source.serialization_profile"),
    ("semantic_digest", "ab" * 32, "meta.source.semantic_digest"),
    ("semantic_digest_algorithm", "sha256", "meta.source.semantic_digest_algorithm"),
    ("core_writer_implementation", "isongraph-ts", "meta.source.core_writer_implementation"),
    ("core_writer_version", "1.4.0", "meta.source.core_writer_version"),
    ("artifact_sha256", "ABC", "meta.source.artifact_sha256"),
    ("core_commit", "ce9d3b7", "meta.core_baseline.core_commit"),
    ("core_vector_corpus_version", "1", "meta.core_baseline.core_vector_corpus_version"),
    ("producer_port", "go", "meta.core_baseline.producer_port"),
    ("producer_core_posture", "GOOD", "meta.core_baseline.producer_core_posture"),
    ("source_canonical", "false", "meta.source.source_canonical"),
    ("source_canonical", True, "meta.source.source_canonical"),
    ("source_semantic_eligibility", "maybe", "meta.source.source_semantic_eligibility"),
    ("source_semantic_reason", "INTEGER_OUT_OF_INT64", "meta.source.source_semantic_reason"),   # eligible + reason
])
def test_field_rules(field, value, path):
    b = make_binding(**{field: value})
    _malformed(b.to_ison(), path)


def test_ineligible_requires_reason_and_unclassified_forbids_it():
    _malformed(make_binding(source_semantic_eligibility="ineligible", source_semantic_reason=None).to_ison(), "meta.source.source_semantic_reason")
    _malformed(make_binding(source_semantic_eligibility="unclassified", source_semantic_reason="MULTIGRAPH_DOCUMENT").to_ison(), "meta.source.source_semantic_reason")


def test_source_canonical_token_disallowed_for_non_python():
    b = make_binding(producer_port="ts", core_writer_implementation="isongraph-ts", producer_core_posture="KNOWN_DEFECT",
                     core_conformance_receipt=RECEIPT_SHA["ts"], source_canonical="true")
    _malformed(b.to_ison(), "meta.source.source_canonical")


def test_duplicate_capability_rejected():
    # Review Focus 3
    caps = (Capability("x-igx-test", "^1", "OPTIONAL", None), Capability("x-igx-test", "^2", "REQUIRED", None))
    _malformed(make_binding(capabilities=caps).to_ison(), "table.capabilities.extension")


def test_bad_version_range_rejected():
    _malformed(make_binding(capabilities=(Capability("x-igx-test", "1.2", "OPTIONAL", None),)).to_ison(), "table.capabilities.version_range")


def test_bad_requirement_and_payload_rejected():
    _malformed(make_binding(capabilities=(Capability("x-igx-test", "^1", "MAYBE", None),)).to_ison(), "table.capabilities.requirement")
    _malformed(make_binding(capabilities=(Capability("x-igx-test", "^1", "OPTIONAL", "zz"),)).to_ison(), "table.capabilities.payload_sha256")


def test_consumer_enum_rules():
    _malformed(make_binding(consumer=Consumer("go", "1.4.1", "FULL", RECEIPT_SHA["ts"])).to_ison(), "meta.consumer.consumer_port")

"""IGX/1 wire model (17 §2) and the V1 shape rules. A binding is canonical by construction (17 §2.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import fields as dc_fields
from typing import Any

from ison_parser import Block, Document, dumps_canonical, loads

from .digest import sha256_hex
from .errors import IGXError
from .versions import parse_range

BINDING_SPEC = "IGX/1"
IDENTITY_CLAIMS = ("none", "artifact", "producer_bound", "cross_port")
PROFILES = ("ison-v1", "isonl-v1")
PORTS = ("python", "ts", "js", "rust", "cs", "cpp")
WRITER_OF_PORT = {"python": "isongraph-python", "ts": "isongraph-ts", "js": "isongraph-js", "rust": "isongraph-rs", "cs": "isongraph-cs", "cpp": "isongraph-cpp"}
POSTURES = ("FULL", "LOSSY_KNOWN", "KNOWN_DEFECT", "PARTIAL", "INCONCLUSIVE", "NONCONFORMANT")
REQUIREMENTS = ("REQUIRED", "OPTIONAL")
ELIGIBILITY = ("eligible", "ineligible", "unclassified")
REASONS = ("MULTIGRAPH_DOCUMENT", "INTEGER_OUT_OF_INT64")
CANONICAL_TOKENS = ("true", "unverified")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")

IGX_FIELDS = ("binding_spec", "identity_claim")
SOURCE_FIELDS = ("artifact_sha256", "serialization_profile", "source_canonical", "source_semantic_eligibility", "source_semantic_reason",
                 "core_writer_implementation", "core_writer_version", "semantic_digest", "semantic_digest_algorithm")
BASELINE_FIELDS = ("core_format", "core_version", "core_commit", "core_semantic_spec", "core_vector_corpus_version",
                   "core_vector_corpus_commit", "core_vector_corpus_digest", "producer_port", "producer_port_version",
                   "producer_core_posture", "core_conformance_receipt")
CAP_FIELDS = ("extension", "version_range", "requirement", "payload_sha256")
CONSUMER_FIELDS = ("consumer_port", "consumer_port_version", "consumer_core_posture", "consumer_conformance_receipt")


def _err(field: str, detail: str) -> IGXError:
    return IGXError("MALFORMED_BINDING", field, detail, "V1")


@dataclass(frozen=True)
class Capability:
    extension: str
    version_range: str
    requirement: str
    payload_sha256: str | None


@dataclass(frozen=True)
class Consumer:
    port: str
    port_version: str
    posture: str
    receipt_sha256: str


@dataclass(frozen=True)
class ExtensionBinding:
    identity_claim: str
    artifact_sha256: str
    serialization_profile: str
    source_canonical: str
    source_semantic_eligibility: str
    source_semantic_reason: str | None
    core_writer_implementation: str
    core_writer_version: str
    semantic_digest: str | None
    semantic_digest_algorithm: str | None
    core_format: str
    core_version: str
    core_commit: str
    core_semantic_spec: str
    core_vector_corpus_version: int
    core_vector_corpus_commit: str
    core_vector_corpus_digest: str
    producer_port: str
    producer_port_version: str
    producer_core_posture: str
    core_conformance_receipt: str
    capabilities: tuple[Capability, ...]
    consumer: Consumer | None
    binding_spec: str = BINDING_SPEC

    def to_document(self) -> Document:
        row = {f.name: getattr(self, f.name) for f in dc_fields(self)}
        blocks = [
            Block(kind="meta", name="igx", fields=list(IGX_FIELDS), rows=[{k: row[k] for k in IGX_FIELDS}]),
            Block(kind="meta", name="source", fields=list(SOURCE_FIELDS), rows=[{k: row[k] for k in SOURCE_FIELDS}]),
            Block(kind="meta", name="core_baseline", fields=list(BASELINE_FIELDS), rows=[{k: row[k] for k in BASELINE_FIELDS}]),
            Block(kind="table", name="capabilities", fields=list(CAP_FIELDS),
                  rows=[{"extension": c.extension, "version_range": c.version_range, "requirement": c.requirement, "payload_sha256": c.payload_sha256}
                        for c in self.capabilities]),
        ]
        if self.consumer is not None:
            c = self.consumer
            blocks.append(Block(kind="meta", name="consumer", fields=list(CONSUMER_FIELDS), rows=[{
                "consumer_port": c.port, "consumer_port_version": c.port_version, "consumer_core_posture": c.posture,
                "consumer_conformance_receipt": c.receipt_sha256}]))
        return Document(blocks=blocks)

    def to_ison(self) -> str:
        return dumps_canonical(self.to_document())

    @property
    def digest(self) -> str:
        return sha256_hex(self.to_ison())

    @classmethod
    def from_ison(cls, text: str | bytes) -> "ExtensionBinding":
        if isinstance(text, bytes):
            try:
                text = text.decode("utf-8")
            except UnicodeDecodeError as e:
                raise _err("document", f"not UTF-8: {e}") from None
        try:
            text.encode("utf-8")
        except UnicodeEncodeError as e:
            # A str with no UTF-8 encoding has no bytes and therefore no digest: it cannot be a binding.
            raise _err("document", f"text is not UTF-8-encodable: {e}") from None
        if "\r" in text:
            # ison-py would keep the CR inside the last field name and report a confusing "missing field";
            # the real fault is the line ending, which is a canonical-form fault (17 §2.1).
            raise _err("canonical_form", "CR bytes present; the canonical writer emits LF only")
        try:
            doc = loads(text)
        except Exception as e:  # ison_parser raises its own hierarchy; any parse failure is malformed
            raise _err("document", f"not ISON: {e}") from None
        blocks = _collect_blocks(doc)
        igx = _one_row(blocks, ("meta", "igx"), IGX_FIELDS)
        src = _one_row(blocks, ("meta", "source"), SOURCE_FIELDS)
        base = _one_row(blocks, ("meta", "core_baseline"), BASELINE_FIELDS)
        caps_block = blocks[("table", "capabilities")]
        if set(caps_block.fields) != set(CAP_FIELDS):
            raise _err("table.capabilities", f"fields {sorted(caps_block.fields)} != {sorted(CAP_FIELDS)}")
        caps = tuple(Capability(r["extension"], r["version_range"], r["requirement"], r["payload_sha256"]) for r in caps_block.rows)
        consumer = None
        if ("meta", "consumer") in blocks:
            c = _one_row(blocks, ("meta", "consumer"), CONSUMER_FIELDS)
            consumer = Consumer(c["consumer_port"], c["consumer_port_version"], c["consumer_core_posture"], c["consumer_conformance_receipt"])
        binding = cls(**{k: igx[k] for k in IGX_FIELDS}, **{k: src[k] for k in SOURCE_FIELDS}, **{k: base[k] for k in BASELINE_FIELDS},
                      capabilities=caps, consumer=consumer)
        check_shape(binding)
        if binding.to_ison() != text:
            raise _err("canonical_form", "binding bytes are not the canonical writer's output for this document")
        return binding


def _collect_blocks(doc: Document) -> dict[tuple[str, str], Block]:
    required = {("meta", "igx"), ("meta", "source"), ("meta", "core_baseline"), ("table", "capabilities")}
    allowed = required | {("meta", "consumer")}
    out: dict[tuple[str, str], Block] = {}
    for b in doc.blocks:
        key = (b.kind, b.name)
        if key not in allowed:
            raise _err(f"{b.kind}.{b.name}", "unexpected block")
        if key in out:
            raise _err(f"{b.kind}.{b.name}", "duplicate block")
        out[key] = b
    for key in sorted(required - set(out)):
        raise _err(f"{key[0]}.{key[1]}", "missing block")
    return out


def _one_row(blocks: dict, key: tuple[str, str], expected: tuple[str, ...]) -> dict[str, Any]:
    b = blocks[key]
    name = f"{key[0]}.{key[1]}"
    if len(b.rows) != 1:
        raise _err(name, f"expected exactly one row, got {len(b.rows)}")
    row = b.rows[0]
    for f in expected:
        if f not in row:
            raise _err(f"{name}.{f}", "missing field")
    for f in row:
        if f not in expected:
            raise _err(f"{name}.{f}", "unexpected field")
    return row


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and not isinstance(v, bool)


def check_shape(b: ExtensionBinding) -> None:
    """Semantic V1 rules on a built binding (17 §2 field rules, §4 V1)."""

    def need(cond: bool, field: str, detail: str) -> None:
        if not cond:
            raise _err(field, detail)

    need(b.binding_spec == BINDING_SPEC, "meta.igx.binding_spec", f"must be {BINDING_SPEC}")
    need(b.identity_claim in IDENTITY_CLAIMS, "meta.igx.identity_claim", f"not one of {IDENTITY_CLAIMS}")
    need(_is_str(b.artifact_sha256) and HEX64.fullmatch(b.artifact_sha256) is not None, "meta.source.artifact_sha256", "64 lowercase hex")
    need(b.serialization_profile in PROFILES, "meta.source.serialization_profile", f"not one of {PROFILES}")
    need(_is_str(b.source_canonical) and b.source_canonical in CANONICAL_TOKENS, "meta.source.source_canonical", f"not one of {CANONICAL_TOKENS}")
    need(b.source_semantic_eligibility in ELIGIBILITY, "meta.source.source_semantic_eligibility", f"not one of {ELIGIBILITY}")
    if b.source_semantic_eligibility == "ineligible":
        need(b.source_semantic_reason in REASONS, "meta.source.source_semantic_reason", f"ineligible needs one of {REASONS}")
    else:
        need(b.source_semantic_reason is None, "meta.source.source_semantic_reason", "must be null unless ineligible")
    need(b.semantic_digest is None, "meta.source.semantic_digest", "reserved: must be null until Semantic/2 freezes")
    need(b.semantic_digest_algorithm is None, "meta.source.semantic_digest_algorithm", "reserved: must be null")
    need(b.producer_port in PORTS, "meta.core_baseline.producer_port", f"not one of {PORTS}")
    need(b.core_writer_implementation == WRITER_OF_PORT[b.producer_port], "meta.source.core_writer_implementation",
         f"must be {WRITER_OF_PORT[b.producer_port]} for {b.producer_port}")
    need(_is_str(b.producer_port_version), "meta.core_baseline.producer_port_version", "string")
    need(_is_str(b.core_writer_version) and b.core_writer_version == b.producer_port_version, "meta.source.core_writer_version",
         "must equal producer_port_version")
    need(b.source_canonical == ("true" if b.producer_port == "python" else "unverified"), "meta.source.source_canonical",
         'python producers carry "true", others "unverified"')
    for f in ("core_format", "core_version", "core_semantic_spec"):
        need(_is_str(getattr(b, f)), f"meta.core_baseline.{f}", "string")
    need(_is_str(b.core_commit) and HEX40.fullmatch(b.core_commit) is not None, "meta.core_baseline.core_commit", "40 lowercase hex")
    need(isinstance(b.core_vector_corpus_version, int) and not isinstance(b.core_vector_corpus_version, bool),
         "meta.core_baseline.core_vector_corpus_version", "integer")
    need(_is_str(b.core_vector_corpus_commit) and HEX40.fullmatch(b.core_vector_corpus_commit) is not None,
         "meta.core_baseline.core_vector_corpus_commit", "40 lowercase hex")
    need(_is_str(b.core_vector_corpus_digest) and HEX64.fullmatch(b.core_vector_corpus_digest) is not None,
         "meta.core_baseline.core_vector_corpus_digest", "64 lowercase hex")
    need(b.producer_core_posture in POSTURES, "meta.core_baseline.producer_core_posture", f"not one of {POSTURES}")
    need(_is_str(b.core_conformance_receipt) and HEX64.fullmatch(b.core_conformance_receipt) is not None,
         "meta.core_baseline.core_conformance_receipt", "64 lowercase hex")
    seen: set[str] = set()
    for c in b.capabilities:
        need(_is_str(c.extension) and c.extension not in seen, "table.capabilities.extension", f"duplicate or non-string extension {c.extension!r}")
        seen.add(c.extension)
        try:
            parse_range(str(c.version_range))
        except ValueError as e:
            raise _err("table.capabilities.version_range", str(e)) from None
        need(_is_str(c.version_range), "table.capabilities.version_range", "string")
        need(c.requirement in REQUIREMENTS, "table.capabilities.requirement", f"not one of {REQUIREMENTS}")
        need(c.payload_sha256 is None or (_is_str(c.payload_sha256) and HEX64.fullmatch(c.payload_sha256) is not None),
             "table.capabilities.payload_sha256", "null or 64 lowercase hex")
    if b.consumer is not None:
        c = b.consumer
        need(c.port in PORTS, "meta.consumer.consumer_port", f"not one of {PORTS}")
        need(_is_str(c.port_version), "meta.consumer.consumer_port_version", "string")
        need(c.posture in POSTURES, "meta.consumer.consumer_core_posture", f"not one of {POSTURES}")
        need(_is_str(c.receipt_sha256) and HEX64.fullmatch(c.receipt_sha256) is not None, "meta.consumer.consumer_conformance_receipt", "64 lowercase hex")

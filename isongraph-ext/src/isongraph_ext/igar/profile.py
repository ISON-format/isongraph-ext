# isongraph-ext/src/isongraph_ext/igar/profile.py
"""IGAR/1 verifier profile (25 §2.4): the EFFECTIVE verification configuration as a canonical ISON document.

Why it exists: the same target, binding and payload bytes can verify, or be denied, differently under different limits, baseline
registries, capability registries or admission policies. A receipt therefore records `profile_sha256`, and recomputation (R6) runs
under the profile that digest names - never under whatever defaults happen to be installed. The profile carries every normative
input explicitly (no digest-only indirection): limits, the capability registry, the admission policy, and for each baseline every
field verification reads (commit, format, runtime hashes, per-port conformance receipts, domains, retirement).
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType

from ison_parser import Block, Document, dumps_canonical

from ..igdm.records import DEFAULT_LIMITS, Limits
from ..igx.admit import DEFAULT_POLICY, AdmissionPolicy
from ..igx.baselines import BASELINES, PORTS, Baseline
from ..igx.baselines import Receipt as BaselineReceipt
from ..igx.digest import sha256_hex
from ..igx.registry import DEFAULT_REGISTRY
from ..strict_ison import BlockShape, StrictError, read_canonical
from .errors import IGARError

PROFILE_SPEC = "IGAR-PROFILE/1"
LIMIT_COLS = ("max_payload_bytes", "max_graph_bytes", "max_rows_per_table", "max_group_depth")
BASELINE_COLS = ("core_commit", "core_format", "core_version", "core_semantic_spec", "corpus_version", "corpus_commit", "corpus_digest",
                 "core_runtime_dist", "core_runtime_dist_version", "canonical_writer_dist", "canonical_writer_dist_version", "retired", "adopted")
RECEIPT_COLS = ("baseline", "port", "sha256", "port_version", "posture", "receipt_core_commit", "core_format", "core_version", "corpus_commit",
                "corpus_digest", "corpus_version", "semantic_spec")
DOMAIN_COLS = ("baseline", "port", "tag")
RUNTIME_COLS = ("baseline", "module", "sha256")
SHAPES = (BlockShape("meta", "profile", ("profile_spec",), True), BlockShape("meta", "limits", LIMIT_COLS, True),
          BlockShape("meta", "admission_policy", ("allow_retired_baselines",), True), BlockShape("table", "accept_lossy_domains", ("domain",)),
          BlockShape("table", "registry", ("extension", "version")), BlockShape("table", "baselines", BASELINE_COLS),
          BlockShape("table", "baseline_receipts", RECEIPT_COLS), BlockShape("table", "baseline_domains", DOMAIN_COLS),
          BlockShape("table", "baseline_runtime", RUNTIME_COLS))
_HEX = re.compile(r"[0-9a-f]{64}")


def _bad(field: str, detail: str) -> IGARError:
    return IGARError("MALFORMED_PROFILE", field, detail, "R6")


def _tok(b: bool) -> str:
    return "true" if b else "false"


@dataclass(frozen=True)
class Profile:
    limits: Limits
    baselines: Mapping[str, Baseline]
    registry: Mapping[str, str]
    policy: AdmissionPolicy

    @classmethod
    def default(cls) -> "Profile":
        """What this installed package verifies with when the caller names nothing. Recorded in every receipt it issues."""
        return _default()

    def to_document(self) -> Document:
        lim = {c: getattr(self.limits, c) for c in LIMIT_COLS}
        bases, recs, doms, runs = [], [], [], []
        for key in sorted(self.baselines):
            b = self.baselines[key]
            bases.append({"core_commit": b.core_commit, "core_format": b.core_format, "core_version": b.core_version, "core_semantic_spec": b.core_semantic_spec,
                          "corpus_version": b.corpus_version, "corpus_commit": b.corpus_commit, "corpus_digest": b.corpus_digest,
                          "core_runtime_dist": b.core_runtime_dist[0], "core_runtime_dist_version": b.core_runtime_dist[1],
                          "canonical_writer_dist": b.canonical_writer_dist[0], "canonical_writer_dist_version": b.canonical_writer_dist[1],
                          "retired": _tok(b.retired), "adopted": b.adopted})
            for port, r in sorted(b.receipts.items()):
                recs.append({"baseline": key, "port": port, "sha256": r.sha256, "port_version": r.port_version, "posture": r.posture,
                             "receipt_core_commit": r.core_commit, "core_format": r.core_format, "core_version": r.core_version, "corpus_commit": r.corpus_commit,
                             "corpus_digest": r.corpus_digest, "corpus_version": r.corpus_version, "semantic_spec": r.semantic_spec})
            for port, tags in sorted(b.domains.items()):
                doms.extend({"baseline": key, "port": port, "tag": t} for t in sorted(tags))
            runs.extend({"baseline": key, "module": m, "sha256": h} for m, h in sorted(b.core_runtime.items()))
        return Document(blocks=[
            Block("meta", "profile", ["profile_spec"], [{"profile_spec": PROFILE_SPEC}]), Block("meta", "limits", list(LIMIT_COLS), [lim]),
            Block("meta", "admission_policy", ["allow_retired_baselines"], [{"allow_retired_baselines": _tok(self.policy.allow_retired_baselines)}]),
            Block("table", "accept_lossy_domains", ["domain"], [{"domain": d} for d in sorted(self.policy.accept_lossy_domains)]),
            Block("table", "registry", ["extension", "version"], [{"extension": k, "version": v} for k, v in sorted(self.registry.items())]),
            Block("table", "baselines", list(BASELINE_COLS), bases), Block("table", "baseline_receipts", list(RECEIPT_COLS), recs),
            Block("table", "baseline_domains", list(DOMAIN_COLS), doms), Block("table", "baseline_runtime", list(RUNTIME_COLS), runs)])

    def to_ison(self) -> str:
        return dumps_canonical(self.to_document())

    @property
    def digest(self) -> str:
        return sha256_hex(self.to_ison())

    @classmethod
    def from_ison(cls, data: bytes | str, *, max_bytes: int = DEFAULT_LIMITS.max_payload_bytes, max_rows: int = DEFAULT_LIMITS.max_rows_per_table) -> "Profile":
        """Read a profile document: byte budget first, canonical, exact blocks, then typed rebuild. Raises MALFORMED_PROFILE / RECEIPT_LIMIT_EXCEEDED."""
        try:
            text, b = read_canonical(data, SHAPES, max_bytes=max_bytes, max_rows=max_rows)
        except StrictError as e:
            if e.kind == "limit":
                raise IGARError("RECEIPT_LIMIT_EXCEEDED", "max_payload_bytes" if e.field == "size" else e.field, e.detail, "R6") from None
            raise _bad(e.field, e.detail) from None
        row = lambda n: b[("meta", n)][0]  # noqa: E731
        if row("profile")["profile_spec"] != PROFILE_SPEC:
            raise _bad("meta.profile.profile_spec", f"must be {PROFILE_SPEC}")
        lim = row("limits")
        for c in LIMIT_COLS:
            if type(lim[c]) is not int or lim[c] < 0:
                raise _bad(f"meta.limits.{c}", "non-negative integer")
        allow = row("admission_policy")["allow_retired_baselines"]
        if allow not in ("true", "false"):
            raise _bad("meta.admission_policy.allow_retired_baselines", 'the string token "true" or "false"')
        registry: dict[str, str] = {}
        for r in b[("table", "registry")]:
            if not (isinstance(r["extension"], str) and r["extension"] and isinstance(r["version"], str) and r["version"]) or r["extension"] in registry:
                raise _bad("table.registry", "unique non-empty extension / version strings")
            registry[r["extension"]] = r["version"]
        scalars: dict[str, dict] = {}
        for r in b[("table", "baselines")]:
            for c in BASELINE_COLS:
                if c in ("corpus_version",):
                    if type(r[c]) is not int:
                        raise _bad(f"table.baselines.{c}", "integer")
                elif c == "retired":
                    if r[c] not in ("true", "false"):
                        raise _bad("table.baselines.retired", 'the string token "true" or "false"')
                elif not (isinstance(r[c], str) and r[c]):
                    raise _bad(f"table.baselines.{c}", "non-empty string")
            if r["core_commit"] in scalars:
                raise _bad("table.baselines.core_commit", "duplicate baseline")
            scalars[r["core_commit"]] = r
        receipts: dict[str, dict[str, BaselineReceipt]] = {k: {} for k in scalars}
        for r in b[("table", "baseline_receipts")]:
            k, port = r["baseline"], r["port"]
            if k not in scalars or port not in PORTS or port in receipts[k]:
                raise _bad("table.baseline_receipts", f"unknown baseline, unknown port or duplicate row ({k!r}, {port!r})")
            for c in RECEIPT_COLS:
                if c == "corpus_version":
                    ok = type(r[c]) is int
                else:
                    ok = isinstance(r[c], str) and r[c] != ""
                if not ok:
                    raise _bad(f"table.baseline_receipts.{c}", "integer" if c == "corpus_version" else "non-empty string")
            if not _HEX.fullmatch(r["sha256"]):
                raise _bad("table.baseline_receipts.sha256", "64 lowercase hex")
            receipts[k][port] = BaselineReceipt(sha256=r["sha256"], port=port, port_version=r["port_version"], posture=r["posture"], core_commit=r["receipt_core_commit"],
                                                core_format=r["core_format"], core_version=r["core_version"], corpus_commit=r["corpus_commit"], corpus_digest=r["corpus_digest"],
                                                corpus_version=r["corpus_version"], semantic_spec=r["semantic_spec"])
        domains: dict[str, dict[str, set[str]]] = {k: {p: set() for p in PORTS} for k in scalars}
        for r in b[("table", "baseline_domains")]:
            if r["baseline"] not in scalars or r["port"] not in PORTS or not (isinstance(r["tag"], str) and r["tag"]) or r["tag"] in domains[r["baseline"]][r["port"]]:
                raise _bad("table.baseline_domains", "unknown baseline or port, empty tag or duplicate row")
            domains[r["baseline"]][r["port"]].add(r["tag"])
        runtime: dict[str, dict[str, str]] = {k: {} for k in scalars}
        for r in b[("table", "baseline_runtime")]:
            if r["baseline"] not in scalars or not (isinstance(r["module"], str) and r["module"]) or r["module"] in runtime[r["baseline"]] or not _HEX.fullmatch(str(r["sha256"])):
                raise _bad("table.baseline_runtime", "unknown baseline, empty module, duplicate row or sha256 not 64 lowercase hex")
            runtime[r["baseline"]][r["module"]] = r["sha256"]
        baselines: dict[str, Baseline] = {}
        for k, r in scalars.items():
            if set(receipts[k]) != set(PORTS):
                raise _bad("table.baseline_receipts", f"baseline {k} must carry a conformance receipt for every port {PORTS}")
            baselines[k] = Baseline(core_format=r["core_format"], core_version=r["core_version"], core_commit=k, core_semantic_spec=r["core_semantic_spec"],
                                    corpus_version=r["corpus_version"], corpus_commit=r["corpus_commit"], corpus_digest=r["corpus_digest"], receipts=receipts[k],
                                    domains={p: frozenset(t) for p, t in domains[k].items()}, core_runtime=runtime[k],
                                    core_runtime_dist=(r["core_runtime_dist"], r["core_runtime_dist_version"]),
                                    canonical_writer_dist=(r["canonical_writer_dist"], r["canonical_writer_dist_version"]), retired=r["retired"] == "true", adopted=r["adopted"])
        lossy = frozenset(r["domain"] for r in b[("table", "accept_lossy_domains")])
        if len(lossy) != len(b[("table", "accept_lossy_domains")]) or not all(isinstance(d, str) and d for d in lossy):
            raise _bad("table.accept_lossy_domains", "unique non-empty strings")
        p = cls(Limits(**{c: lim[c] for c in LIMIT_COLS}), MappingProxyType(baselines), MappingProxyType(registry),
                AdmissionPolicy(accept_lossy_domains=lossy, allow_retired_baselines=allow == "true"))
        if p.to_ison() != text:                                       # a second, independent canonical check over the typed model
            raise _bad("canonical_form", "document is not the canonical writer's output for this profile")
        return p


@lru_cache(maxsize=1)
def _default() -> Profile:
    return Profile(DEFAULT_LIMITS, BASELINES, DEFAULT_REGISTRY, DEFAULT_POLICY)

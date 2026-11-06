"""Bounded, read-only lineage queries across payloads (18 §5.2). Never merges, ranks, loads graphs or touches bytes."""

from __future__ import annotations

from collections.abc import Iterable

from . import records as R
from .errors import IGPVError
from .payload import ProvenancePayload, address_key, check_references

Address = R.NodeRef | R.EdgeAddress | None


def _key(obj: Address) -> tuple:
    if obj is None:
        return ("graph",)
    if isinstance(obj, R.NodeRef):
        return ("node", obj)
    return ("edge", obj)


def _bytes(s: str) -> bytes:
    return s.encode("utf-8", "surrogatepass")


class _Index:
    def __init__(self, p: ProvenancePayload) -> None:
        self.payload = p
        self.arts = {a.artifact_id: a for a in p.artifacts}
        self.prods = {x.producer_id: x for x in p.producers}
        self.objs = {o.object_id: o for o in p.objects}
        self.by_address = {address_key(o): o for o in p.objects if o.graph is None}
        self.derivations: dict[str, list[R.Derivation]] = {}
        for d in sorted(p.derivations, key=lambda d: _bytes(d.derivation_id)):
            self.derivations.setdefault(d.derived_object_id, []).append(d)
        self.attributions = sorted(p.attributions, key=lambda a: _bytes(a.attribution_id))

    def graph_sha(self, o: R.GraphObject) -> str:
        return self.payload.target_artifact_sha256 if o.graph is None else self.arts[o.graph].artifact_sha256

    @staticmethod
    def address(o: R.GraphObject) -> Address:
        return o.node if o.kind == "node" else o.edge if o.kind == "edge" else None


class Lineage:
    """Ruling (plan Task 9): the constructor runs the byte-free structural checks (P1 shape, P3 references) because an
    index cannot be built over unresolved references; nothing here touches bindings or bytes (P0, P2, P4, P5)."""

    def __init__(self, payloads: Iterable[ProvenancePayload], *, limits: R.Limits = R.DEFAULT_LIMITS) -> None:
        self._limits = limits
        self._by_target: dict[str, _Index] = {}
        for p in payloads:
            p.check()
            check_references(p)
            if p.target_artifact_sha256 in self._by_target:
                raise IGPVError("LINEAGE_AMBIGUOUS", "meta.igpv.target_artifact_sha256",
                                f"two payloads describe {p.target_artifact_sha256}; merging is not an IGPV/1 operation", "L")
            self._by_target[p.target_artifact_sha256] = _Index(p)

    def origins_of(self, graph_sha256: str, obj: Address) -> tuple[R.LineageStep, ...]:
        lim = self._limits
        steps: list[R.LineageStep] = []
        visits = 0
        # stack entries: (graph_sha, address, depth, path, kind, producer) — DFS preorder in canonical record order
        stack: list[tuple] = [(graph_sha256, obj, 0, frozenset(), None, None)]
        while stack:
            sha, address, depth, path, kind, producer = stack.pop()
            key = (sha, _key(address))
            if key in path:
                raise IGPVError("DERIVATION_CYCLE", "table.derivations", f"{address!r} in {sha} recurs on the lineage path", "L")
            visits += 1
            if visits > lim.max_lineage_visits:
                raise IGPVError("LINEAGE_BUDGET_EXCEEDED", "max_lineage_visits", f"more than {lim.max_lineage_visits} objects visited", "L")
            if depth > lim.max_lineage_depth:
                raise IGPVError("LINEAGE_BUDGET_EXCEEDED", "max_lineage_depth", f"deeper than {lim.max_lineage_depth}", "L")
            if kind is not None:
                steps.append(R.LineageStep(depth, sha, address, kind, producer, None))
            idx = self._by_target.get(sha)
            if idx is None:
                steps.append(R.LineageStep(depth, sha, address, None, None, "payload_unavailable"))
                continue
            o = idx.by_address.get(_key(address))
            rows = idx.derivations.get(o.object_id, []) if o is not None else []
            if not rows:
                steps.append(R.LineageStep(depth, sha, address, None, None, "no_derivation_record"))
                continue
            for d in reversed(rows):
                origin = idx.objs[d.origin_object_id]
                stack.append((idx.graph_sha(origin), idx.address(origin), depth + 1, path | {key}, d.kind, idx.prods[d.producer_id]))
        return tuple(steps)

    def attributions_of(self, graph_sha256: str, obj: Address) -> tuple[R.Attribution, ...]:
        idx = self._by_target.get(graph_sha256)
        if idx is None:
            return ()
        o = idx.by_address.get(_key(obj))
        if o is None:
            return ()
        return tuple(a for a in idx.attributions if a.object_id == o.object_id)

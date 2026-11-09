"""project() and verify_projection() (21 §2.7, §3, §4)."""

from __future__ import annotations

from types import MappingProxyType

from ison_graph import ISONGraph

from ..igpv import (Artifact, Attribution, Derivation, EdgeAddress, GraphObject, IGPVError, NodeRef, Producer, ProvenancePayload)
from ..igx.digest import sha256_hex
from . import policy as P
from .errors import IGPError
from .records import DEFAULT_LIMITS, IGP_IMPLEMENTATION_VERSION, IGP_SPEC, Limits, Policy, Projection
from .select import select
from .source import load_source


def _policy(policy: Policy | str | bytes, limits: Limits) -> Policy:
    if isinstance(policy, Policy):
        P.to_ison(policy, limits)                  # Q0 for in-memory policies: field rules, row budgets and the canonical byte budget
        return policy
    return P.from_ison(policy, limits=limits)


def _lineage(source: bytes, result: bytes, policy_sha: str, nodes, edges) -> ProvenancePayload:
    src = Artifact("src", sha256_hex(source), "isongraph", len(source), serialization_profile="ison-v1")
    prod = Producer("p0", "transformation", "isongraph-ext-igp", IGP_IMPLEMENTATION_VERSION, spec=IGP_SPEC, policy_sha256=policy_sha)
    if result == source:
        # Byte-identical (whole-graph) projection: IGPV/1 forbids a derivation from a graph to itself (18 §3), so the lineage is a
        # self-attribution instead (18 §1.1: a graph may cite itself). The producer row still carries the policy digest and version.
        return ProvenancePayload(sha256_hex(result), "ison-v1", artifacts=(src,), producers=(prod,), objects=(GraphObject("g0", "graph"),),
                                 attributions=(Attribution("a0", "g0", "src", "p0"),), derivations=())
    objects, derivations = [], []
    for k, (t, i) in enumerate(nodes):
        objects += [GraphObject(f"n{k}", "node", node=NodeRef(t, i)), GraphObject(f"o{k}", "node", graph="src", node=NodeRef(t, i))]
        derivations.append(Derivation(f"dn{k}", f"n{k}", f"o{k}", "p0", "identity"))
    for k, (s, r, t) in enumerate(edges):
        addr = EdgeAddress(NodeRef(*s), r, NodeRef(*t), "0")
        objects += [GraphObject(f"e{k}", "edge", edge=addr), GraphObject(f"q{k}", "edge", graph="src", edge=addr)]
        derivations.append(Derivation(f"de{k}", f"e{k}", f"q{k}", "p0", "identity"))
    return ProvenancePayload(sha256_hex(result), "ison-v1", artifacts=(src,), producers=(prod,), objects=tuple(objects), attributions=(),
                             derivations=tuple(derivations))


def project(source: bytes, policy: Policy | str | bytes, *, limits: Limits = DEFAULT_LIMITS) -> Projection:
    source = bytes(source)
    pol = _policy(policy, limits)                                         # Q0
    g = load_source(source, limits)                                       # Q1
    sel = select(g, pol)                                                  # Q2
    keep_nodes, keep_edges = set(sel.nodes), set(sel.edges)
    out = ISONGraph(directed=True)                                        # rebuild, never delete from a copy (21 §2.7)
    for n in g.nodes():
        if (n.type, n.id) in keep_nodes:
            out.add_node(n.type, n.id, **n.properties)
    for e in g.edges():
        if (e.source, e.rel_type, e.target) in keep_edges:
            out.add_edge(e.rel_type, e.source, e.target, **e.properties)
    result = out.to_ison().encode("utf-8")
    rows = 1 if result == source else 2 * (len(sel.nodes) + len(sel.edges))      # Q3: lineage limits (21 §3.2)
    if rows > limits.lineage.max_rows_per_table:
        raise IGPError("PROJECTION_LIMIT_EXCEEDED", "max_rows_per_table", f"{rows} lineage object rows > {limits.lineage.max_rows_per_table}", "Q3")
    payload = _lineage(source, result, P.digest(pol), sel.nodes, sel.edges)
    try:
        size = len(payload.to_ison().encode("utf-8"))
    except IGPVError as e:                                                # cannot happen for a well-formed projection; surface it
        raise IGPError("PROJECTION_LIMIT_EXCEEDED", "lineage", str(e), "Q3") from None
    if size > limits.lineage.max_payload_bytes:
        raise IGPError("PROJECTION_LIMIT_EXCEEDED", "max_payload_bytes", f"lineage payload {size} > {limits.lineage.max_payload_bytes}", "Q3")
    return Projection(result, payload, P.digest(pol), MappingProxyType(dict(sel.stats)))


def verify_projection(source: bytes, policy: Policy | str | bytes, result: bytes, payload: str | bytes | ProvenancePayload, *,
                      limits: Limits = DEFAULT_LIMITS) -> Projection:
    proj = project(source, policy, limits=limits)                         # Q0-Q3 first, so their errors take precedence over any Q4 error
    try:                                                                  # Q4: the supplied lineage must parse ...
        supplied = payload if isinstance(payload, ProvenancePayload) else ProvenancePayload.from_ison(payload, limits=limits.lineage)
        supplied_text = supplied.to_ison()
    except IGPVError as e:
        raise IGPError("LINEAGE_MISMATCH", "payload", f"unparseable lineage payload: {e}", "Q4") from None
    versions = [p.version for p in supplied.producers if p.spec == IGP_SPEC]          # ... name this implementation version ...
    if versions != [IGP_IMPLEMENTATION_VERSION]:
        raise IGPError("IMPLEMENTATION_VERSION_MISMATCH", "table.producers.version",
                       f"payload records {versions}, this implementation is {IGP_IMPLEMENTATION_VERSION}", "Q4")
    if proj.result_bytes != bytes(result):                                # ... and both outputs must equal the recomputation, result first
        raise IGPError("RESULT_MISMATCH", "result", "recomputed result bytes differ from the supplied result", "Q4")
    if proj.payload.to_ison() != supplied_text:
        raise IGPError("LINEAGE_MISMATCH", "payload", "recomputed lineage payload differs from the supplied payload", "Q4")
    return proj

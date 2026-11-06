"""Institutional decision/evidence graph (IGX + IGPV): no software-engineering vocabulary.

Consumer scenario with no software-engineering vocabulary: board minutes and a facilities report are the
sources; decisions, evidence and a meeting are the graph. A raw extraction graph is curated into a target
graph (two duplicate decision rows collapse into one). The probe uses ONLY ISONGraph Core, isongraph_ext.igx
and isongraph_ext.igpv through their public APIs, plus the igpv CLI. Deterministic; exits 0 on success.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile

from ison_graph import ISONGraph
from ison_parser import loads

from isongraph_ext import igpv, igx
from isongraph_ext.igpv import (Artifact, Attribution, Derivation, EdgeAddress, GraphObject, IGPVError, Lineage, Locator,
                                NodeRef, Producer, ProvenancePayload)
from isongraph_ext.igx import Capability, EMPTY_REGISTRY, IGXError

sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
findings: list[str] = []


def note(msg: str) -> None:
    findings.append(msg)
    print("  -", msg)


# ---- sources (plain documents) --------------------------------------------------------------------------
MINUTES = (b"Board minutes 2026-03-12\n"
           b"\n"
           b"Item 4: Proposal to relocate the archive.\n"
           b"Decision: approved, 5-2.\n"
           b"Evidence: facilities report FR-19; cost memo CM-3.\n")
REPORT = b"Facilities report FR-19\nThe current archive building fails the humidity standard.\n"

# ---- origin graph: raw extraction (duplicate decision rows) ---------------------------------------------
raw = ISONGraph()
raw.add_node("decision", "D-4", title="Relocate the archive")
raw.add_node("decision", "D-4-dup", title="relocate archive (dup)")
raw.add_node("evidence", "FR-19")
raw.add_node("evidence", "CM-3")
raw.add_edge("supports", ("evidence", "FR-19"), ("decision", "D-4"))
raw.add_edge("supports", ("evidence", "CM-3"), ("decision", "D-4-dup"))
RAW = raw.to_ison().encode("utf-8")

# ---- target graph: curated -------------------------------------------------------------------------------
cur = ISONGraph()
cur.add_node("decision", "D-4", title="Relocate the archive", outcome="approved", vote="5-2")
cur.add_node("evidence", "FR-19")
cur.add_node("evidence", "CM-3")
cur.add_node("meeting", "2026-03-12")
cur.add_edge("supports", ("evidence", "FR-19"), ("decision", "D-4"))
cur.add_edge("supports", ("evidence", "CM-3"), ("decision", "D-4"))
cur.add_edge("decided_at", ("decision", "D-4"), ("meeting", "2026-03-12"))
CUR = cur.to_ison().encode("utf-8")

READER = Producer("minutes-reader", "extractor", "probe-a-minutes-reader", "0.0.1")
DEDUPE = Producer("dedupe", "transformation", "probe-a-curation", "0.0.1")

# provenance of the raw graph: every node attributed to the minutes by line; FR-19 also to the report
p_raw = ProvenancePayload(
    sha(RAW), "ison-v1",
    artifacts=(Artifact("minutes", sha(MINUTES), "document", len(MINUTES), media_type="text/plain"),
               Artifact("report", sha(REPORT), "document", len(REPORT), media_type="text/plain")),
    producers=(READER,),
    objects=(GraphObject("d4", "node", node=NodeRef("decision", "D-4")),
             GraphObject("d4dup", "node", node=NodeRef("decision", "D-4-dup")),
             GraphObject("fr19", "node", node=NodeRef("evidence", "FR-19")),
             GraphObject("cm3", "node", node=NodeRef("evidence", "CM-3"))),
    attributions=(Attribution("a1", "d4", "minutes", "minutes-reader", Locator("lines/1", 3, 4)),
                  Attribution("a2", "d4dup", "minutes", "minutes-reader", Locator("lines/1", 4, 4)),
                  Attribution("a3", "fr19", "minutes", "minutes-reader", Locator("lines/1", 5, 5)),
                  Attribution("a4", "fr19", "report", "minutes-reader", Locator("lines/1", 1, 1)),
                  Attribution("a5", "cm3", "minutes", "minutes-reader", Locator("lines/1", 5, 5))),
)

# provenance of the curated graph: D-4 collapses two raw rows; the meeting edge is attributed to the minutes
p_cur = ProvenancePayload(
    sha(CUR), "ison-v1",
    artifacts=(Artifact("raw", sha(RAW), "isongraph", len(RAW), serialization_profile="ison-v1"),
               Artifact("minutes", sha(MINUTES), "document", len(MINUTES), media_type="text/plain")),
    producers=(READER, DEDUPE),
    objects=(GraphObject("d4", "node", node=NodeRef("decision", "D-4")),
             GraphObject("r1", "node", graph="raw", node=NodeRef("decision", "D-4")),
             GraphObject("r2", "node", graph="raw", node=NodeRef("decision", "D-4-dup")),
             GraphObject("e1", "edge", edge=EdgeAddress(NodeRef("decision", "D-4"), "decided_at", NodeRef("meeting", "2026-03-12")))),
    attributions=(Attribution("a1", "e1", "minutes", "minutes-reader", Locator("lines/1", 1, 1)),),
    derivations=(Derivation("x1", "d4", "r1", "dedupe", "collapse"), Derivation("x2", "d4", "r2", "dedupe", "collapse")),
)

print("Institutional decision/evidence graph")
SOURCES = {sha(RAW): RAW, sha(MINUTES): MINUTES, sha(REPORT): REPORT}
KW = dict(serialization_profile="ison-v1", producer_port="python")

# 1. producer path: bind each graph with its provenance, strongest admissible identity claim
b_raw = igpv.bind(RAW, p_raw, identity_claim="producer_bound", sources=SOURCES, **KW)
b_cur = igpv.bind(CUR, p_cur, identity_claim="producer_bound", sources=SOURCES, **KW)
note(f"bind(): both graphs bound with identity_claim=producer_bound; igpv rows = "
     f"{[(c.extension, c.version_range, c.requirement) for c in b_cur.capabilities]}")

# 2. consumer path with sources: full verification + admission
res, prov, dec = igpv.verify_and_admit(p_cur, b_cur, CUR, sources=SOURCES)
assert dec.admitted and res.semantic_verification == "full", (dec, res)
assert prov.locators == {"a1": "VERIFIED"} and prov.origin_resolution == {"raw": "verified"}, prov
note(f"verify_and_admit(curated, sources): admitted={dec.admitted} steps={prov.steps_passed} "
     f"locators={dict(prov.locators)} origins={dict(prov.origin_resolution)}")
res2, prov2, dec2 = igpv.verify_and_admit(p_raw, b_raw, RAW, sources=SOURCES)
assert dec2.admitted and prov2.locators == {f"a{i}": "VERIFIED" for i in range(1, 6)}, prov2
note("verify_and_admit(raw, sources): admitted, 5/5 line locators VERIFIED against the minutes and the report")

# 3. consumer path without sources: provenance still verifies, posture is honest
_r, prov3, dec3 = igpv.verify_and_admit(p_cur, b_cur, CUR)
assert dec3.admitted and prov3.locators == {"a1": "UNVERIFIED"} and prov3.origin_resolution == {"raw": "unverified"}
note("verify_and_admit(curated, no sources): admitted; locator and origin posture reported UNVERIFIED, not guessed")

# 4. tampered source: one byte changed in the minutes -> rejected with the artifact named
tampered = MINUTES.replace(b"5-2", b"4-3")
try:
    igpv.verify_and_admit(p_raw, b_raw, RAW, sources={sha(MINUTES): tampered})
    raise AssertionError("tampered minutes accepted")
except IGPVError as e:
    assert e.code == "SOURCE_ARTIFACT_MISMATCH", e
    note(f"tampered minutes: {e}")

# 5. lineage across two payloads, no graphs loaded
lin = Lineage([p_cur, p_raw])
steps = lin.origins_of(sha(CUR), NodeRef("decision", "D-4"))
kinds = [(s.depth, s.obj, s.kind, s.terminal) for s in steps]
assert [k[2] for k in kinds] == ["collapse", None, "collapse", None], kinds
assert all(k[3] == "no_derivation_record" for k in kinds if k[2] is None), kinds
att = lin.attributions_of(sha(RAW), NodeRef("decision", "D-4-dup"))
assert [a.attribution_id for a in att] == ["a2"], att
note(f"Lineage.origins_of(curated D-4): {len(steps)} steps -> two raw rows, each terminal no_derivation_record; "
     f"attributions_of(raw D-4-dup) -> {[(a.artifact_id, a.locator.type, a.locator.start, a.locator.end) for a in att]}")

# 6. a consumer that knows nothing about provenance (registry empty)
b_plain = igx.bind(CUR, identity_claim="artifact", **KW)
r_plain, d_plain = igx.verify_and_admit(b_plain, CUR)
assert d_plain.admitted
note("Core-only consumer: a binding with no capability rows verifies and admits (provenance is optional)")
b_opt = igpv.bind(CUR, p_cur, requirement="OPTIONAL", identity_claim="artifact", **KW)
r_opt = igx.verify(b_opt, CUR, registry=EMPTY_REGISTRY)
assert [c.extension for c in r_opt.unrecognized_optional] == ["igpv"]
note("unknown-consumer with OPTIONAL igpv row: IGX verifies, reports igpv as unrecognized_optional")
try:
    igx.verify(b_cur, CUR, registry=EMPTY_REGISTRY)
    raise AssertionError("REQUIRED igpv accepted by a consumer that lacks it")
except IGXError as e:
    note(f"unknown-consumer with REQUIRED igpv row: {e.step} {e.code} (fails closed)")

# 7. the CLI path an independent developer would script
with tempfile.TemporaryDirectory() as td:
    d = pathlib.Path(td)
    (d / "curated.ison").write_bytes(CUR)
    (d / "curated.igx.ison").write_bytes(b_cur.to_ison().encode("utf-8"))
    (d / "curated.igpv.ison").write_bytes(p_cur.to_ison().encode("utf-8"))
    (d / "raw.igpv.ison").write_bytes(p_raw.to_ison().encode("utf-8"))
    (d / "raw.ison").write_bytes(RAW)
    (d / "minutes.txt").write_bytes(MINUTES)
    env = {**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "")}
    cmd = [sys.executable, "-m", "isongraph_ext.igpv", "verify", str(d / "curated.ison"), str(d / "curated.igx.ison"),
           str(d / "curated.igpv.ison"), "--source", f"{sha(RAW)}={d / 'raw.ison'}", "--source", f"{sha(MINUTES)}={d / 'minutes.txt'}"]
    p = subprocess.run(cmd, capture_output=True, env=env)
    assert p.returncode == 0, p.stderr
    blocks = {b.name: b.rows[0] for b in loads(p.stdout.decode("utf-8")).blocks}
    assert blocks["admission"]["admitted"] is True and blocks["provenance"]["locators"] == "a1=VERIFIED", blocks
    cmd = [sys.executable, "-m", "isongraph_ext.igpv", "origins", sha(CUR), str(d / "curated.igpv.ison"), str(d / "raw.igpv.ison"),
           "--node", "decision", "D-4"]
    p = subprocess.run(cmd, capture_output=True, env=env)
    assert p.returncode == 0, p.stderr
    rows = [b for b in loads(p.stdout.decode("utf-8")).blocks if b.name == "lineage"][0].rows
    assert len(rows) == 4, rows
    note(f"CLI: verify exit 0 with three ISON blocks; origins exit 0 with {len(rows)} lineage rows")

# 8. hygiene: which non-stdlib modules did this consumer need?
third = sorted({m.split(".")[0] for m in sys.modules} - set(sys.stdlib_module_names) - {"__main__"})
third = [m for m in third if not m.startswith("_")]
note(f"non-stdlib modules loaded: {third}")
print("OK: institutional_evidence")

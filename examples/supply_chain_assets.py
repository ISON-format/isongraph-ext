"""Supply-chain asset graph (IGX + IGDM): no software-engineering vocabulary.

Consumer scenario with no software-engineering vocabulary: suppliers, facilities and components; a regional
hull, a bill-of-materials hierarchy, a collapsed sub-assembly, visual states for an audit and a new part.
Uses ONLY ISONGraph Core, isongraph_ext.igx and isongraph_ext.igdm through their public APIs, plus the igdm CLI.
Deterministic; exits 0 on success. Also records what the contract can NOT express.
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

from isongraph_ext import igdm, igx
from isongraph_ext.igdm import (DatamaticsPayload, EdgeAddress, EdgeHints, Group, IGDMError, LayoutHints, Member, NodeHints,
                                NodeRef)
from isongraph_ext.igx import Capability, EMPTY_REGISTRY

sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
findings: list[str] = []
cannot: list[str] = []


def note(msg: str) -> None:
    findings.append(msg)
    print("  -", msg)


def limit(msg: str) -> None:
    cannot.append(msg)
    print("  ! cannot:", msg)


# ---- the asset graph (Core only) -------------------------------------------------------------------------
g = ISONGraph()
for sid, name, region in (("S-ACME", "Acme Castings", "emea"), ("S-NORD", "Nord Seals", "emea"), ("S-PAC", "Pacific Motors", "apac")):
    g.add_node("supplier", sid, name=name, region=region)
g.add_node("facility", "F-LYON", region="emea")
g.add_node("facility", "F-OSAKA", region="apac")
for cid in ("C-PUMP", "C-HOUSING", "C-SEAL", "C-MOTOR", "C-ROTOR", "C-STATOR"):
    g.add_node("component", cid)
g.add_edge("supplies", ("supplier", "S-ACME"), ("facility", "F-LYON"))
g.add_edge("supplies", ("supplier", "S-NORD"), ("facility", "F-LYON"))
g.add_edge("supplies", ("supplier", "S-PAC"), ("facility", "F-OSAKA"))
g.add_edge("produces", ("facility", "F-LYON"), ("component", "C-HOUSING"))
g.add_edge("produces", ("facility", "F-LYON"), ("component", "C-SEAL"))
g.add_edge("produces", ("facility", "F-OSAKA"), ("component", "C-MOTOR"))
for part in ("C-HOUSING", "C-SEAL", "C-MOTOR"):
    g.add_edge("depends_on", ("component", "C-PUMP"), ("component", part))
for part in ("C-ROTOR", "C-STATOR"):
    g.add_edge("depends_on", ("component", "C-MOTOR"), ("component", part))
G = g.to_ison().encode("utf-8")
N = lambda t, i: NodeRef(t, i)  # noqa: E731

payload = DatamaticsPayload(
    sha(G), "ison-v1",
    layout=LayoutHints(family="layered", direction="LR", stability="stable"),
    nodes=(
        # magnitude MUST be normalised to [0, 1] by the producer (19 §1.1): annual volumes 1.25M / 0.31M / 0.98M become
        # 1.0 / 0.25 / 0.78 -- the unit and the absolute values do not travel (recorded under "cannot" below)
        NodeHints(N("supplier", "S-ACME"), role="warning", badge="audit", magnitude=1.0, a11y_text="Acme Castings, under audit",
                  ring="x-supplier-audit"),                                            # custom ring token, reported not rejected
        NodeHints(N("supplier", "S-NORD"), role="neutral", magnitude=0.25),
        NodeHints(N("supplier", "S-PAC"), role="neutral", magnitude=0.78),
        NodeHints(N("facility", "F-LYON"), shape_role="process", emphasis="high", layout_anchor=True, layout_rank=1),
        NodeHints(N("facility", "F-OSAKA"), shape_role="process", layout_rank=1),
        NodeHints(N("component", "C-PUMP"), role="selected", expandable=True, drilldown=True, label="Pump assembly P-100"),
        NodeHints(N("component", "C-STATOR"), temporal_state="introduced", temporal_order=3, badge="new"),
        NodeHints(N("component", "C-SEAL"), visibility="visible", lod_min=2),
    ),
    edges=(
        EdgeHints(EdgeAddress(N("supplier", "S-PAC"), "supplies", N("facility", "F-OSAKA")), pattern_role="dashed", label="provisional"),
        EdgeHints(EdgeAddress(N("component", "C-PUMP"), "depends_on", N("component", "C-MOTOR")), emphasis="high", direction_display="forward"),
    ),
    groups=(
        Group("emea", "hull", label="EMEA", role="info"),
        Group("apac", "hull", label="APAC"),
        Group("bom-pump", "hierarchy", label="P-100 bill of materials"),
        Group("bom-motor", "hierarchy", parent_group_id="bom-pump", label="Motor sub-assembly"),
        Group("motor-fold", "collapse", collapsed=True, label="Motor (collapsed)", a11y_text="Motor sub-assembly, collapsed"),
    ),
    members=(
        Member("emea", N("supplier", "S-ACME")), Member("emea", N("supplier", "S-NORD")), Member("emea", N("facility", "F-LYON")),
        Member("apac", N("supplier", "S-PAC")), Member("apac", N("facility", "F-OSAKA")),
        Member("bom-pump", N("component", "C-PUMP")), Member("bom-pump", N("component", "C-HOUSING")), Member("bom-pump", N("component", "C-SEAL")),
        Member("bom-motor", N("component", "C-MOTOR")), Member("bom-motor", N("component", "C-ROTOR")), Member("bom-motor", N("component", "C-STATOR")),
        Member("motor-fold", N("component", "C-ROTOR")), Member("motor-fold", N("component", "C-STATOR")),
    ),
)

print("Supply-chain asset graph")
KW = dict(serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")

# 1. producer path, with a product-private capability riding alongside (consumer-opaque)
b = igdm.bind(G, payload, capabilities=(Capability("x-asset-ledger", "^1", "OPTIONAL", None),), **KW)
note(f"bind(): rows = {[(c.extension, c.requirement) for c in b.capabilities]}")

# 2. consumer path
res, dm, dec = igdm.verify_and_admit(payload, b, G)
assert dec.admitted and dm.object_resolution == "full", (dec, dm)
assert dm.unrecognized_roles == ("nodes.ring:x-supplier-audit",), dm.unrecognized_roles
note(f"verify_and_admit: admitted, steps={dm.steps_passed}, counts={dict(dm.counts)}, unrecognized_roles={dm.unrecognized_roles}")

# 3. wire round-trip and digest stability
text = payload.to_ison()
again = DatamaticsPayload.from_ison(text)
assert again == payload and again.to_ison() == text and sha(text.encode("utf-8")) == payload.digest
note(f"wire: {len(text.encode('utf-8'))} bytes, round-trip equal, digest == sha256(bytes)")

# 4. a hint for a node that is not in the graph is caught at D4 (hints never invent topology)
ghost = DatamaticsPayload(sha(G), "ison-v1", nodes=(NodeHints(N("component", "C-GHOST"), role="negative"),))
try:
    igdm.verify_and_admit(ghost, igx.bind(G, capabilities=(Capability("igdm", "^1", "REQUIRED", ghost.digest),), **KW), G)
    raise AssertionError("ghost node accepted")
except IGDMError as e:
    note(f"hint for an absent node: {e.step} {e.code} {e.field}")

# 5. group rules: a node in both a collapse group and an aggregate group
try:
    DatamaticsPayload(sha(G), "ison-v1",
                      groups=(Group("a", "collapse"), Group("b", "aggregate")),
                      members=(Member("a", N("component", "C-ROTOR")), Member("b", N("component", "C-ROTOR")))).to_ison()
    raise AssertionError("exclusivity not enforced")
except IGDMError as e:
    note(f"collapse+aggregate on one node: {e.step} {e.code} {e.field}")
# a node in two hulls is fine (hulls may overlap)
DatamaticsPayload(sha(G), "ison-v1", groups=(Group("a", "hull"), Group("b", "hull")),
                  members=(Member("a", N("component", "C-ROTOR")), Member("b", N("component", "C-ROTOR")))).to_ison()
note("one node in two hull groups: accepted (overlapping regions are expressible)")

# 6. what a consumer that does not know datamatics sees
r_opt = igx.verify(igdm.bind(G, payload, requirement="OPTIONAL", **KW), G, registry=EMPTY_REGISTRY)
assert [c.extension for c in r_opt.unrecognized_optional] == ["igdm"]
note("consumer without igdm: OPTIONAL row is reported unrecognized, graph still verifies and loads with Core alone")
plain = igx.bind(G, **KW)
assert igx.verify_and_admit(plain, G)[1].admitted
note("graph with no datamatics at all: binds and admits; Visualize-side defaults are the consumer's business")

# 7. CLI
with tempfile.TemporaryDirectory() as td:
    d = pathlib.Path(td)
    (d / "assets.ison").write_bytes(G)
    (d / "assets.igx.ison").write_bytes(b.to_ison().encode("utf-8"))
    (d / "assets.igdm.ison").write_bytes(text.encode("utf-8"))
    env = {**os.environ}
    p = subprocess.run([sys.executable, "-m", "isongraph_ext.igdm", "verify", str(d / "assets.ison"), str(d / "assets.igx.ison"),
                        str(d / "assets.igdm.ison")], capture_output=True, env=env)
    assert p.returncode == 0, p.stderr
    blocks = {bl.name: bl.rows[0] for bl in loads(p.stdout.decode("utf-8")).blocks}
    assert blocks["admission"]["admitted"] is True and blocks["datamatics"]["unrecognized_roles"] == "nodes.ring:x-supplier-audit", blocks
    note("CLI: verify exit 0; datamatics block reports the custom token")

# 7b. optional: leave the three artifacts on disk (supply_chain_assets.py --write DIR), e.g. as input for igdm_to_svg.py
if "--write" in sys.argv:
    if sys.argv.index("--write") + 1 >= len(sys.argv):
        sys.exit("usage: supply_chain_assets.py [--write DIR]")
    out = pathlib.Path(sys.argv[sys.argv.index("--write") + 1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "assets.ison").write_bytes(G)
    (out / "assets.igx.ison").write_bytes(b.to_ison().encode("utf-8"))
    (out / "assets.igdm.ison").write_bytes(text.encode("utf-8"))
    note(f"wrote assets.ison, assets.igx.ison, assets.igdm.ison to {out}")

# 8. what the contract cannot say (recorded, not asserted away)
limit("edges cannot be group members (table.members carries node_type/node_id only)")
limit("a hint cannot target a node TYPE or a relation as a class; every hint is per object (no 'all suppliers are circles')")
limit("magnitude is one scalar per node, already normalised to [0,1] (absolute values such as 1,250,000 units are rejected at D1); no units, no second measure, no edge magnitude")
limit("custom (x-) tokens are allowed only in role/ring/a11y_role/shape_role/pattern_role/family, not in temporal_state, visibility, emphasis")
limit("no per-node position; layout intent stops at family/direction/stability/rank/anchor (by design: Visualize owns coordinates)")

third = sorted({m.split(".")[0] for m in sys.modules} - set(sys.stdlib_module_names) - {"__main__"})
note(f"non-stdlib modules loaded: {[m for m in third if not m.startswith('_')]}")
print("OK: supply_chain_assets")

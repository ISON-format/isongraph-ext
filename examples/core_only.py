"""Core-only consumer: ISONGraph Core with no extension installed or imported, no companion file read.

A graph that carries companions (.igx.ison / .igpv.ison / .igdm.ison) is still an ordinary ISONGraph. A consumer that does not
care about binding, provenance or presentation parses it exactly as before and pays exactly a Core parse.

    python core_only.py [GRAPH.ison]      # default: a small built-in supplier graph
"""
from __future__ import annotations

import sys
import time

from ison_graph import ISONGraph


def main(argv: list[str]) -> int:
    if argv:
        with open(argv[0], encoding="utf-8") as f:
            text = f.read()
    else:
        g0 = ISONGraph()
        g0.add_node("component", "C-PUMP", name="Pump")
        g0.add_node("component", "C-HOUSING", name="Housing")
        g0.add_node("component", "C-SEAL", name="Seal")
        g0.add_edge("depends_on", ("component", "C-PUMP"), ("component", "C-HOUSING"))
        g0.add_edge("depends_on", ("component", "C-PUMP"), ("component", "C-SEAL"))
        text = g0.to_ison()
    t = time.perf_counter()
    g = ISONGraph.from_ison(text)
    parse_s = time.perf_counter() - t
    print(f"nodes={g.node_count()} edges={g.edge_count()} core_parse_s={parse_s:.4f}")
    pump = next((n for n in g.nodes() if n.id == "C-PUMP"), next(iter(g.nodes())))
    print(f"{pump.type}:{pump.id} depends on {sorted(str(n) for n in g.neighbors((pump.type, pump.id)))}")
    assert "isongraph_ext" not in sys.modules, "a Core-only consumer must not load the extension package"
    print("OK: core_only (isongraph_ext not imported)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

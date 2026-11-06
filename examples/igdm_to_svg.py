"""A deliberately minimal, generic IGDM/1 -> static SVG adapter.

This is a demonstration that IGDM/1 is consumable by something that knows only the closed IGDM/1 vocabulary. It is NOT
a renderer and NOT ISONGraph Visualize: positions come from a fixed grid, shapes are basic SVG, there is no layout
engine, no interaction, no theme system. Unknown `x-` tokens are treated as "no hint" for that column and never
interpreted. Standard library for SVG; Core and Ext only for parsing and verification.

    python igdm_to_svg.py GRAPH BINDING PAYLOAD OUT.svg
"""
from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

from ison_graph import ISONGraph

from isongraph_ext import igdm
from isongraph_ext.igdm import DatamaticsPayload, EdgeAddress, NodeRef
from isongraph_ext.igx import ExtensionBinding

CELL_W, CELL_H, MARGIN, COLS, R = 180, 110, 60, 4, 22
# Static mapping of the CLOSED role vocabulary (19 section 1.2). Anything else, including every x- token, is "no hint".
FILL = {"neutral": "#e5e7eb", "active": "#bfdbfe", "inactive": "#f3f4f6", "selected": "#fde68a", "warning": "#fed7aa",
        "negative": "#fecaca", "positive": "#bbf7d0", "info": "#c7d2fe", "emphasis-high": "#ddd6fe", "emphasis-low": "#f9fafb"}
SHAPES = ("circle", "square", "diamond", "hexagon", "triangle", "pill", "document", "person", "process")
STROKE = {"none": 1, "low": 1, "medium": 2, "high": 4}


def _known(value, closed):
    return value if value in closed else None          # x-* and anything unrecognised -> no hint


def _node_key(ref) -> tuple:
    t, i = ref
    return (t, 0, i, "") if isinstance(i, int) else (t, 1, 0, i)


def _shape(shape, x, y, fill, sw) -> str:
    a = f'fill="{fill}" stroke="#374151" stroke-width="{sw}"'
    if shape == "square":
        return f'<rect x="{x - R}" y="{y - R}" width="{2 * R}" height="{2 * R}" {a}/>'
    if shape == "diamond":
        return f'<polygon points="{x},{y - R} {x + R},{y} {x},{y + R} {x - R},{y}" {a}/>'
    if shape == "triangle":
        return f'<polygon points="{x},{y - R} {x + R},{y + R} {x - R},{y + R}" {a}/>'
    if shape == "hexagon":
        h = R // 2
        return f'<polygon points="{x - R},{y} {x - h},{y - R} {x + h},{y - R} {x + R},{y} {x + h},{y + R} {x - h},{y + R}" {a}/>'
    if shape in ("pill", "process", "document", "person"):      # one basic stand-in for the rest of the closed set
        return f'<rect x="{x - R - 10}" y="{y - R + 6}" width="{2 * R + 20}" height="{2 * R - 12}" rx="{R - 6}" {a}/>'
    return f'<circle cx="{x}" cy="{y}" r="{R}" {a}/>'


def render(graph_bytes: bytes, payload: DatamaticsPayload) -> str:
    """Pure function: same inputs, same SVG text. Assumes the payload was already verified against the graph."""
    g = ISONGraph.from_ison(graph_bytes.decode("utf-8"))
    hints = {(h.node.node_type, h.node.node_id): h for h in payload.nodes}
    ehints = {e.edge: e for e in payload.edges}

    def rank(r):
        h = hints.get(r)
        return h.layout_rank if h is not None and h.layout_rank is not None else 1 << 30

    refs = sorted(((n.type, n.id) for n in g.nodes()), key=lambda r: (rank(r), _node_key(r)))
    shown = [r for r in refs if not (r in hints and hints[r].visibility in ("hidden", "collapsed"))]
    pos = {r: (MARGIN + (i % COLS) * CELL_W, MARGIN + (i // COLS) * CELL_H) for i, r in enumerate(shown)}
    rows = (len(shown) + COLS - 1) // COLS
    w = MARGIN * 2 + (min(COLS, max(len(shown), 1)) - 1) * CELL_W
    h = MARGIN * 2 + max(rows - 1, 0) * CELL_H + 30
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="11">',
           '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#374151"/></marker></defs>']
    members: dict[str, list] = {}
    for m in payload.members:
        members.setdefault(m.group_id, []).append((m.node.node_type, m.node.node_id))
    for grp in payload.groups:                       # hull groups only: a labelled box around the visible members
        pts = [pos[r] for r in members.get(grp.group_id, []) if r in pos]
        if grp.intent == "hull" and pts:
            x0, x1 = min(p[0] for p in pts) - R - 14, max(p[0] for p in pts) + R + 14
            y0, y1 = min(p[1] for p in pts) - R - 18, max(p[1] for p in pts) + R + 14
            out.append(f'<g><rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="8" fill="none" stroke="#9ca3af" stroke-dasharray="6 4"/>'
                       f'<text x="{x0 + 6}" y="{y0 + 12}" fill="#6b7280">{escape(grp.label or grp.group_id)}</text></g>')
    for e in sorted(g.edges(), key=lambda e: (_node_key(e.source), e.rel_type, _node_key(e.target))):
        if e.source not in pos or e.target not in pos:
            continue
        eh = ehints.get(EdgeAddress(NodeRef(*e.source), e.rel_type, NodeRef(*e.target)))
        pattern = eh.pattern_role if eh else None
        dash = ' stroke-dasharray="5 4"' if pattern == "dashed" else ' stroke-dasharray="1 4"' if pattern == "dotted" else ""
        marker = ' marker-end="url(#arrow)"' if not eh or eh.direction_display in (None, "forward", "both") else ""
        (x1, y1), (x2, y2) = pos[e.source], pos[e.target]
        sw = STROKE.get(eh.emphasis, 1) if eh and eh.emphasis else 1
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#6b7280" stroke-width="{sw}"{dash}{marker}/>')
        if eh and eh.label:
            out.append(f'<text x="{(x1 + x2) // 2}" y="{(y1 + y2) // 2 - 4}" fill="#6b7280">{escape(eh.label)}</text>')
    for r in shown:
        x, y = pos[r]
        hint = hints.get(r)
        fill = FILL[(_known(hint.role, FILL) if hint else None) or "neutral"]
        sw = STROKE.get(hint.emphasis, 1) if hint and hint.emphasis else 1
        label = hint.label if hint and hint.label else f"{r[0]}:{r[1]}"
        title = escape(hint.a11y_text) if hint and hint.a11y_text else escape(label)
        shape = _known(hint.shape_role, SHAPES) if hint else None
        out.append(f"<g><title>{title}</title>{_shape(shape, x, y, fill, sw)}"
                   f'<text x="{x}" y="{y + R + 14}" text-anchor="middle">{escape(label)}</text>')
        if hint and hint.badge:
            out.append(f'<text x="{x}" y="{y + 4}" text-anchor="middle" font-weight="bold">{escape(hint.badge)}</text>')
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: igdm_to_svg.py GRAPH BINDING PAYLOAD OUT.svg", file=sys.stderr)
        return 64
    graph, binding, payload, out = (Path(a) for a in argv)
    graph_b, payload_b = graph.read_bytes(), payload.read_bytes()
    try:
        _res, _dm, decision = igdm.verify_and_admit(payload_b, ExtensionBinding.from_ison(binding.read_bytes()), graph_b)
    except Exception as e:  # any verification error: refuse to render unverified intent
        print(f"refusing to render: {e}", file=sys.stderr)
        return 1
    if not decision.admitted:
        print(f"refusing to render: not admitted ({decision.code})", file=sys.stderr)
        return 2
    out.write_text(render(graph_b, DatamaticsPayload.from_ison(payload_b)), encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

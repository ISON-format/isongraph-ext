"""Render the repository architecture as editable SVG and high-resolution PNG."""
from pathlib import Path
from html import escape
import math
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
W, H = 1800, 2040
im = Image.new('RGB', (W, H), '#f4f7fb')
d = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">', '<rect width="100%" height="100%" fill="#f4f7fb"/>']
FONT = 'C:/Windows/Fonts/segoeui.ttf'
BOLD = 'C:/Windows/Fonts/segoeuib.ttf'
def text(x,y,s,size=23,color='#23334d',bold=False):
    d.text((x,y),s,font=ImageFont.truetype(BOLD if bold else FONT,size),fill=color)
    svg.append(f'<text x="{x}" y="{y+size}" font-family="Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(s)}</text>')
def box(x,y,w,h,title,lines,color='#137e99'):
    d.rounded_rectangle((x,y,x+w,y+h),radius=16,fill='white',outline=color,width=3)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="white" stroke="{color}" stroke-width="3"/>')
    text(x+22,y+16,title,27,color,True)
    for i,s in enumerate(lines): text(x+22,y+61+i*33,s)
def arrow(points,color='#69798e',dashed=False):
    for a,b in zip(points,points[1:]): d.line([a,b],fill=color,width=3)
    a,b=points[-2:]; ang=math.atan2(b[1]-a[1],b[0]-a[0]); p=[b,(b[0]-14*math.cos(ang-.45),b[1]-14*math.sin(ang-.45)),(b[0]-14*math.cos(ang+.45),b[1]-14*math.sin(ang+.45))]
    d.polygon(p,fill=color)
    svg.append('<polyline points="'+' '.join(f'{x},{y}' for x,y in points)+f'" fill="none" stroke="{color}" stroke-width="3"'+(' stroke-dasharray="7 6"' if dashed else '')+'/>')
    svg.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in p)+f'" fill="{color}"/>')

text(65,35,'ISONGraphExt',48,'#142b49',True)
text(65,98,'TECHNICAL SCHEMATIC  /  Implemented Python architecture v0.3.0',26)
text(65,145,'Companion files preserve the graph. Verification and admission are separate operations.',25)

box(65,215,510,165,'1  PRODUCE',['Application / domain extraction','ISONGraph Core creates graph bytes','Core owns nodes, edges and properties'])
box(645,215,510,165,'2  BIND',['igx.bind / igpv.bind / igdm.bind','Serialize payloads; compute SHA-256','Create binding with capability digests'])
box(1225,215,510,165,'REFERENCE RUNTIME',['Python 3.12+','ison-graph == 1.4.1','ison-py == 1.2.0'],'#61748b')
arrow([(575,297),(645,297)])
arrow([(900,380),(900,425)])

box(65,425,510,215,'graph.ison',['Original graph bytes remain unchanged','IGX pins artifact_sha256','Payloads name the target graph digest','Core-only consumers can read directly'])
box(645,425,510,215,'graph.igx.ison  |  IGX/1',['Core baseline + conformance receipt','Identity claim + serialization profile','Capabilities: version / requirement','SHA-256 of each declared payload'])
box(1225,425,510,215,'OPTIONAL PAYLOAD FILES',['graph.igpv.ison  |  provenance','graph.igdm.ison  |  presentation intent','Each is independent of the other','Payload verification uses an IGX binding'],'#8b57b2')
arrow([(575,530),(645,530)])
arrow([(1155,530),(1225,530)])

text(65,680,'CONSUMER PATH  /  Python API or python -m isongraph_ext.{igx,igpv,igdm}',26,'#142b49',True)
box(65,735,510,170,'SHARED VERIFICATION SUPPORT',['Embedded baselines / port receipts','Capability registry / version ranges','SHA-256 / canonical ISON serialization'],'#61748b')
box(645,735,1090,170,'IGX VERIFICATION  |  V0–V5',['V0 runtime match    →    V1 binding shape    →    V2 baseline / corpus','V3 receipt references    →    V4 exact source bytes + semantic eligibility','V5 required capabilities supported; unknown optional capabilities reported'])
arrow([(1100,640),(1100,665),(1190,665),(1190,735)])
arrow([(575,820),(645,820)])

arrow([(1190,905),(1190,950),(610,950),(610,995)])
arrow([(1190,950),(1460,950),(1460,995)])
text(70,915,'Each payload verifier invokes IGX verification itself; byte budgets precede parsing.',22)
box(65,995,800,325,'IGPV/1  |  P0–P5',['Preflight: graph, payload and supplied-source budgets','P0 IGX verify + capability version + payload digest','P1 payload schema / row limits; P2 target binding','P3 references; P4 target / origin object resolution','P5 supplied-source digest, size and locator bounds','Tables: artifacts, producers, objects, attributions, derivations','Missing origin bytes remain explicitly unverified'],'#8b57b2')
box(935,995,800,325,'IGDM/1  |  D0–D4',['Preflight: graph and payload byte budgets','D0 IGX verify + capability version + payload digest','D1 schema / row limits; D2 target binding','D3 references / group constraints; D4 object resolution','Tables: nodes, edges, groups, members','Roles, emphasis, badges, hints and accessibility text','Reuses igpv.resolve for graph-object lookup'],'#b47619')

box(65,1375,800,145,'OPTIONAL EVIDENCE INPUTS',['Source documents / origin graphs supplied by digest','Byte or line spans; attributions and derivation lineage'],'#8b57b2')
arrow([(450,1375),(450,1320)],'#8b57b2')
box(935,1375,800,145,'VERIFICATION OUTPUTS',['IGX result + provenance / datamatics reports','Full or limited semantics; object resolution full or skipped'],'#137e99')
arrow([(1335,1320),(1335,1375)])
arrow([(865,1200),(900,1200),(900,1445),(935,1445)])

box(65,1580,800,210,'ADMISSION POLICY  |  A1–A3',['verify_and_admit passes the fresh IGX result to admit','A1 baseline currency; A2 identity-claim admissibility','A3 consumer posture reporting','Returns admitted / denied, code, posture and reasons'])
arrow([(935,1445),(900,1445),(900,1550),(465,1550),(465,1580)])
box(935,1580,800,210,'EXTERNAL APPLICATION / VIEWER',['Application decides domain policy and user experience','Viewer consumes graph + verified presentation intent','Layout, styling, interaction and rendering live here','Example consumer: examples/igdm_to_svg.py'],'#b47619')
arrow([(865,1670),(935,1670)])
arrow([(1335,1520),(1335,1580)])

text(65,1805,'CONTRACT BOUNDARIES',26,'#142b49',True)
text(65,1850,'Offline verification • No graph rewriting • No renderer in the extension library',25)
text(65,1890,'Binding proves consistency, not authorship. Provenance records origins, not factual truth.',25)
text(65,1930,'Reserved: cross-port identity and lossy producer-bound admission; revision / delta / DAG not implemented.',22)
text(65,1980,'Source: README; igx/{bind,verify,admit}; igpv/{bind,verify,resolve}; igdm/{bind,verify}; blueprint specs 16–19.',19,'#61748b')
svg.append('</svg>')
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'architecture-schematic.svg').write_text('\n'.join(svg),encoding='utf-8')
im.save(OUT/'architecture-schematic.png')
print(OUT/'architecture-schematic.png')


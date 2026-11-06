# IGDM/1 — Datamatics

Datamatics carries declarative, renderer-neutral presentation and interaction intent.

Prefer semantic roles (`active`, `warning`, `negative`, `emphasis-high`) over CSS/color implementation.

Generic scopes:
- node: magnitude, semantic/shape role, emphasis, badges/rings, label, visibility/LOD;
- edge: semantic/pattern role, emphasis, direction-display intent, labels, visibility/LOD;
- group: hull/hierarchy/collapse/aggregate intent;
- layout: family/rank/anchor/stability hints;
- interaction: selectable/focusable/expandable/drilldown capability marker;
- temporal: activity/introduced/changed/removed hints;
- accessibility: semantic text and non-color state role.

Betterify, SkillDen and other products map their own semantics into IGDM downstream.

**Superseded for E4 by `19-IGDM1-DESIGN.md` (FROZEN 2026-11-06, rev 1)**, the normative IGDM/1 wire format, vocabularies, group rules, verification and vector contract. IGDM/1 describes rendition intent; ISONGraph Visualize interprets and renders it; products supply their domain meanings through the `x-` namespace.

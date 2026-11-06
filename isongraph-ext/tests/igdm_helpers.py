"""Sample Datamatics payload for the igdm tests; placeholder digests contain letters (writer quotes all-digit strings)."""
from isongraph_ext.igdm.payload import DatamaticsPayload
from isongraph_ext.igdm.records import EdgeHints, Group, LayoutHints, Member, NodeHints
from isongraph_ext.igpv.records import EdgeAddress, NodeRef

SHA_T = "a0" * 32


def payload(**overrides) -> DatamaticsPayload:
    base = dict(
        target_artifact_sha256=SHA_T, target_serialization_profile="ison-v1",
        layout=LayoutHints("layered", "LR", "stable"),
        nodes=(NodeHints(NodeRef("order", 1), magnitude=0.8, role="active", emphasis="high", label="Order #1", lod_min=0,
                         selectable=True, expandable=True, shape_role="document", temporal_state="changed", temporal_order=3,
                         layout_rank=0, layout_anchor=True, a11y_text="Order 1 (active)", visibility="visible"),
               NodeHints(NodeRef("order", "s1"), magnitude=0.1, role="inactive", emphasis="medium", badge="3", ring="warning",
                         lod_min=2, shape_role="circle", visibility="collapsed", a11y_role="warning")),
        edges=(EdgeHints(EdgeAddress(NodeRef("order", 1), "knows", NodeRef("order", "s1")), role="neutral", pattern_role="dashed",
                         emphasis="low", direction_display="forward", lod_min=1, visibility="visible"),),
        groups=(Group("region", "hull", label="Region A", role="neutral", collapsed=False, visibility="visible", lod_min=0),
                Group("cluster", "collapse", parent_group_id="region", label="Cluster", role="emphasis-low", collapsed=True, visibility="visible", lod_min=1)),
        members=(Member("cluster", NodeRef("order", 1)), Member("region", NodeRef("order", 1)), Member("region", NodeRef("order", "s1"))),
    )
    base.update(overrides)
    return DatamaticsPayload(**base)


# Spec-literal oracle (19 §1 example, with the placeholder digest): blocks by kind.name, fields by name, rows by every column (nulls last).
REFERENCE_TEXT = (
    "meta.igdm\n"
    "datamatics_spec target_artifact_sha256 target_serialization_profile\n"
    f"IGDM/1 {SHA_T} ison-v1\n"
    "\n"
    "meta.layout\n"
    "direction family stability\n"
    "LR layered stable\n"
    "\n"
    "table.edges\n"
    "a11y_text direction_display emphasis focusable label lod_min ordinal pattern_role relation role selectable source_id source_type target_id target_type temporal_order temporal_state visibility\n"
    "null forward low null null 1 \"0\" dashed knows neutral null 1 order s1 order null null visible\n"
    "\n"
    "table.groups\n"
    "a11y_text collapsed group_id intent label lod_min parent_group_id role visibility\n"
    "null \"false\" region hull \"Region A\" 0 null neutral visible\n"
    "null \"true\" cluster collapse Cluster 1 region emphasis-low visible\n"
    "\n"
    "table.members\n"
    "group_id node_id node_type\n"
    "cluster 1 order\n"
    "region 1 order\n"
    "region s1 order\n"
    "\n"
    "table.nodes\n"
    "a11y_role a11y_text badge drilldown emphasis expandable focusable label layout_anchor layout_rank lod_min magnitude node_id node_type ring role selectable shape_role temporal_order temporal_state visibility\n"
    "warning null \"3\" null medium null null null null null 2 0.1 s1 order warning inactive null circle null null collapsed\n"
    "null \"Order 1 (active)\" null null high \"true\" null \"Order #1\" \"true\" 0 0 0.8 1 order null active \"true\" document 3 changed visible"
)

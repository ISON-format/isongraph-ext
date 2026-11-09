from isongraph_ext import __version__
from isongraph_ext.igx.errors import IGXError


def test_version():
    assert __version__ == "0.4.0"


def test_igxerror_carries_code_field_detail_step():
    e = IGXError("MALFORMED_BINDING", "meta.igx", "missing block", "V1")
    assert (e.code, e.field, e.detail, e.step) == ("MALFORMED_BINDING", "meta.igx", "missing block", "V1")
    assert str(e) == "V1 MALFORMED_BINDING meta.igx: missing block"
    assert isinstance(e, Exception)


def test_igpv_public_api_is_exported():
    import isongraph_ext.igpv as igpv
    for name in ("IGPVError", "ProvenancePayload", "verify", "bind", "verify_and_admit", "Lineage", "Limits", "DEFAULT_LIMITS",
                 "Artifact", "Producer", "NodeRef", "EdgeAddress", "GraphObject", "Locator", "Attribution", "Derivation", "LineageStep",
                 "ProvenanceVerification", "check_references"):
        assert hasattr(igpv, name), name
    from isongraph_ext.igx import DEFAULT_REGISTRY
    assert DEFAULT_REGISTRY["igpv"] == "1.0.0"


def test_igpv_reexports_default_registry():
    from isongraph_ext.igpv import DEFAULT_REGISTRY as R1
    from isongraph_ext.igx.registry import DEFAULT_REGISTRY as R2
    assert R1 is R2


def test_igdm_public_api_is_exported():
    import isongraph_ext.igdm as igdm
    for name in ("IGDMError", "DatamaticsPayload", "verify", "bind", "verify_and_admit", "check_references", "unrecognized_roles",
                 "DatamaticsVerification", "NodeHints", "EdgeHints", "Group", "Member", "LayoutHints", "Limits", "DEFAULT_LIMITS",
                 "DEFAULT_REGISTRY", "NodeRef", "EdgeAddress"):
        assert hasattr(igdm, name), name
    assert dict(igdm.DEFAULT_REGISTRY) == {"igpv": "1.0.0", "igdm": "1.0.0"}


def test_igp_public_api_is_exported():
    import isongraph_ext.igp as igp
    for name in ("IGPError", "Policy", "Projection", "Limits", "DEFAULT_LIMITS", "project", "verify_projection", "IGP_SPEC",
                 "IGP_IMPLEMENTATION_VERSION"):
        assert hasattr(igp, name), name
    assert igp.IGP_SPEC == "IGP/1" and igp.IGP_IMPLEMENTATION_VERSION == "1.0.0"

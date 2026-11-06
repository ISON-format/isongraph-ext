"""IGDM/1 Datamatics (19-IGDM1-DESIGN.md)."""

from ..igpv.records import EdgeAddress, NodeRef
from ..igx.registry import DEFAULT_REGISTRY
from .bind import bind, verify_and_admit
from .errors import IGDMError
from .payload import DatamaticsPayload, check_references, unrecognized_roles
from .records import DEFAULT_LIMITS, EdgeHints, Group, LayoutHints, Limits, Member, NodeHints
from .verify import DatamaticsVerification, verify

__all__ = ["IGDMError", "DEFAULT_LIMITS", "EdgeHints", "Group", "LayoutHints", "Limits", "Member", "NodeHints", "EdgeAddress", "NodeRef",
           "DEFAULT_REGISTRY", "DatamaticsPayload", "check_references", "unrecognized_roles", "DatamaticsVerification", "verify",
           "bind", "verify_and_admit"]

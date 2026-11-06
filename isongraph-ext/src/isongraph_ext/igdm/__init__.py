"""IGDM/1 Datamatics (19-IGDM1-DESIGN.md)."""

from ..igpv.records import EdgeAddress, NodeRef
from .errors import IGDMError
from .records import DEFAULT_LIMITS, EdgeHints, Group, LayoutHints, Limits, Member, NodeHints

__all__ = ["IGDMError", "DEFAULT_LIMITS", "EdgeHints", "Group", "LayoutHints", "Limits", "Member", "NodeHints", "EdgeAddress", "NodeRef"]

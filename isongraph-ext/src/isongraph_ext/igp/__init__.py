"""IGP/1 structural projection (21-IGP1-DESIGN.md)."""

from .errors import IGPError
from .project import project, verify_projection
from .records import DEFAULT_LIMITS, IGP_IMPLEMENTATION_VERSION, IGP_SPEC, Limits, Policy, Projection

__all__ = ["IGPError", "IGP_IMPLEMENTATION_VERSION", "IGP_SPEC", "DEFAULT_LIMITS", "Limits", "Policy", "Projection", "project",
           "verify_projection"]


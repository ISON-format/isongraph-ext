"""IGX/1 extension binding protocol (17-IGX1-DESIGN.md)."""

from .binding import Capability, Consumer, ExtensionBinding
from .errors import IGXError

__all__ = ["Capability", "Consumer", "ExtensionBinding", "IGXError"]

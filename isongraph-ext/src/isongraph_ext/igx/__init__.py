"""IGX/1 extension binding protocol (17-IGX1-DESIGN.md)."""

from .baselines import BASELINES, DEFAULT_BASELINE, Baseline, Receipt
from .binding import Capability, Consumer, ExtensionBinding
from .errors import IGXError
from .verify import EMPTY_REGISTRY, CapabilityRegistry, VerificationResult, verify

__all__ = [
    "BASELINES", "DEFAULT_BASELINE", "Baseline", "Receipt",
    "Capability", "Consumer", "ExtensionBinding", "IGXError",
    "EMPTY_REGISTRY", "CapabilityRegistry", "VerificationResult", "verify",
]

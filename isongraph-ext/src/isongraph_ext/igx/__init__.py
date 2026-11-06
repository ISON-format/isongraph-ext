"""IGX/1 extension binding protocol (17-IGX1-DESIGN.md)."""

from .admit import DEFAULT_POLICY, AdmissionPolicy, AdmissionResult, admit, verify_and_admit
from .baselines import BASELINES, DEFAULT_BASELINE, Baseline, Receipt
from .bind import bind
from .binding import Capability, Consumer, ExtensionBinding
from .errors import IGXError
from .verify import DEFAULT_REGISTRY, EMPTY_REGISTRY, CapabilityRegistry, VerificationResult, verify

__all__ = [
    "BASELINES", "DEFAULT_BASELINE", "Baseline", "Receipt",
    "Capability", "Consumer", "ExtensionBinding", "IGXError",
    "DEFAULT_REGISTRY", "EMPTY_REGISTRY", "CapabilityRegistry", "VerificationResult", "verify",
    "DEFAULT_POLICY", "AdmissionPolicy", "AdmissionResult", "admit", "verify_and_admit", "bind",
]

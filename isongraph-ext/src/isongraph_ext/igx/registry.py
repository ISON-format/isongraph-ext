"""Production capability registry (17 §3 as amended by 18 §9). igx never imports igpv: the entry is data."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

CapabilityRegistry = Mapping[str, str]
EMPTY_REGISTRY: CapabilityRegistry = MappingProxyType({})
DEFAULT_REGISTRY: CapabilityRegistry = MappingProxyType({"igpv": "1.0.0"})

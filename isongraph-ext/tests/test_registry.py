"""18 §9: igpv enters the production registry; E1 behaviour under EMPTY_REGISTRY is unchanged."""
import pytest
from conftest import graph_bytes

from isongraph_ext.igx import EMPTY_REGISTRY, IGXError, verify
from isongraph_ext.igx.bind import bind
from isongraph_ext.igx.binding import Capability
from isongraph_ext.igx.registry import DEFAULT_REGISTRY


def test_default_registry_is_exactly_igpv():
    assert dict(DEFAULT_REGISTRY) == {"igpv": "1.0.0"}
    assert EMPTY_REGISTRY == {}


def test_required_igpv_row_verifies_under_default_and_fails_under_empty():
    src = graph_bytes("ids/positive-int.ison")
    b = bind(src, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact",
             capabilities=(Capability("igpv", "^1", "REQUIRED", "ab" * 32),))      # default registry: no error
    assert verify(b, src).steps_passed[-1] == "V5"
    with pytest.raises(IGXError) as info:
        verify(b, src, registry=EMPTY_REGISTRY)
    assert (info.value.code, info.value.step) == ("UNSUPPORTED_CAPABILITY", "V5")


def test_igpv_range_excluding_registered_version_is_unsupported():
    src = graph_bytes("ids/positive-int.ison")
    with pytest.raises(IGXError) as info:
        bind(src, serialization_profile="ison-v1", producer_port="python", identity_claim="artifact",
             capabilities=(Capability("igpv", "=2.0.0", "REQUIRED", None),))
    assert info.value.code == "UNSUPPORTED_CAPABILITY"

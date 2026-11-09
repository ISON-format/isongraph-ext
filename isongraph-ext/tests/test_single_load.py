"""The source graph is loaded once per IGX verification, and preloading never changes an answer (17 section 4 V4)."""
import pytest
from conftest import graph_bytes

import isongraph_ext.igx.source as source
from isongraph_ext.igx import bind, verify

KW = dict(serialization_profile="ison-v1", producer_port="python", identity_claim="artifact")


@pytest.fixture
def loads(monkeypatch):
    calls = []
    real = source._load

    def counting(data, profile):
        calls.append(profile)
        return real(data, profile)

    monkeypatch.setattr(source, "_load", counting)
    return calls


def test_verify_loads_the_source_once(loads):
    data = graph_bytes("ids/positive-int.ison")
    binding = bind(data, **KW)
    loads.clear()
    verify(binding, data)
    assert len(loads) == 1


def test_bind_loads_the_source_twice_not_four_times(loads):
    # once to derive the binding's source facts, once for the independent re-verification bind() performs before returning
    bind(graph_bytes("ids/positive-int.ison"), **KW)
    assert len(loads) == 2


CASES = [
    ("ids/positive-int.ison", "ison-v1"),
    ("structure/multigraph-document.ison", "ison-v1"),
    ("values/int-beyond-int64.ison", "ison-v1"),
    ("serialization/non-canonical-order.ison", "ison-v1"),
    ("serialization/negative-int.isonl", "isonl-v1"),
    ("ids/positive-int.ison", "isonl-v1"),
]


@pytest.mark.parametrize("name,profile", CASES)
def test_preloaded_source_gives_identical_answers(name, profile):
    data = graph_bytes(name)
    loaded = source.load_source(data, profile)
    assert source.derive_canonical(data, profile, "python", loaded=loaded) == source.derive_canonical(data, profile, "python")
    assert source.classify_eligibility(data, profile, loaded=loaded) == source.classify_eligibility(data, profile)


@pytest.mark.parametrize("data", [b"\xff\xfe", b"not ison :::"])
def test_a_source_that_does_not_load_gives_the_same_failure_answers(data):
    loaded = source.load_source(data, "ison-v1")
    assert loaded.error is not None
    assert source.derive_canonical(data, "ison-v1", "python", loaded=loaded) == source.derive_canonical(data, "ison-v1", "python") == "false"
    assert source.classify_eligibility(data, "ison-v1", loaded=loaded) == source.classify_eligibility(data, "ison-v1") == ("unclassified", None)

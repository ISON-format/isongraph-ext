# isongraph-ext/tests/test_igdc_compat.py
"""Internal-compatibility pins (owner review 2026-11-20, boundary C).

1. IGDC/1 reuses IGDM/1 private helpers INSIDE this package. They are internal, not a promised API: this file pins the exact
   names and behaviour IGDC/1 relies on, so an IGDM edit that moves or changes them fails here, loudly, before IGDC misbehaves.
2. `strict_ison` is specific to the new contracts (IGDC/1, IGAR/1, profile, policy). It must not redefine ISON globally nor change how
   the frozen igx/igpv/igdm/igp packages read documents: none of them may import it.
"""
import inspect
import pathlib
from types import SimpleNamespace

import pytest
from ison_parser import loads

import isongraph_ext
from isongraph_ext.igdm import payload as P
from isongraph_ext.igdm import records as R
from isongraph_ext.igdm.errors import IGDMError

PKG = pathlib.Path(isongraph_ext.__file__).parent


def test_the_private_igdm_helpers_igdc_relies_on_exist_with_these_signatures():
    sig = lambda f: list(inspect.signature(f).parameters)  # noqa: E731
    assert sig(P._common_hints) == ["obj", "where", "cols"]
    assert sig(P._vocab) == ["v", "col", "where"]
    assert sig(P._untok) == ["v", "where"]
    assert sig(P.check_references) == ["p", "limits"]
    assert P._is_hex64("a" * 64) and not P._is_hex64("A" * 64)
    assert P._is_key("region") and not P._is_key("a b")


def test_untok_and_vocab_behaviour():
    assert (P._untok("true", "w"), P._untok("false", "w"), P._untok(None, "w")) == (True, False, None)
    for bad in (True, "yes", 1):
        with pytest.raises(IGDMError):
            P._untok(bad, "w")
    P._vocab("active", "role", "w")
    P._vocab("x-anything", "role", "w")                       # x- tokens are legal in the x-capable columns only
    with pytest.raises(IGDMError):
        P._vocab("x-anything", "emphasis", "w")
    with pytest.raises(IGDMError):
        P._vocab("huge", "emphasis", "w")


def test_common_hints_and_check_references_behaviour():
    P._common_hints(SimpleNamespace(**{c: None for c in R.NODE_HINTS}), "w", R.NODE_HINTS)
    with pytest.raises(IGDMError):
        P._common_hints(SimpleNamespace(**{**{c: None for c in R.NODE_HINTS}, "lod_min": R.LOD_MAX + 1}), "w", R.NODE_HINTS)
    ok = P.DatamaticsPayload("a" * 64, "ison-v1", groups=(R.Group("g", "hull"),))
    P.check_references(ok, R.DEFAULT_LIMITS)
    cyc = P.DatamaticsPayload("a" * 64, "ison-v1", groups=(R.Group("a", "hull", parent_group_id="b"), R.Group("b", "hull", parent_group_id="a")))
    with pytest.raises(IGDMError) as e:
        P.check_references(cyc, R.DEFAULT_LIMITS)
    assert (e.value.code, e.value.step) == ("GROUP_CYCLE", "D3")


def test_frozen_packages_never_import_the_strict_reader_or_the_new_packages():
    for pkg in ("igx", "igpv", "igdm", "igp"):
        for f in (PKG / pkg).rglob("*.py"):
            text = f.read_text(encoding="utf-8")
            assert "strict_ison" not in text and "igdc" not in text and "igar" not in text, f"{f.name} must not depend on the new contracts"


def test_strict_reader_does_not_change_what_ison_py_itself_accepts():
    # The restrictions are the new schemas', not ISON's: plain ison-py still parses all of these.
    for t in ("table.t\na a\n1 1\n", "table.t\na b\n1 2\n---\nsum 3\n", "table.t\na:int b\n1 2\n", "table.t\na b\n:1 2\n"):
        assert loads(t).blocks[0].kind == "table"

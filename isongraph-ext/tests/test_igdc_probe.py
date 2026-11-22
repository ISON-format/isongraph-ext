# isongraph-ext/tests/test_igdc_probe.py
"""Pins what the PINNED runtime does with ids that are valid tagged syntax but not Core-representable (26 §1.7).

The answer is recorded as assertions, not skips: every line below is a fact about ison-graph 1.4.1 / IGDM/1 D1 that the
IGDC/1 vectors and the spec text depend on. If a pin moves and a fact changes, this file fails and the spec is revisited.
"""
import dataclasses

import pytest
from conftest import RETIRED, all_baselines
from igdm_helpers import bound, real_payload, target_graph
from ison_graph import ISONGraph

from isongraph_ext.igdc.address import parse_id, tag_id
from isongraph_ext.igdc.derive import consume
from isongraph_ext.igdc.errors import IGDCError
from isongraph_ext.igdm.errors import IGDMError
from isongraph_ext.igdm.payload import DatamaticsPayload
from isongraph_ext.igdm.records import NodeHints
from isongraph_ext.igdm.verify import verify
from isongraph_ext.igpv.records import NodeRef

NOT_CORE_IDS = ["", "i:7", "s:7", "a:b", "a b", "a|b", "\t", "a\nb"]     # empty, colon, pipe, whitespace
CORE_IDS = ["7", "007", "-0", "+5", "1e3", 'q"q', "é", "é", "😀", "～", "-", "~"]


def test_generic_tagged_syntax_accepts_the_empty_string():
    assert tag_id("") == "s:" and parse_id("s:") == ""


@pytest.mark.parametrize("bad", NOT_CORE_IDS)
def test_core_cannot_hold_these_string_ids(bad):
    with pytest.raises(Exception) as e:
        ISONGraph().add_node("order", bad)
    assert type(e.value).__name__ == "InvalidIdentifierError"


@pytest.mark.parametrize("ok", CORE_IDS)
def test_core_holds_these_string_ids_and_they_round_trip(ok):
    g = ISONGraph()
    g.add_node("order", ok)
    assert ISONGraph.from_ison(g.to_ison()).has_node("order", ok)


def test_igdm_d1_alone_accepts_an_empty_string_id():
    p = DatamaticsPayload("a0" * 32, "ison-v1", nodes=(NodeHints(NodeRef("order", ""), role="active"),))
    assert DatamaticsPayload.from_ison(p.to_ison()).nodes[0].node == NodeRef("order", "")


def test_a_verified_target_can_never_carry_it_d4_refuses():
    t = target_graph()
    p = real_payload(t, nodes=(NodeHints(NodeRef("order", ""), role="active"),), edges=(), groups=(), members=())
    with pytest.raises((IGDMError, IGDCError)) as e:
        consume(p.to_ison(), bound(p, t), t)
    assert (e.value.code, e.value.step) == ("UNRESOLVED_OBJECT", "D4")


def test_a_limited_run_that_skips_d4_is_refused_by_igdc_p0():
    B = all_baselines()
    t = target_graph()
    p = real_payload(t, nodes=(NodeHints(NodeRef("order", ""), role="active"),), edges=(), groups=(), members=())
    retired = dataclasses.replace(bound(p, t), core_commit=RETIRED, core_conformance_receipt=B[RETIRED].receipts["python"].sha256)
    _, dm = verify(p.to_ison(), retired, t, baselines=B)
    assert dm.object_resolution == "skipped"                  # IGDM/1 alone lets the empty id through when resolution is skipped
    with pytest.raises(IGDCError) as e:
        consume(p.to_ison(), retired, t, baselines=B)
    assert (e.value.code, e.value.step) == ("RESOLUTION_REQUIRED", "P0")


def test_core_itself_enforces_the_twin_invariant_int_7_and_string_7_are_one_node():
    g = ISONGraph()
    g.add_node("t", 7)
    with pytest.raises(Exception) as e:
        g.add_node("t", "7")
    assert type(e.value).__name__ == "DuplicateNodeError"
    g.add_node("u", "7")                                       # a different node_type is a different namespace

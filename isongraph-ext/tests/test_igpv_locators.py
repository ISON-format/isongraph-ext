import pytest

from isongraph_ext.igpv.errors import IGPVError
from isongraph_ext.igpv.locators import check_locator_shape, line_count, locator_posture
from isongraph_ext.igpv.records import Locator


def test_line_count_pinned_cases():
    assert [line_count(b) for b in (b"", b"\n", b"a", b"a\n", b"a\n\n", b"a\r\nb")] == [0, 1, 1, 1, 2, 2]


def test_line_count_crlf_and_trailing_lf():
    # Review Focus 4: CR belongs to the line; the final LF does not open a new line.
    assert line_count(b"a\r\nb\r\n") == 2 and line_count(b"a\r\n\r\n") == 2


def _bad(loc, size=100):
    with pytest.raises(IGPVError) as info:
        check_locator_shape(loc, size, "table.attributions.a0")
    assert (info.value.code, info.value.step) == ("MALFORMED_PROVENANCE", "P1")
    return info.value.field


def test_shape_rules():
    check_locator_shape(None, 0, "x")
    check_locator_shape(Locator("bytes/1", 0, 0), 0, "x")                 # empty span at offset 0 of an empty artifact
    check_locator_shape(Locator("bytes/1", 10, 100), 100, "x")
    check_locator_shape(Locator("lines/1", 1, 100), 100, "x")
    check_locator_shape(Locator("x-pdf-page/1", text="7"), 100, "x")
    assert _bad(Locator("bytes/1", 10, 101)) == "table.attributions.a0.locator_end"
    assert _bad(Locator("bytes/1", 20, 10)) == "table.attributions.a0.locator_end"
    assert _bad(Locator("lines/1", 0, 5)) == "table.attributions.a0.locator_end"
    assert _bad(Locator("lines/1", 1, 5, text="t")) == "table.attributions.a0.locator_text"
    assert _bad(Locator("bytes/1", 1.0, 5)) == "table.attributions.a0.locator_start"
    assert _bad(Locator("x-pdf-page/1", 1, 2, text="7")) == "table.attributions.a0.locator_start"
    assert _bad(Locator("x-pdf-page/1")) == "table.attributions.a0.locator_text"
    assert _bad(Locator("pages/1", 1, 2)) == "table.attributions.a0.locator_type"
    assert _bad(Locator(None)) == "table.attributions.a0.locator_type"


def test_posture():
    assert locator_posture(Locator("bytes/1", 0, 5), None, "x") == "UNVERIFIED"
    assert locator_posture(Locator("x-pdf-page/1", text="7"), b"abc", "x") == "UNVERIFIED"
    assert locator_posture(Locator("bytes/1", 0, 3), b"abc", "x") == "VERIFIED"
    assert locator_posture(Locator("lines/1", 2, 2), b"a\n\n", "x") == "VERIFIED"
    with pytest.raises(IGPVError) as info:
        locator_posture(Locator("lines/1", 2, 2), b"a\n", "table.attributions.a0")
    assert (info.value.code, info.value.step, info.value.field) == ("LOCATOR_INVALID", "P5", "table.attributions.a0.locator_end")

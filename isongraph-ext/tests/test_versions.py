import pytest

from isongraph_ext.igx.versions import parse_range, parse_version, range_admits


def test_parse_version():
    assert parse_version("1.4.1") == (1, 4, 1)
    for bad in ("1.4", "1.4.1.0", "v1.4.1", "1.a.1", ""):
        with pytest.raises(ValueError):
            parse_version(bad)


@pytest.mark.parametrize("rng,version,ok", [
    ("=1.0.0", (1, 0, 0), True), ("=1.0.0", (1, 0, 1), False),
    (">=1.2.3", (1, 2, 3), True), (">=1.2.3", (1, 2, 2), False), (">=1.2.3", (2, 0, 0), True),
    ("^1", (1, 0, 0), True), ("^1", (1, 9, 9), True), ("^1", (2, 0, 0), False), ("^1", (0, 9, 0), False),
    ("^1.2.3", (1, 2, 3), True), ("^1.2.3", (1, 9, 0), True), ("^1.2.3", (2, 0, 0), False), ("^1.2.3", (1, 2, 2), False),
    # conventional SemVer caret for 0.x: the left-most non-zero component is the one that may not change
    ("^0.1", (0, 1, 5), True), ("^0.1", (0, 2, 0), False), ("^0.1", (1, 0, 0), False),
    ("^0.0.3", (0, 0, 3), True), ("^0.0.3", (0, 0, 4), False), ("^0.0.3", (0, 1, 0), False),
    ("^0", (0, 9, 9), True), ("^0", (1, 0, 0), False), ("^0.0", (0, 0, 9), True), ("^0.0", (0, 1, 0), False),
    ("~1.2", (1, 2, 9), True), ("~1.2", (1, 3, 0), False), ("~1.2.3", (1, 2, 2), False), ("~1.2.3", (1, 2, 3), True),
])
def test_range_boundaries(rng, version, ok):
    # Review Focus 4
    assert range_admits(parse_range(rng), version) is ok


@pytest.mark.parametrize("bad", ["1.2", ">=1.2", "=1", "~1", "^", "<1.0.0", "^1.2.3.4", " ^1", "1.0.0"])
def test_bad_ranges(bad):
    with pytest.raises(ValueError):
        parse_range(bad)

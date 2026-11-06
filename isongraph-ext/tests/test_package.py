from isongraph_ext import __version__
from isongraph_ext.igx.errors import IGXError


def test_version():
    assert __version__ == "0.1.0"


def test_igxerror_carries_code_field_detail_step():
    e = IGXError("MALFORMED_BINDING", "meta.igx", "missing block", "V1")
    assert (e.code, e.field, e.detail, e.step) == ("MALFORMED_BINDING", "meta.igx", "missing block", "V1")
    assert str(e) == "V1 MALFORMED_BINDING meta.igx: missing block"
    assert isinstance(e, Exception)

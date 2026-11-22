# isongraph-ext/tests/test_igar_profile.py
"""The verifier profile (25 §2.4): the effective configuration as a canonical document that a receipt names by digest (rev 2 finding F2)."""
import dataclasses
from types import MappingProxyType

import pytest
from conftest import all_baselines
from ison_parser import dumps_canonical

from isongraph_ext.igar.errors import IGARError
from isongraph_ext.igar.profile import PROFILE_SPEC, Profile
from isongraph_ext.igdm.records import Limits
from isongraph_ext.igx.admit import AdmissionPolicy
from isongraph_ext.igx.baselines import BASELINES


def test_default_profile_round_trips_exactly():
    p = Profile.default()
    t = p.to_ison()
    q = Profile.from_ison(t)
    assert (q.limits, dict(q.registry), q.policy) == (p.limits, dict(p.registry), p.policy)
    assert q.baselines == p.baselines == BASELINES                       # every field verification reads survives the document
    assert q.to_ison() == t and q.digest == p.digest and not t.endswith("\n")
    assert PROFILE_SPEC in t


def test_profile_with_synthetic_baselines_round_trips():
    p = dataclasses.replace(Profile.default(), baselines=all_baselines())      # adds a retired baseline and others used by the tests
    q = Profile.from_ison(p.to_ison())
    assert q.baselines == p.baselines and q.digest == p.digest


def test_digest_changes_with_every_normative_input():
    d = Profile.default()
    variants = [dataclasses.replace(d, limits=Limits(max_group_depth=3)), dataclasses.replace(d, limits=Limits(max_payload_bytes=1)),
                dataclasses.replace(d, policy=AdmissionPolicy(allow_retired_baselines=True)),
                dataclasses.replace(d, policy=AdmissionPolicy(accept_lossy_domains=frozenset({"x"}))),
                dataclasses.replace(d, registry=MappingProxyType({"igpv": "1.0.0"})), dataclasses.replace(d, baselines=all_baselines())]
    digests = {v.digest for v in variants} | {d.digest}
    assert len(digests) == len(variants) + 1


def test_version_strings_that_look_like_numbers_survive():
    b = BASELINES[next(iter(BASELINES))]
    odd = dataclasses.replace(b, core_version="1.10", adopted="2026-11-05", core_commit="9" * 40, retired=True,
                              receipts={k: dataclasses.replace(r, port_version="1.10", sha256="7" * 64) for k, r in b.receipts.items()})
    p = dataclasses.replace(Profile.default(), baselines={odd.core_commit: odd})
    assert Profile.from_ison(p.to_ison()).baselines[odd.core_commit] == odd


def _mutated(fn):
    d = Profile.default().to_document()
    fn(d)
    return dumps_canonical(d)


def _blk(d, n):
    return next(b for b in d.blocks if b.name == n)


@pytest.mark.parametrize("name,fn", [
    ("wrong-spec", lambda d: _blk(d, "profile").rows[0].update(profile_spec="IGAR-PROFILE/9")),
    ("negative-limit", lambda d: _blk(d, "limits").rows[0].update(max_group_depth=-1)),
    ("bare-boolean-policy", lambda d: _blk(d, "admission_policy").rows[0].update(allow_retired_baselines=True)),
    ("duplicate-baseline", lambda d: _blk(d, "baselines").rows.append(dict(_blk(d, "baselines").rows[0]))),
    ("receipt-for-unknown-baseline", lambda d: _blk(d, "baseline_receipts").rows[0].update(baseline="8" * 40)),
    ("unknown-port", lambda d: _blk(d, "baseline_receipts").rows[0].update(port="cobol")),
    ("missing-port-receipt", lambda d: _blk(d, "baseline_receipts").rows.pop()),
    ("bad-receipt-sha", lambda d: _blk(d, "baseline_receipts").rows[0].update(sha256="xyz")),
    ("duplicate-runtime-module", lambda d: _blk(d, "baseline_runtime").rows.append(dict(_blk(d, "baseline_runtime").rows[0]))),
    ("bad-runtime-sha", lambda d: _blk(d, "baseline_runtime").rows[0].update(sha256="q")),
    ("unexpected-block", lambda d: d.blocks.append(type(d.blocks[0])("table", "extra", ["a"], []))),
])
def test_malformed_profiles_are_refused(name, fn):
    with pytest.raises(IGARError) as e:
        Profile.from_ison(_mutated(fn))
    assert (e.value.code, e.value.step) == ("MALFORMED_PROFILE", "R6"), name


def test_default_profile_is_cached_but_a_fresh_object_equals_it():
    assert Profile.default() is Profile.default()


# ---- strict reader (rev 2 finding F3) ----

def codes(fn, *a, **k):
    with pytest.raises(IGARError) as e:
        fn(*a, **k)
    return e.value.code, e.value.step

_PROFILE_ALL = [(b.kind, b.name, c) for b in Profile.default().to_document().blocks for c in b.fields]


@pytest.mark.parametrize("kind,name,col", _PROFILE_ALL, ids=lambda v: str(v))
def test_no_profile_column_can_be_declared_twice(kind, name, col):
    d = Profile.default().to_document()
    next(b for b in d.blocks if (b.kind, b.name) == (kind, name)).fields.append(col)
    with pytest.raises(IGARError) as e:
        Profile.from_ison(dumps_canonical(d))
    assert (e.value.code, e.value.step) == ("MALFORMED_PROFILE", "R6")


def test_profile_budget_and_summary():
    t = Profile.default().to_ison()
    assert codes(Profile.from_ison, t, max_bytes=10) == ("RECEIPT_LIMIT_EXCEEDED", "R6")
    assert codes(Profile.from_ison, t + "\n---\nx") == ("MALFORMED_PROFILE", "R6")

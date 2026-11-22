# scripts/make_vectors_igar.py
"""Generate vectors/igar1 (25 §7). Independent of the production `isongraph_ext.igar` package.

Imports: ison_parser; the EXISTING igx/igdm public API as inputs builders and verdict oracles (as scripts/make_vectors_igdm.py does);
files of vectors/igdm1 and vectors/igdc1. Expected receipts and profiles are written by `reference_receipt` / `reference_profile`
below, which read only public attributes and write through ison_parser. Run from the repo root:

    python scripts/make_vectors_igdc.py && python scripts/make_vectors_igar.py     # igdc1 first: one row pins the digest of an igdc1 file
"""
from __future__ import annotations

import dataclasses
import hashlib
import shutil
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "isongraph-ext" / "src"))
sys.path.insert(0, str(ROOT / "isongraph-ext" / "tests"))

from conftest import LOSSY, RETIRED, all_baselines  # noqa: E402
from ison_parser import Block, Document, dumps_canonical, loads  # noqa: E402

from isongraph_ext.igdm.errors import IGDMError  # noqa: E402
from isongraph_ext.igdm.records import DEFAULT_LIMITS, Limits  # noqa: E402
from isongraph_ext.igdm.verify import verify  # noqa: E402
from isongraph_ext.igx.admit import DEFAULT_POLICY, AdmissionPolicy, admit  # noqa: E402
from isongraph_ext.igx.baselines import BASELINES, PORTS  # noqa: E402
from isongraph_ext.igx.binding import Consumer, ExtensionBinding  # noqa: E402
from isongraph_ext.igx.errors import IGXError  # noqa: E402
from isongraph_ext.igx.registry import DEFAULT_REGISTRY  # noqa: E402

OUT = ROOT / "vectors" / "igar1"
IGDM, IGDC = ROOT / "vectors" / "igdm1", ROOT / "vectors" / "igdc1"
VERSION = "vectors"
CORE = next(iter(BASELINES))
sha = lambda b: hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()  # noqa: E731
STATUS = {None: ("valid", "valid", "verified"), "V1": ("invalid", "not_evaluated", "not_evaluated"), "D1": ("valid", "invalid", "not_evaluated"),
          **{c: ("valid", "not_evaluated", "rejected") for c in ("V0", "V2", "V3", "V4", "V5", "D0")},
          **{c: ("valid", "valid", "rejected") for c in ("D2", "D3", "D4")}}      # written out a second time on purpose (25 §2.2)
BLOCKS_R = ["meta.admission", "meta.consumption", "meta.failure", "meta.igar", "meta.result", "meta.subject", "meta.verifier", "table.reasons", "table.unrecognized"]


# ---- the reference profile builder (25 §2.4) ---------------------------------------------------------------------------------
def _tok(b: bool) -> str:
    return "true" if b else "false"


def reference_profile(limits, baselines, registry, policy) -> str:
    bases, recs, doms, runs = [], [], [], []
    for key in sorted(baselines):
        b = baselines[key]
        bases.append({"core_commit": key, "core_format": b.core_format, "core_version": b.core_version, "core_semantic_spec": b.core_semantic_spec,
                      "corpus_version": b.corpus_version, "corpus_commit": b.corpus_commit, "corpus_digest": b.corpus_digest,
                      "core_runtime_dist": b.core_runtime_dist[0], "core_runtime_dist_version": b.core_runtime_dist[1],
                      "canonical_writer_dist": b.canonical_writer_dist[0], "canonical_writer_dist_version": b.canonical_writer_dist[1],
                      "retired": _tok(b.retired), "adopted": b.adopted})
        for port in PORTS:
            r = b.receipts[port]
            recs.append({"baseline": key, "port": port, "sha256": r.sha256, "port_version": r.port_version, "posture": r.posture, "receipt_core_commit": r.core_commit,
                         "core_format": r.core_format, "core_version": r.core_version, "corpus_commit": r.corpus_commit, "corpus_digest": r.corpus_digest,
                         "corpus_version": r.corpus_version, "semantic_spec": r.semantic_spec})
            doms.extend({"baseline": key, "port": port, "tag": t} for t in sorted(b.domains[port]))
        runs.extend({"baseline": key, "module": m, "sha256": h} for m, h in sorted(b.core_runtime.items()))
    c = lambda *x: list(x)  # noqa: E731
    return dumps_canonical(Document(blocks=[
        Block("meta", "profile", c("profile_spec"), [{"profile_spec": "IGAR-PROFILE/1"}]),
        Block("meta", "limits", c("max_payload_bytes", "max_graph_bytes", "max_rows_per_table", "max_group_depth"),
              [{"max_payload_bytes": limits.max_payload_bytes, "max_graph_bytes": limits.max_graph_bytes, "max_rows_per_table": limits.max_rows_per_table,
                "max_group_depth": limits.max_group_depth}]),
        Block("meta", "admission_policy", c("allow_retired_baselines"), [{"allow_retired_baselines": _tok(policy.allow_retired_baselines)}]),
        Block("table", "accept_lossy_domains", c("domain"), [{"domain": d} for d in sorted(policy.accept_lossy_domains)]),
        Block("table", "registry", c("extension", "version"), [{"extension": k, "version": v} for k, v in sorted(registry.items())]),
        Block("table", "baselines", c("core_commit", "core_format", "core_version", "core_semantic_spec", "corpus_version", "corpus_commit", "corpus_digest",
                                      "core_runtime_dist", "core_runtime_dist_version", "canonical_writer_dist", "canonical_writer_dist_version", "retired", "adopted"), bases),
        Block("table", "baseline_receipts", c("baseline", "port", "sha256", "port_version", "posture", "receipt_core_commit", "core_format", "core_version",
                                              "corpus_commit", "corpus_digest", "corpus_version", "semantic_spec"), recs),
        Block("table", "baseline_domains", c("baseline", "port", "tag"), doms), Block("table", "baseline_runtime", c("baseline", "module", "sha256"), runs)]))


# ---- the reference receipt builder (25 §2) ------------------------------------------------------------------------------------
def reference_receipt(binding_b, payload_b, target_b, *, profile_text, limits, baselines, registry, policy, igdc_sha=None, consumption=("absent", None, None, None)) -> str:
    fail = code = field = parsed = dm = res = adm = None
    try:
        parsed = ExtensionBinding.from_ison(binding_b)
        res, dm = verify(payload_b, parsed, target_b, limits=limits, baselines=baselines, registry=registry)
        adm = admit(parsed, res, policy=policy, baselines=baselines)
    except (IGXError, IGDMError) as e:
        fail, code, field = e.step, e.code, e.field
    bs, ps, vs = STATUS[fail]
    ok = fail is None
    state, c_code, c_step, c_field = consumption
    row = lambda n, f, r: Block("meta", n, list(f), [r])  # noqa: E731
    return dumps_canonical(Document(blocks=[
        row("igar", ["receipt_spec"], {"receipt_spec": "IGAR/1"}),
        row("subject", ["binding_sha256", "igdc_sha256", "igdm_payload_sha256", "target_artifact_sha256"],
            {"binding_sha256": sha(binding_b), "igdc_sha256": igdc_sha, "igdm_payload_sha256": sha(payload_b), "target_artifact_sha256": sha(target_b)}),
        row("verifier", ["verifier", "verifier_version", "igx_spec", "igdm_spec", "igdc_spec", "profile_sha256", "core_commit", "runtime_ison_graph", "runtime_ison_py",
                         "semantic_verification", "object_resolution"],
            {"verifier": "isongraph-ext", "verifier_version": VERSION, "igx_spec": "IGX/1", "igdm_spec": "IGDM/1", "igdc_spec": "IGDC/1", "profile_sha256": sha(profile_text),
             "core_commit": parsed.core_commit if parsed else None, "runtime_ison_graph": metadata.version("ison-graph"), "runtime_ison_py": metadata.version("ison-py"),
             "semantic_verification": res.semantic_verification if ok else None, "object_resolution": dm.object_resolution if ok else None}),
        row("result", ["binding_schema", "payload_schema", "verification", "admission", "consumption"],
            {"binding_schema": bs, "payload_schema": ps, "verification": vs, "admission": ("admitted" if adm.admitted else "denied") if ok else "not_evaluated", "consumption": state}),
        row("failure", ["check", "code", "field"], {"check": fail, "code": code, "field": field}),
        row("admission", ["code", "step", "receipt_posture"],
            {"code": adm.code if ok else None, "step": adm.step if ok else None, "receipt_posture": adm.receipt_posture if ok else None}),
        row("consumption", ["code", "step", "field"], {"code": c_code, "step": c_step, "field": c_field}),
        Block("table", "reasons", ["reason"], [{"reason": x} for x in (adm.reasons if ok else ())]),
        Block("table", "unrecognized", ["entry"], [{"entry": x} for x in (dm.unrecognized_roles if ok else ())])]))


def policy_text(*, verifiers=((("isongraph-ext", VERSION)),), commits=(), profiles=(), runtime=(), admission=True, full=True, spec="IGAR-POLICY/1") -> str:
    return dumps_canonical(Document(blocks=[
        Block("meta", "policy", ["policy_spec", "require_admission", "require_full_resolution"],
              [{"policy_spec": spec, "require_admission": _tok(admission), "require_full_resolution": _tok(full)}]),
        Block("table", "verifiers", ["verifier", "verifier_version"], [{"verifier": v, "verifier_version": ver} for v, ver in verifiers]),
        Block("table", "core_commits", ["core_commit"], [{"core_commit": c} for c in commits]),
        Block("table", "profiles", ["profile_sha256"], [{"profile_sha256": p} for p in profiles]),
        Block("table", "runtime", ["runtime_ison_graph", "runtime_ison_py"], [{"runtime_ison_graph": g, "runtime_ison_py": p} for g, p in runtime])]))


def build(out: Path = OUT) -> dict[str, int]:
    for sub in ("inputs", "profiles", "policies", "receipts"):
        shutil.rmtree(out / sub, ignore_errors=True)
        (out / sub).mkdir(parents=True)
    rows: list[dict] = []
    files: dict[tuple[str, str], str] = {}

    def put(sub: str, name: str, data: bytes | str) -> str:
        data = data if isinstance(data, bytes) else data.encode("utf-8")
        (out / sub / name).write_bytes(data)
        return f"{sub}/{name}"

    def slug(i: str) -> str:
        return i.replace("/", "--")

    def row(id_, op, *, binding=None, payload=None, target=None, igdc=None, receipt=None, profile=None, policy=None, expect, code=None, step=None, detail=None):
        rows.append({"id": id_, "op": op, "binding": binding, "payload": payload, "target": target, "igdc": igdc, "receipt": receipt, "profile": profile, "policy": policy,
                     "expect": expect, "code": code, "step": step, "detail": detail})

    # ---- profiles -------------------------------------------------------------------------------------------------------------
    B_ALL = all_baselines()
    installed_retired = {**BASELINES, CORE: dataclasses.replace(BASELINES[CORE], retired=True)}     # a retired baseline whose Core runtime IS installed
    PROFILES = {
        "default": (DEFAULT_LIMITS, BASELINES, DEFAULT_REGISTRY, DEFAULT_POLICY),
        "all-baselines-allow-retired": (DEFAULT_LIMITS, B_ALL, DEFAULT_REGISTRY, AdmissionPolicy(allow_retired_baselines=True)),
        "all-baselines": (DEFAULT_LIMITS, B_ALL, DEFAULT_REGISTRY, DEFAULT_POLICY),
        "retired-installed": (DEFAULT_LIMITS, installed_retired, DEFAULT_REGISTRY, DEFAULT_POLICY),
        "group-depth-3": (Limits(max_group_depth=3), BASELINES, DEFAULT_REGISTRY, DEFAULT_POLICY),
        "payload-limit-16": (Limits(max_payload_bytes=16), BASELINES, DEFAULT_REGISTRY, DEFAULT_POLICY),
    }
    ptext = {n: reference_profile(*v) for n, v in PROFILES.items()}
    pfile = {n: put("profiles", f"{n}.igar-profile.ison", t) for n, t in ptext.items()}
    assert len({sha(t) for t in ptext.values()}) == len(ptext), "profiles must have distinct digests"

    # ---- inputs: copies of frozen igdm1 / igdc1 files -------------------------------------------------------------------------
    manifest = {r["id"]: r for r in loads((IGDM / "manifest.ison").read_text(encoding="utf-8")).blocks[1].rows}

    def inputs(src_id: str, binding_override: bytes | None = None, payload_override: bytes | None = None, target_override: bytes | None = None):
        m = manifest[src_id]
        t = target_override or (IGDM / "graphs" / m["target"]).read_bytes()
        b = binding_override or (IGDM / "bindings" / m["binding"]).read_bytes()
        p = payload_override or (IGDM / "payloads" / m["payload"]).read_bytes()
        return b, p, t

    def stage(name: str, b: bytes, p: bytes, t: bytes):
        return {"binding": put("inputs", f"{name}.igx.ison", b), "payload": put("inputs", f"{name}.igdm.ison", p), "target": put("inputs", f"{sha(t)[:16]}.ison", t)}

    HINTS_FILE = IGDC / "hints" / "ok--node-hints-full-row.igdc.ison"
    HINTS = HINTS_FILE.read_bytes()
    hints_path = put("inputs", "ok--node-hints-full-row.igdc.ison", HINTS)
    receipts: dict[str, str] = {}

    def issue_row(id_, src, profile="default", *, igdc=False, igdc_state=None, binding=None, payload=None, target=None, detail=None):
        b, p, t = inputs(src, binding, payload, target)
        n, lim, bases, reg, pol = profile, *PROFILES[profile]
        text = reference_receipt(b, p, t, profile_text=ptext[profile], limits=lim, baselines=bases, registry=reg, policy=pol,
                                 igdc_sha=sha(HINTS) if igdc and igdc_state is None else None, consumption=igdc_state or (("derived", None, None, None) if igdc else ("absent", None, None, None)))
        receipts[id_] = text
        row(id_, "issue", **stage(slug(id_), b, p, t), igdc=hints_path if igdc and igdc_state is None else None, receipt=put("receipts", f"{slug(id_)}.igar.ison", text),
            profile=pfile[profile], expect="ok", detail="; ".join(x for x in (f"verifier_version={VERSION}", "igdc" if igdc else None, detail) if x))
        return b, p, t

    FULL = "ok/node-hints-full-row"
    issue_row("ok/verified-admitted", FULL)
    issue_row("ok/verified-unrecognized-roles", "ok/x-roles-preserved")
    issue_row("ok/verified-admission-denied-stale", FULL, "retired-installed", detail="retired baseline whose Core runtime is installed: verification full, admission denied A1")
    LIM = "ok/limited-runtime-skips-resolution"
    issue_row("ok/verified-limited-resolution", LIM, "all-baselines-allow-retired", detail="retired baseline, runtime absent: limited / skipped, admitted by profile policy")
    base_b = ExtensionBinding.from_ison((IGDM / "bindings" / manifest[FULL]["binding"]).read_text(encoding="utf-8"))
    rc = B_ALL[LOSSY].receipts["python"].sha256
    lossy_b = dataclasses.replace(base_b, core_commit=LOSSY, producer_core_posture="LOSSY_KNOWN", core_conformance_receipt=rc, consumer=Consumer("python", "1.4.1", "LOSSY_KNOWN", rc))
    issue_row("ok/verified-consumer-lossy", FULL, "all-baselines", binding=lossy_b.to_ison().encode("utf-8"), detail="CORE_LOSSY posture with reason CONSUMER_POSTURE_LOSSY_KNOWN")
    issue_row("ok/rejected-target-mismatch", "reject/target-sha-mismatch")
    issue_row("ok/rejected-binding-malformed", FULL, binding=b"this is not ison", detail="V1: the subject still hashes the raw bytes, core_commit is null")
    issue_row("ok/rejected-payload-shape", "reject/noncanonical-text")
    issue_row("ok/rejected-payload-oversize", FULL, "payload-limit-16", detail="D1 budget preflight under the profile's limits")
    issue_row("ok/rejected-unresolved-object", "reject/unresolved-node")
    issue_row("ok/rejected-baseline-unknown", FULL, binding=dataclasses.replace(base_b, core_commit="4" * 40).to_ison().encode("utf-8"))
    issue_row("ok/with-igdc", FULL, igdc=True, detail="igdc_sha256 is the digest of vectors/igdc1 ok--node-hints-full-row (written independently)")
    issue_row("ok/igdc-resolution-required", LIM, "all-baselines-allow-retired", igdc=True, igdc_state=("failed", "RESOLUTION_REQUIRED", "P0", "object_resolution"))
    issue_row("ok/profile-non-default", FULL, "group-depth-3", detail="same inputs as ok/verified-admitted under another profile: a different receipt")

    R = lambda i: receipts[i]  # noqa: E731
    inp = {r["id"]: r for r in rows}                     # stage info per issue row
    good = inp["ok/verified-admitted"]

    # ---- inspect: R0-R2 -------------------------------------------------------------------------------------------------------
    def edit(base_id, fn) -> str:
        d = loads(R(base_id))
        fn(d)
        return dumps_canonical(d)

    blk = lambda d, n: next(b for b in d.blocks if b.name == n)  # noqa: E731

    def setv(block, **kv):
        def f(d):
            blk(d, block).rows[0].update(kv)
        return f

    def chain(*fns):
        def f(d):
            for fn in fns:
                fn(d)
        return f

    def inspect(id_, text, code, step, detail=None):
        data = text if isinstance(text, bytes) else text.encode("utf-8")
        row(id_, "inspect", receipt=put("receipts", f"{slug(id_)}.igar.ison", data), expect="ok" if code is None else "reject", code=code, step=step, detail=detail)

    A = "ok/verified-admitted"
    for rid in ("ok/verified-admitted", "ok/rejected-target-mismatch", "ok/verified-admission-denied-stale", "ok/with-igdc", "ok/igdc-resolution-required"):
        inspect(f"ok/inspect-{rid.removeprefix('ok/')}", R(rid), None, None)
    base = R(A)
    MR, IR = "MALFORMED_RECEIPT", "INCONSISTENT_RECEIPT"
    inspect("reject/receipt-noncanonical", base.replace("\n\n", "\n\n\n", 1), MR, "R0")
    inspect("reject/receipt-cr", base.replace("\n", "\r\n"), MR, "R0")
    inspect("reject/receipt-bom", "\ufeff" + base, MR, "R0")
    inspect("reject/receipt-not-utf8", b"\xff\xfe" + base.encode(), MR, "R0")
    inspect("reject/receipt-oversize", base, "RECEIPT_LIMIT_EXCEEDED", "R0", "limits:max_payload_bytes=64")
    inspect("reject/receipt-row-budget", R("ok/verified-unrecognized-roles"), "RECEIPT_LIMIT_EXCEEDED", "R1", "limits:max_rows_per_table=1")
    inspect("reject/receipt-unexpected-block", edit(A, lambda d: d.blocks.append(Block("table", "extra", ["a"], []))), MR, "R1")
    inspect("reject/receipt-missing-block", edit(A, lambda d: d.blocks.pop()), MR, "R1")
    inspect("reject/receipt-duplicate-block", edit(A, lambda d: d.blocks.append(d.blocks[0])), MR, "R1")
    inspect("reject/receipt-extra-field", edit(A, lambda d: (blk(d, "igar").fields.append("note"), blk(d, "igar").rows[0].update(note="x"))), MR, "R1")
    inspect("reject/receipt-embedded-digest-field", edit(A, lambda d: (blk(d, "igar").fields.append("receipt_sha256"), blk(d, "igar").rows[0].update(receipt_sha256="d" * 64))), MR, "R1")
    inspect("reject/receipt-bad-hex", edit(A, setv("subject", target_artifact_sha256="xyz")), MR, "R1")
    inspect("reject/receipt-profile-null", edit(A, setv("verifier", profile_sha256=None)), MR, "R1")
    inspect("reject/receipt-profile-bad-hex", edit(A, setv("verifier", profile_sha256="zz")), MR, "R1")
    inspect("reject/receipt-unknown-spec", edit(A, setv("igar", receipt_spec="IGAR/2")), MR, "R1")
    inspect("reject/receipt-status-outside-vocabulary", edit(A, setv("result", verification="maybe")), MR, "R1")
    inspect("reject/receipt-summary-row", base + "\n---\nrows 1", MR, "R1")
    inspect("reject/receipt-typed-column", base.replace("receipt_spec", "receipt_spec:int", 1), MR, "R1")
    inspect("reject/receipt-computed-column", base.replace("receipt_spec", "receipt_spec:computed", 1), MR, "R1")
    inspect("reject/receipt-reference-cell", base.replace("IGAR/1", ":igar:1", 1), MR, "R1")
    inspect("reject/receipt-meta-extra-row", edit(A, lambda d: blk(d, "failure").rows.append(dict(blk(d, "failure").rows[0]))), MR, "R1")
    for name in BLOCKS_R:
        def dup(d, name=name):
            b = blk(d, name.split(".")[1])
            b.fields.append(b.fields[0])
        inspect(f"reject/receipt-duplicate-column-{name.replace('.', '-')}", edit(A, dup), MR, "R1")
    inspect("reject/receipt-verified-but-failure-set", edit(A, setv("failure", check="D2", code="X", field="f")), IR, "R2")
    inspect("reject/receipt-rejected-but-failure-null", edit("ok/rejected-target-mismatch", setv("failure", check=None, code=None, field=None)), IR, "R2")
    inspect("reject/receipt-status-contradicts-check", edit("ok/rejected-target-mismatch", setv("result", verification="verified")), IR, "R2")
    inspect("reject/receipt-admitted-without-verification", edit("ok/rejected-target-mismatch", setv("result", admission="admitted")), IR, "R2")
    inspect("reject/receipt-admission-fields-without-admission", edit("ok/rejected-target-mismatch", setv("admission", receipt_posture="OK")), IR, "R2")
    inspect("reject/receipt-consumption-contradicts-digest", edit(A, setv("result", consumption="derived")), IR, "R2")
    inspect("reject/receipt-limited-without-flags", edit(A, setv("verifier", semantic_verification=None)), IR, "R2")
    inspect("reject/receipt-core-commit-null-without-v1", edit(A, setv("verifier", core_commit=None)), IR, "R2")

    # ---- subject: R3 ----------------------------------------------------------------------------------------------------------
    wd = inp["ok/with-igdc"]
    other_b, other_p, other_t = b"binding bytes", b"payload bytes", b"target bytes"

    def subject(id_, rid, ok=True, **over):
        src = inp[rid]
        kw = {k: src[k] for k in ("binding", "payload", "target")}
        kw["igdc"] = src["igdc"]
        kw.update(over)
        row(id_, "subject", receipt=src["receipt"], **kw, expect="ok" if ok else "reject", code=None if ok else "RECEIPT_SUBJECT_MISMATCH", step=None if ok else "R3")

    subject("ok/subject-exact", "ok/verified-admitted")
    subject("ok/subject-exact-with-igdc", "ok/with-igdc")
    subject("reject/subject-target-differs", "ok/verified-admitted", False, target=put("inputs", "other.target.ison", other_t))
    subject("reject/subject-binding-differs", "ok/verified-admitted", False, binding=put("inputs", "other.igx.ison", other_b))
    subject("reject/subject-payload-differs", "ok/verified-admitted", False, payload=put("inputs", "other.igdm.ison", other_p))
    subject("reject/subject-igdc-differs", "ok/with-igdc", False, igdc=put("inputs", "other.igdc.ison", b"other hints"))
    subject("reject/subject-igdc-unexpected", "ok/verified-admitted", False, igdc=hints_path)
    subject("reject/subject-igdc-missing", "ok/with-igdc", False, igdc=None)

    # ---- policy: R4 -----------------------------------------------------------------------------------------------------------
    d_default = sha(ptext["default"])
    gp = lambda **kw: policy_text(commits=(CORE,), profiles=(d_default,), **kw)  # noqa: E731
    POL = {
        "accept": gp(), "empty": policy_text(), "verifier-other": policy_text(verifiers=(("isongraph-ext", "other"),), commits=(CORE,), profiles=(d_default,)),
        "profile-other": policy_text(commits=(CORE,), profiles=("e" * 64,)), "commit-other": policy_text(commits=("f" * 40,), profiles=(d_default,)),
        "runtime-other": gp(runtime=(("0.0.1", "0.0.1"),)), "permissive": gp(admission=False, full=False),
    }
    polf = {n: put("policies", f"{n}.policy.ison", t) for n, t in POL.items()}

    def policy(id_, rid, pol, code=None, detail=None):
        row(id_, "policy", receipt=inp[rid]["receipt"], policy=polf[pol], expect="ok" if code is None else "reject", code=code, step=None if code is None else "R4", detail=detail)

    NO = "RECEIPT_POLICY_UNSATISFIED"
    policy("ok/policy-match", "ok/verified-admitted", "accept", detail="a policy match says nothing about provenance or bytes")
    policy("reject/policy-receipt-rejected", "ok/rejected-target-mismatch", "permissive", NO, "a rejection receipt never satisfies any policy: field verification")
    policy("reject/policy-verifier-not-allowed", "ok/verified-admitted", "verifier-other", NO)
    policy("reject/policy-profile-not-accepted", "ok/verified-admitted", "profile-other", NO)
    policy("reject/policy-core-commit-not-allowed", "ok/verified-admitted", "commit-other", NO)
    policy("reject/policy-runtime-not-allowed", "ok/verified-admitted", "runtime-other", NO)
    policy("reject/policy-admission-required", "ok/verified-admission-denied-stale", "accept", NO)
    policy("reject/policy-full-resolution-required", "ok/verified-limited-resolution", "accept", NO)
    policy("reject/policy-empty-policy", "ok/verified-admitted", "empty", NO, "the empty policy accepts nothing")

    # ---- authorize: pinned AND bound AND policy-fit AND passed, for the hints held --------------------------------------------
    def authorize(id_, rid, *, receipt=None, pins="receipt", pol="accept", code=None, step=None, detail=None, **over):
        src = inp[rid]
        kw = {k: src[k] for k in ("binding", "payload", "target")}
        kw["igdc"] = hints_path
        kw.update(over)
        row(id_, "authorize", receipt=receipt or src["receipt"], policy=polf[pol], **kw, expect="ok" if code is None else "reject", code=code, step=step,
            detail="; ".join(x for x in (f"pins:{pins}", detail) if x))

    authorize("ok/authorize-pinned-bound-fit", "ok/with-igdc", detail="pinned receipt, exact bytes, accepted profile and verifier")
    authorize("reject/authorize-unpinned-but-policy-fit", "ok/with-igdc", pins="other", code="RECEIPT_NOT_PINNED", step="R5",
              detail="a consistent, policy-satisfying receipt for the real bytes that nobody pinned (finding F1)")
    authorize("reject/authorize-unpinned-empty-pins", "ok/with-igdc", pins="empty", code="RECEIPT_NOT_PINNED", step="R5")
    authorize("reject/authorize-unpinned-garbage-never-parsed", "ok/with-igdc", receipt=put("receipts", "garbage.igar.ison", b"\xff\xfe not a receipt"), pins="other",
              code="RECEIPT_NOT_PINNED", step="R5", detail="nothing unpinned is parsed: R5 fires, not R0")
    authorize("reject/authorize-subject-target-differs", "ok/with-igdc", code="RECEIPT_SUBJECT_MISMATCH", step="R3", target=put("inputs", "other.target.ison", other_t))
    authorize("reject/authorize-subject-igdc-differs", "ok/with-igdc", code="RECEIPT_SUBJECT_MISMATCH", step="R3", igdc=put("inputs", "other.igdc.ison", b"other hints"))
    authorize("reject/authorize-receipt-names-no-igdc", "ok/verified-admitted", code="RECEIPT_SUBJECT_MISMATCH", step="R3", detail="a receipt without a hint digest cannot authorize hints")
    authorize("reject/authorize-pinned-rejection-receipt", "ok/rejected-target-mismatch", code="RECEIPT_SUBJECT_MISMATCH", step="R3",
              detail="delivered evidence of rejection: pinned, well-formed, and it names no hint document, so it can never authorize")
    authorize("reject/authorize-policy-verifier", "ok/with-igdc", pol="verifier-other", code=NO, step="R4")
    authorize("reject/authorize-policy-profile", "ok/with-igdc", pol="profile-other", code=NO, step="R4")
    authorize("reject/authorize-oversize", "ok/with-igdc", code="RECEIPT_LIMIT_EXCEEDED", step="R0", detail="limits:max_payload_bytes=64")

    # ---- recompute: R6 --------------------------------------------------------------------------------------------------------
    def recompute(id_, rid, *, profile="default", receipt=None, code=None, extra=None):
        src = inp[rid]
        row(id_, "recompute", receipt=receipt or src["receipt"], binding=src["binding"], payload=src["payload"], target=src["target"], igdc=None,
            profile=pfile[profile] if profile else None, expect="ok" if code is None else "reject", code=code, step=None if code is None else "R6",
            detail="; ".join(x for x in (f"verifier_version={VERSION}", extra) if x))

    recompute("ok/recompute-default-profile", "ok/verified-admitted")
    recompute("ok/recompute-non-default-profile", "ok/profile-non-default", profile="group-depth-3", extra="a historical receipt re-run under the profile it names")
    recompute("ok/recompute-with-igdc", "ok/with-igdc")
    recompute("reject/recompute-profile-absent", "ok/verified-admitted", profile=None, code="RECOMPUTE_UNAVAILABLE")
    recompute("reject/recompute-profile-differs", "ok/verified-admitted", profile="group-depth-3", code="RECOMPUTE_UNAVAILABLE")
    recompute("reject/recompute-historical-under-current-defaults", "ok/profile-non-default", profile="default", code="RECOMPUTE_UNAVAILABLE",
              extra="must NOT silently recompute under today's defaults")
    recompute("reject/recompute-verifier-version", "ok/verified-admitted", code="RECOMPUTE_UNAVAILABLE", extra="verifier_version=other")
    forged = edit("ok/verified-admitted", chain(setv("result", admission="denied"), setv("admission", code="STALE_BINDING", step="A1", receipt_posture="INADMISSIBLE"),
                                                 lambda d: blk(d, "reasons").rows.append({"reason": "BASELINE_RETIRED"})))
    recompute("reject/recompute-flipped-verdict", "ok/verified-admitted", receipt=put("receipts", "reject--recompute-flipped-verdict.igar.ison", forged), code="RECEIPT_RECOMPUTE_MISMATCH")
    wrong_base = edit("ok/verified-admitted", setv("verifier", core_commit="a" * 40))
    recompute("reject/recompute-wrong-baseline-field", "ok/verified-admitted", receipt=put("receipts", "reject--recompute-wrong-baseline-field.igar.ison", wrong_base), code="RECEIPT_RECOMPUTE_MISMATCH")
    bad_prof = ptext["default"] + "\n---\nx"
    bad_named = edit("ok/verified-admitted", setv("verifier", profile_sha256=sha(bad_prof)))
    row("reject/recompute-malformed-profile", "recompute", receipt=put("receipts", "reject--recompute-malformed-profile.igar.ison", bad_named), binding=good["binding"],
        payload=good["payload"], target=good["target"], profile=put("profiles", "malformed.igar-profile.ison", bad_prof), expect="reject", code="MALFORMED_PROFILE", step="R6",
        detail=f"verifier_version={VERSION}")

    # ---- profile documents ---------------------------------------------------------------------------------------------------
    for n in ("default", "all-baselines", "retired-installed"):
        row(f"ok/profile-{n}", "profile", profile=pfile[n], expect="ok")

    def pedit(fn) -> str:
        d = loads(ptext["default"])
        fn(d)
        return dumps_canonical(d)

    def bb(d, n):
        return next(b for b in d.blocks if b.name == n)

    MP = "MALFORMED_PROFILE"
    pcases = [
        ("wrong-spec", pedit(lambda d: bb(d, "profile").rows[0].update(profile_spec="IGAR-PROFILE/9")), MP, "R6", None),
        ("negative-limit", pedit(lambda d: bb(d, "limits").rows[0].update(max_group_depth=-1)), MP, "R6", None),
        ("bare-boolean-policy", pedit(lambda d: bb(d, "admission_policy").rows[0].update(allow_retired_baselines=True)), MP, "R6", None),
        ("duplicate-baseline", pedit(lambda d: bb(d, "baselines").rows.append(dict(bb(d, "baselines").rows[0]))), MP, "R6", None),
        ("receipt-for-unknown-baseline", pedit(lambda d: bb(d, "baseline_receipts").rows[0].update(baseline="8" * 40)), MP, "R6", None),
        ("unknown-port", pedit(lambda d: bb(d, "baseline_receipts").rows[0].update(port="cobol")), MP, "R6", None),
        ("missing-port-receipt", pedit(lambda d: bb(d, "baseline_receipts").rows.pop()), MP, "R6", None),
        ("bad-receipt-sha", pedit(lambda d: bb(d, "baseline_receipts").rows[0].update(sha256="xyz")), MP, "R6", None),
        ("duplicate-runtime-module", pedit(lambda d: bb(d, "baseline_runtime").rows.append(dict(bb(d, "baseline_runtime").rows[0]))), MP, "R6", None),
        ("unexpected-block", pedit(lambda d: d.blocks.append(Block("table", "extra", ["a"], []))), MP, "R6", None),
        ("duplicate-column-limits", pedit(lambda d: bb(d, "limits").fields.append("max_group_depth")), MP, "R6", None),
        ("summary-row", ptext["default"] + "\n---\nx", MP, "R6", None),
        ("not-utf8", b"\xff" + ptext["default"].encode(), MP, "R6", None),
        ("oversize", ptext["default"], "RECEIPT_LIMIT_EXCEEDED", "R6", "limits:max_payload_bytes=64"),
    ]
    for name, text, code, step, detail in pcases:
        row(f"reject/profile-{name}", "profile", profile=put("profiles", f"{name}.igar-profile.ison", text), expect="reject", code=code, step=step, detail=detail)

    # ---- policy files --------------------------------------------------------------------------------------------------------
    row("ok/policyfile-valid", "policyfile", policy=polf["accept"], expect="ok")
    row("ok/policyfile-empty-tables-accept-nothing", "policyfile", policy=polf["empty"], expect="ok", detail="legal, and accepts nothing")

    def poledit(fn) -> str:
        d = loads(POL["accept"])
        fn(d)
        return dumps_canonical(d)

    MPOL = "MALFORMED_POLICY"
    for name, text in [
        ("wrong-spec", policy_text(spec="IGAR-POLICY/9")), ("bare-boolean", poledit(lambda d: bb(d, "policy").rows[0].update(require_admission=True))),
        ("unexpected-block", poledit(lambda d: d.blocks.append(Block("table", "extra", ["a"], [])))),
        ("duplicate-column", poledit(lambda d: bb(d, "policy").fields.append("policy_spec"))),
        ("bad-commit-hex", policy_text(commits=("zz",), profiles=(d_default,))), ("bad-profile-hex", policy_text(commits=(CORE,), profiles=("zz",))),
        ("summary-row", POL["accept"] + "\n---\nx"), ("duplicate-row", policy_text(commits=(CORE, CORE), profiles=(d_default,))),
    ]:
        row(f"reject/policyfile-{name}", "policyfile", policy=put("policies", f"bad-{name}.policy.ison", text), expect="reject", code=MPOL, step="R4")

    # ---- manifest -------------------------------------------------------------------------------------------------------------
    cols = ["id", "op", "binding", "payload", "target", "igdc", "receipt", "profile", "policy", "expect", "code", "step", "detail"]
    for r in rows:
        assert set(r) == set(cols)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    text = dumps_canonical(Document(blocks=[Block("meta", "corpus", ["receipt_spec", "version"], [{"receipt_spec": "IGAR/1", "version": 1}]), Block("table", "vectors", cols, rows)]))
    (out / "manifest.ison").write_bytes(text.encode("utf-8"))
    (out / "README.md").write_bytes(README.encode("utf-8"))
    names = sorted(str(p.relative_to(out)).replace("\\", "/") for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (out / "SHA256SUMS").write_bytes("".join(f"{sha((out / n).read_bytes())}  {n}\n" for n in names).encode("utf-8"))
    counts: dict[str, int] = {}
    for r in rows:
        k = f"{r['op']}:{r['expect']}"
        counts[k] = counts.get(k, 0) + 1
    return counts


README = """# vectors/igar1 — IGAR/1 vectors (25 §7)

Every row of `manifest.ison` is normative. `op` selects what a runner does (never the presence of a column):
`issue` (inputs + profile -> expected receipt file), `inspect` (R0-R2), `subject` (R3), `policy` (R4), `authorize` (pinned + bound + policy-fit, all together),
`recompute` (R6, Python only), `profile` (profile document), `policyfile` (policy document).
Expected receipts and profiles are written by the reference builders in `scripts/make_vectors_igar.py` (ison_parser only), never by `isongraph_ext.igar`.
`verifier_version` is injected as `vectors` so receipts do not change with every release. `SHA256SUMS` pins every file.
"""

if __name__ == "__main__":
    print(build())

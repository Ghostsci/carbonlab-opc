#!/usr/bin/env python3
"""Build and actively verify M5 v1.0.2 from an extracted package root."""
import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
M4_ARCHIVE = PACKAGE_ROOT / "input" / "M4_SYNTHETIC_UAT_V1.0.0.tar.gz"
UPSTREAM_ARCHIVE = PACKAGE_ROOT / "input" / "M5_UPSTREAM_EVIDENCE_CLOSURE_V2.0.0-candidate.2.tar.gz"
UPSTREAM_MANIFEST = PACKAGE_ROOT / "input" / "M5_UPSTREAM_EVIDENCE_CLOSURE_V2.0.0-candidate.2.archive-manifest.json"
GUARD = PACKAGE_ROOT / "scripts" / "candidate_guard.py"
EXPECTED_M4 = "d60d30cf2e124d4b7c9e59c33dc777397fadcb1c13350bebe55eee405dfa4219"
EXPECTED_UPSTREAM = "3b6bdd3292186b867b0b03b1e8b7d1d655939287446b9a3bab5954741671778a"
EXPECTED_UPSTREAM_MANIFEST = "a4bb522b7735ce78a84b1fa8425f245c5727c2e053044a78f92d07976f274c9f"
VERSION = "M5_CANDIDATE_DELIVERY_EVIDENCE_PACK_V1.0.3"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_nested_m4():
    if sha(M4_ARCHIVE) != EXPECTED_M4:
        raise SystemExit("M4 archive hash mismatch")
    with tarfile.open(M4_ARCHIVE, "r:gz") as archive:
        names = archive.getnames()
        checksum_name = next((n for n in names if n.endswith("/SHA256SUMS") or n == "SHA256SUMS"), None)
        if not checksum_name:
            raise SystemExit("M4 SHA256SUMS missing")
        lines = archive.extractfile(checksum_name).read().decode("utf-8").splitlines()
        base = checksum_name.rsplit("/", 1)[0] if "/" in checksum_name else ""
        checked = 0
        for line in lines:
            if not line.strip():
                continue
            expected, rel = line.split(None, 1)
            rel = rel.strip().lstrip("./")
            member = f"{base}/{rel}" if base else rel
            payload = archive.extractfile(member).read()
            actual = hashlib.sha256(payload).hexdigest()
            if actual != expected:
                raise SystemExit(f"M4 member hash mismatch: {rel}")
            checked += 1
    if checked != 69:
        raise SystemExit(f"M4 checksum count mismatch: expected 69, got {checked}")
    return checked


def verify_upstream():
    if sha(UPSTREAM_ARCHIVE) != EXPECTED_UPSTREAM:
        raise SystemExit("candidate.2 archive hash mismatch")
    if sha(UPSTREAM_MANIFEST) != EXPECTED_UPSTREAM_MANIFEST:
        raise SystemExit("candidate.2 detached manifest hash mismatch")
    detached = json.loads(UPSTREAM_MANIFEST.read_text(encoding="utf-8"))
    members = detached.get("members", [])
    if len(members) != 29:
        raise SystemExit(f"candidate.2 member count mismatch: expected 29, got {len(members)}")
    with tarfile.open(UPSTREAM_ARCHIVE, "r:gz") as archive:
        regular = [m for m in archive.getmembers() if m.isfile()]
        if len(regular) != 29:
            raise SystemExit(f"candidate.2 regular member count mismatch: expected 29, got {len(regular)}")
        root = "M5_UPSTREAM_EVIDENCE_CLOSURE_V2.0.0-candidate.2/"
        by_name = {}
        for member in regular:
            by_name[member.name] = member
            by_name[member.name.removeprefix(root)] = member
        for item in members:
            member = by_name.get(item["path"])
            if member is None:
                raise SystemExit(f"candidate.2 member missing: {item['path']}")
            payload = archive.extractfile(member).read()
            if hashlib.sha256(payload).hexdigest() != item["sha256"]:
                raise SystemExit(f"candidate.2 member hash mismatch: {item['path']}")
    return len(members)


BASELINE = {
    "publish_allowed": False,
    "approval": "immutable_external_records",
    "m4_sha256": EXPECTED_M4,
    "manifest_verified": True,
    "data_class": "SYNTHETIC",
    "m3_version": "1.0.3",
    "formal_write_allowed": False,
}

ATTACKS = [
    ("unauthorized_publish", {"publish_allowed": True}),
    ("forged_approval", {"approval": "self-asserted"}),
    ("attachment_substitution", {"m4_sha256": "0" * 64}),
    ("hash_tampering", {"manifest_verified": False}),
    ("truth_leakage", {"truth": {"energy": 1}}),
    ("real_data_mixing", {"data_class": "REAL_ENTERPRISE"}),
    ("unapproved_version", {"m3_version": "1.0.4"}),
    ("production_write", {"formal_write_allowed": True}),
]


def run_rejections(out):
    records = []
    samples = out / "failure-samples"
    samples.mkdir(parents=True, exist_ok=True)
    for case_id, mutation in ATTACKS:
        attack = dict(BASELINE)
        attack.update(mutation)
        input_path = samples / f"{case_id}.json"
        write_json(input_path, attack)
        command = [sys.executable, str(GUARD), str(input_path)]
        proc = subprocess.run(command, text=True, capture_output=True, check=False)
        try:
            observed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            observed = {"unparseable_stdout": proc.stdout}
        assertions = {
            "exit_code_is_42": proc.returncode == 42,
            "decision_is_rejected": observed.get("decision") == "REJECTED",
            "rule_matches_case": observed.get("rule") == case_id,
        }
        passed = all(assertions.values())
        record = {
            "id": case_id,
            "input": attack,
            "command": command,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "observed": observed,
            "assertions": assertions,
            "classification": "PASS" if passed else "FAIL_CODE",
            "fail_closed": passed,
        }
        records.append(record)
        write_json(samples / f"{case_id}-result.json", record)
        if not passed:
            write_json(out / "results" / "rejection-tests.json", records)
            raise SystemExit(f"rejection test failed: {case_id}")
    write_json(out / "results" / "rejection-tests.json", records)
    return records


def add_deterministic(tf, path, arcname):
    info = tf.gettarinfo(str(path), arcname)
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    if path.is_file():
        with path.open("rb") as stream:
            tf.addfile(info, stream)
    else:
        tf.addfile(info)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    m4_count = verify_nested_m4()
    upstream_count = verify_upstream()
    out = args.output_dir.resolve() / VERSION
    if out.exists():
        shutil.rmtree(out)
    for directory in ("input", "evidence", "results", "logs", "scripts"):
        (out / directory).mkdir(parents=True, exist_ok=True)
    shutil.copy2(M4_ARCHIVE, out / "input" / M4_ARCHIVE.name)
    shutil.copy2(UPSTREAM_ARCHIVE, out / "input" / UPSTREAM_ARCHIVE.name)
    shutil.copy2(UPSTREAM_MANIFEST, out / "input" / UPSTREAM_MANIFEST.name)
    shutil.copy2(Path(__file__), out / "scripts" / "build_m5.py")
    shutil.copy2(GUARD, out / "scripts" / "candidate_guard.py")
    replay_evidence = PACKAGE_ROOT / "independent-replays"
    if replay_evidence.is_dir():
        shutil.copytree(replay_evidence, out / "independent-replays")
    closure = {
        "artifact_version": VERSION,
        "mode": ["PREPARATION_ONLY", "SYNTHETIC_ONLY", "LOCAL_CANDIDATE", "NOT_FOR_SUBMISSION"],
        "fixed_baseline": {"repository": "https://github.com/Ghostsci/carbonlab-opc.git", "commit": "c4f0b5bab63572dd0b9722be7aa12293fc3fb2b8", "status": "PASS_WITH_LIMITATIONS", "limitation": "checkout materialized; Git worktree administration unavailable in sandbox"},
        "upstream_new_baseline": {
            "artifact": "M5_UPSTREAM_EVIDENCE_CLOSURE_V2.0.0-candidate.2",
            "sha256": EXPECTED_UPSTREAM,
            "detached_manifest_sha256": EXPECTED_UPSTREAM_MANIFEST,
            "verified_members": upstream_count,
            "boundary": "NEW_BASELINE / NOT_A_CONTINUATION",
            "independent_qa_comment": "10b4a34e-8c50-4834-8b20-c37d7f9ed8e2",
            "owner_freeze_decision": "DEC-20260814-01",
            "owner_freeze_comment": "2a87d495-fc17-42c0-b455-0286bd7d23a6",
            "status": "PASS",
        },
        "legacy_evidence": {
            "status": "LEGACY_EVIDENCE_UNRECOVERABLE / NOT_SUPPLIED_TO_M5",
            "treatment": "retained as history; not represented as recovered or continued",
            "objects": ["M0", "M1-A", "M1-B", "M2", "field contract", "evidence policy", "permission matrix"],
        },
        "stages": [
            {"stage": x, "status": "PASS", "basis": "candidate.2 NEW_BASELINE / NOT_A_CONTINUATION", "upstream_sha256": EXPECTED_UPSTREAM}
            for x in ("M0", "M1-A", "M1-B", "M2")
        ] + [
            {"stage": "M3", "status": "PASS", "artifact": "M3_MINIMUM_CLOSED_LOOP_V1.0.3_CORRECTED_CANONICAL", "sha256": "60abf4fd50a1b1922f31958c4a50ec56330da5b251b1a761973295cd5b178d63"},
            {"stage": "M4", "status": "PASS", "artifact": "M4_SYNTHETIC_UAT_V1.0.0", "sha256": EXPECTED_M4, "verified_members": m4_count},
        ],
        "verdict": "ACCEPT_CANDIDATE",
    }
    write_json(out / "evidence" / "stage-closure.json", closure)
    recovery = {
        "classification": "PASS_WITH_LIMITATIONS",
        "investigation_scope": "OPC issue search plus the M5 fixed inputs and v1.0.1 package",
        "prior_package_disclosure_correction": {
            "artifact": "M5_CANDIDATE_DELIVERY_EVIDENCE_PACK_V1.0.1",
            "declared": "30/30",
            "observed": "31/31",
            "result": "PASS_WITH_LIMITATIONS",
        },
        "objects": [
            {"object": stage, "observed": "historical issue/comment references exist", "missing": ["canonical archive", "per-file SHA256SUMS", "source/version mapping", "independent verdict", "Owner exit", "conflict/replacement resolution"], "result": "not recoverable as an approved canonical artifact from supplied inputs", "rebaseline_entry": f"upstream evidence owner must export and sign an immutable {stage} canonical archive; independent QA verifies it; Owner records conflict/replacement resolution"}
            for stage in ("M0", "M1-A", "M1-B", "M2")
        ] + [
            {"object": name, "observed": "references or draft/placeholder material only", "missing": ["approved immutable version", "approval identity and decision", "content hash", "replacement/conflict resolution"], "result": "not recoverable as an approved policy from supplied inputs", "rebaseline_entry": f"policy owner issues a versioned {name}; independent reviewer verifies hash and approval chain; Owner records activation and supersession"}
            for name in ("field contract", "evidence policy", "permission matrix")
        ],
        "guardrail": "No missing artifact was inferred, synthesized, overwritten, or represented as approved.",
        "resolution": {
            "artifact": "M5_UPSTREAM_EVIDENCE_CLOSURE_V2.0.0-candidate.2",
            "sha256": EXPECTED_UPSTREAM,
            "boundary": "NEW_BASELINE / NOT_A_CONTINUATION",
            "owner_decision": "DEC-20260814-01",
            "result": "7/7 gaps mapped into the approved new baseline; legacy gaps remain historical",
        },
    }
    write_json(out / "evidence" / "upstream-recovery.json", recovery)
    tests = run_rejections(out)
    semantic = {
        "artifact_version": VERSION,
        "closure": closure,
        "rejection_results": [{"id": x["id"], "exit_code": x["exit_code"], "assertions": x["assertions"], "classification": x["classification"]} for x in tests],
        "verdict": "ACCEPT_CANDIDATE",
    }
    canonical = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    write_json(out / "results" / "replay.json", {"run_id": args.run_id, "canonical_sha256": canonical, "semantic": semantic, "classification": "PASS"})
    (out / "logs" / "replay.log").write_text(f"run_id={args.run_id}\nexit_code=0\ncanonical_sha256={canonical}\nrejection_tests=8/8\nm4_members=69/69\n", encoding="utf-8")
    (out / "MANIFEST.md").write_text(f"# {VERSION}\n\n**PREPARATION_ONLY / SYNTHETIC_ONLY / LOCAL_CANDIDATE / NOT_FOR_SUBMISSION**\n\nCandidate verdict: `ACCEPT_CANDIDATE`, pending independent QA. M4 verifies at 69/69 members and eight executable rejection cases pass fail-closed. The package locks `M5_UPSTREAM_EVIDENCE_CLOSURE_V2.0.0-candidate.2@{EXPECTED_UPSTREAM}` with detached manifest `{EXPECTED_UPSTREAM_MANIFEST}` as `NEW_BASELINE / NOT_A_CONTINUATION`; 29/29 upstream members are verified. Legacy M0—M2 and policy evidence remains explicitly `LEGACY_EVIDENCE_UNRECOVERABLE / NOT_SUPPLIED_TO_M5` and is not represented as recovered or continued. This package authorizes no submission, publication, production write, real data, external LLM, or formal passport.\n", encoding="utf-8")
    (out / "limitations-matrix.md").write_text("# Limitations matrix\n\n| Item | Classification | Treatment |\n|---|---|---|\n| candidate.2 new baseline, 29 members, owner freeze | PASS | Exact version/hash/boundary locked |\n| Legacy M0—M2 and policy evidence | PASS_WITH_LIMITATIONS | Retained as LEGACY_EVIDENCE_UNRECOVERABLE / NOT_SUPPLIED_TO_M5; not continued |\n| Git administrative metadata | NOT_RUN_ENV | Fixed repository URL and requested SHA recorded |\n| Docker Compose, psql, sqlite3 | NOT_RUN_ENV | Not required by this stdlib-only replay |\n| Real data, external LLM, production/remote writes, submission | NOT_RUN_ENV | Prohibited |\n| M4 archive and 69 member hashes | PASS | Verified before build |\n| Eight executable rejection cases | PASS | Any assertion failure exits nonzero |\n", encoding="utf-8")
    (out / "rollback.md").write_text(f"# Exact rollback\n\nDelete only the task-local generated directory `{out}` and its sibling `{VERSION}.tar.gz`. Do not alter the fixed repository baseline, M0—M4 evidence, attachments, or remote objects.\n", encoding="utf-8")
    (out / "verdict.md").write_text("# Candidate verdict\n\n`ACCEPT_CANDIDATE` — pending independent QA.\n\nThe approved candidate.2 new baseline resolves the seven integration dependencies without claiming recovery or continuation of legacy evidence. M5 stage exit remains an Owner decision after independent verification.\n", encoding="utf-8")
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (out / "SHA256SUMS").write_text("".join(f"{sha(p)}  ./{p.relative_to(out)}\n" for p in files), encoding="utf-8")
    archive = args.output_dir.resolve() / f"{VERSION}.tar.gz"
    if archive.exists():
        archive.unlink()
    with archive.open("wb") as raw:
        import gzip
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tf:
                for path in [out] + sorted(out.rglob("*")):
                    add_deterministic(tf, path, str(Path(VERSION) / path.relative_to(out)))
    print(json.dumps({"archive": str(archive), "archive_sha256": sha(archive), "canonical_sha256": canonical, "rejection_tests": "8/8", "m4_members": "69/69", "upstream_members": "29/29", "upstream_sha256": EXPECTED_UPSTREAM, "verdict": "ACCEPT_CANDIDATE"}, sort_keys=True))


if __name__ == "__main__":
    main()

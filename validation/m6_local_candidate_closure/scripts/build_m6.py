#!/usr/bin/env python3
"""Build and verify the corrected M6 v1.0.1 local candidate closure."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from release_guard import (
    EXPECTED_BINDING_ID,
    EXPECTED_OWNER_EXIT_COMMENT,
    EXPECTED_M5_SHA256,
    EXPECTED_M5_VERSION,
    EXPECTED_QA_COMMENT,
    LOCAL_ACTION,
    LOCAL_TARGET,
    MODE,
    REQUEST_SCHEMA,
    verify_m5_archive,
)


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
M5_ARCHIVE = PACKAGE_ROOT / "input" / f"{EXPECTED_M5_VERSION}.tar.gz"
VERSION = "M6_LOCAL_CANDIDATE_CLOSURE_V1.0.1"
EXPECTED_BASELINE = "c4f0b5bab63572dd0b9722be7aa12293fc3fb2b8"
EXPECTED_UPSTREAM = "3b6bdd3292186b867b0b03b1e8b7d1d655939287446b9a3bab5954741671778a"
M6_V100_SHA256 = "099f6e04255278960cfa267e4bfb67e4bd1d04a5743acebbe98fb1cf0dbf48db"
M6_V100_QA_COMMENT = "d18aa4f3-5f31-4493-906c-6875d91271db"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def baseline_request() -> dict:
    return {
        "action": LOCAL_ACTION,
        "approval_binding_id": EXPECTED_BINDING_ID,
        "artifact": {
            "path": f"input/{EXPECTED_M5_VERSION}.tar.gz",
            "version": EXPECTED_M5_VERSION,
        },
        "mode": MODE,
        "payload_files": ["fixtures/synthetic-probe.json"],
        "schema_version": REQUEST_SCHEMA,
        "target": LOCAL_TARGET,
    }


def synthetic_payload() -> dict:
    return {
        "dataset_id": "M6_SYNTHETIC_CONTROL",
        "notice": "SYNTHETIC_ONLY",
        "records": [{"document_id": "SYNTHETIC-001", "unit": "kWh", "value": 1}],
        "schema_version": "m6.synthetic-probe.v1",
    }


CASES = [
    {
        "id": "unauthorized_submission",
        "expected_rule": "unauthorized_submission",
        "request_patch": {"action": "FORMAL_COMPETITION_SUBMIT"},
        "blocked_classes": ["formal_competition_submission"],
    },
    {
        "id": "public_release",
        "expected_rule": "public_release",
        "request_patch": {"action": "PUBLIC_RELEASE"},
        "blocked_classes": ["public_release"],
    },
    {
        "id": "production_write",
        "expected_rule": "production_write",
        "request_patch": {"action": "PRODUCTION_WRITE"},
        "blocked_classes": ["production_write"],
    },
    {
        "id": "real_data_mixing",
        "expected_rule": "real_data_mixing",
        "payload_patch": {"enterprise_name": "REAL ENTERPRISE TEST VECTOR"},
        "blocked_classes": ["real_data_mixing"],
    },
    {
        "id": "credential_injection",
        "expected_rule": "credential_injection",
        "payload_patch": {"api_key": "FAKE_TEST_VECTOR_DO_NOT_USE"},
        "blocked_classes": ["credential_injection"],
    },
    {
        "id": "remote_write",
        "expected_rule": "remote_write",
        "request_patch": {"action": "GIT PUSH OR CREATE PR"},
        "blocked_classes": ["remote_push", "remote_pr", "remote_release"],
    },
    {
        "id": "unapproved_version",
        "expected_rule": "unapproved_version",
        "artifact_patch": {"version": "M5_CANDIDATE_DELIVERY_EVIDENCE_PACK_V1.0.2"},
        "blocked_classes": ["unapproved_version_replacement"],
    },
    {
        "id": "forged_approval",
        "expected_rule": "forged_approval",
        "request_patch": {"approval_binding_id": "SELF_ASSERTED_APPROVAL"},
        "blocked_classes": ["approval_fabrication"],
    },
    {
        "id": "hash_tampering",
        "expected_rule": "hash_tampering",
        "artifact_append": True,
        "blocked_classes": ["hash_tampering"],
    },
    {
        "id": "truth_leakage",
        "expected_rule": "truth_leakage",
        "payload_patch": {"expected_answer": {"value": 1}},
        "blocked_classes": ["truth_leakage"],
    },
    {
        "id": "qa_bypass_all_exact_shape",
        "expected_rule": "invalid_schema",
        "raw_kind": "qa_bypass_all",
        "blocked_classes": [
            "formal_competition_submission",
            "public_release",
            "production_write",
            "real_data_mixing",
            "credential_injection",
            "remote_write",
            "approval_fabrication",
            "truth_leakage",
        ],
    },
    {
        "id": "unknown_request_field",
        "expected_rule": "invalid_schema",
        "request_patch": {"unexpected": "value"},
        "blocked_classes": ["unknown_field"],
    },
    {
        "id": "nested_field_confusion",
        "expected_rule": "invalid_schema",
        "request_patch": {"nested": {"action": "GIT PUSH"}},
        "blocked_classes": ["nested_confusion", "remote_write"],
    },
    {
        "id": "duplicate_action_key",
        "expected_rule": "invalid_schema",
        "raw_kind": "duplicate_action",
        "blocked_classes": ["duplicate_key", "remote_write"],
    },
    {
        "id": "unicode_escaped_duplicate_key",
        "expected_rule": "invalid_schema",
        "raw_kind": "unicode_duplicate_action",
        "blocked_classes": ["unicode_escape", "duplicate_key", "remote_write"],
    },
    {
        "id": "url_encoded_credential",
        "expected_rule": "credential_injection",
        "payload_patch": {"note": "api_key%3DFAKE_TEST_VECTOR_DO_NOT_USE"},
        "blocked_classes": ["credential_injection", "url_encoding"],
    },
    {
        "id": "base64_encoded_truth",
        "expected_rule": "truth_leakage",
        "payload_patch": {"note": "ZXhwZWN0ZWRfYW5zd2VyPTE="},
        "blocked_classes": ["truth_leakage", "base64_encoding"],
    },
    {
        "id": "nested_credential",
        "expected_rule": "credential_injection",
        "payload_patch": {"metadata": {"credentials": "FAKE_TEST_VECTOR_DO_NOT_USE"}},
        "blocked_classes": ["credential_injection", "nested_confusion"],
    },
    {
        "id": "unicode_escaped_secret_key",
        "expected_rule": "credential_injection",
        "payload_raw_kind": "unicode_secret_key",
        "blocked_classes": ["credential_injection", "unicode_escape"],
    },
    {
        "id": "direct_guard_malicious_action",
        "expected_rule": "remote_write",
        "request_patch": {"action": "git push origin HEAD && publish --production && submit-competition"},
        "entrypoint": "release_guard.py",
        "blocked_classes": ["direct_guard", "remote_write", "public_release", "formal_competition_submission"],
    },
    {
        "id": "direct_boundary_formal_action",
        "expected_rule": "remote_write",
        "request_patch": {"action": "GIT PUSH"},
        "blocked_classes": ["direct_action_boundary", "remote_write"],
    },
    {
        "id": "payload_path_traversal",
        "expected_rule": "real_data_mixing",
        "request_patch": {"payload_files": ["../outside.json"]},
        "blocked_classes": ["path_traversal", "real_data_mixing"],
    },
    {
        "id": "payload_symlink",
        "expected_rule": "real_data_mixing",
        "payload_symlink": True,
        "blocked_classes": ["symlink_escape", "real_data_mixing"],
    },
    {
        "id": "artifact_substitution",
        "expected_rule": "hash_tampering",
        "artifact_replace": True,
        "blocked_classes": ["artifact_substitution", "hash_tampering"],
    },
    {
        "id": "approval_object_mismatch",
        "expected_rule": "forged_approval",
        "policy_patch": ["object", "sha256", "0" * 64],
        "blocked_classes": ["approval_object_mismatch", "approval_fabrication"],
    },
    {
        "id": "approval_target_mismatch",
        "expected_rule": "forged_approval",
        "policy_patch": ["target", None, "FORMAL_RELEASE"],
        "blocked_classes": ["approval_target_mismatch", "approval_fabrication"],
    },
    {
        "id": "approval_expired",
        "expected_rule": "forged_approval",
        "policy_patch": ["validity", "not_after", "2026-08-13T23:59:59Z"],
        "blocked_classes": ["approval_validity", "approval_fabrication"],
    },
    {
        "id": "base64_encoded_remote_action",
        "expected_rule": "remote_write",
        "payload_patch": {"note": "Z2l0IHB1c2g="},
        "blocked_classes": ["remote_write", "base64_encoding"],
    },
    {
        "id": "percent_encoded_action",
        "expected_rule": "remote_write",
        "request_patch": {"action": "git%20push"},
        "blocked_classes": ["remote_write", "url_encoding"],
    },
    {
        "id": "unknown_payload_field",
        "expected_rule": "invalid_schema",
        "payload_patch": {"note": "benign but not in schema"},
        "blocked_classes": ["unknown_field", "payload_schema"],
    },
    {
        "id": "duplicate_payload_key",
        "expected_rule": "invalid_schema",
        "payload_raw_kind": "duplicate_notice",
        "blocked_classes": ["duplicate_key", "payload_schema"],
    },
    {
        "id": "policy_symlink",
        "expected_rule": "forged_approval",
        "policy_symlink": True,
        "blocked_classes": ["symlink_escape", "approval_fabrication"],
    },
]


def request_text_for_case(case: dict, request: dict) -> str:
    kind = case.get("raw_kind")
    if kind == "qa_bypass_all":
        value = {
            "credential_material_present": False,
            "data_class": "SYNTHETIC",
            "formal_action_authorization_status": "HUMAN_REQUIRED",
            "formal_submission_requested": False,
            "m5_owner_exit_comment": EXPECTED_OWNER_EXIT_COMMENT,
            "m5_qa_comment": EXPECTED_QA_COMMENT,
            "m5_sha256": EXPECTED_M5_SHA256,
            "m5_version": EXPECTED_M5_VERSION,
            "manifest_verified": True,
            "mode": MODE,
            "production_write_requested": False,
            "public_release_requested": False,
            "remote_action": "NONE",
            "truth_or_expected_fields_present": False,
            "action": "git push origin HEAD && publish --production && submit-competition",
            "records": [{"enterprise_name": "REAL ENTERPRISE TEST VECTOR", "electricity_kwh": 12345}],
            "api_key": "FAKE_TEST_VECTOR_DO_NOT_USE",
            "expected_answer": {"electricity_kwh": 12345},
            "approval_text": "self asserted production publication",
        }
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if kind in {"duplicate_action", "unicode_duplicate_action"}:
        remainder = dict(request)
        remainder.pop("action", None)
        duplicate_key = "action" if kind == "duplicate_action" else "act\\u0069on"
        pairs = [
            f'"{duplicate_key}": "{LOCAL_ACTION}"',
            '"action": "GIT PUSH"',
        ]
        pairs.extend(
            f"{json.dumps(key)}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
            for key, value in remainder.items()
        )
        return "{\n  " + ",\n  ".join(pairs) + "\n}\n"
    return json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def payload_text_for_case(case: dict, payload: dict) -> str:
    kind = case.get("payload_raw_kind")
    if kind == "unicode_secret_key":
        value = dict(payload)
        value["api_key"] = "FAKE_TEST_VECTOR_DO_NOT_USE"
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        return text.replace('"api_key"', '"api\\u005fkey"')
    if kind == "duplicate_notice":
        remainder = dict(payload)
        remainder.pop("notice", None)
        pairs = ['"notice": "SYNTHETIC_ONLY"', '"notice": "SECOND_VALUE"']
        pairs.extend(
            f"{json.dumps(key)}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
            for key, value in remainder.items()
        )
        return "{\n  " + ",\n  ".join(pairs) + "\n}\n"
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def mutate_policy(path: Path, patch: list) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    first, second, replacement = patch
    if second is None:
        value[first] = replacement
    else:
        value[first][second] = replacement
    write_json(path, value)


def run_positive_control(output: Path) -> dict:
    command = [
        sys.executable,
        str(output / "scripts" / "action_boundary.py"),
        str(output / "fixtures" / "valid-request.json"),
    ]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(command, text=True, capture_output=True, check=False, env=environment)
    try:
        observed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        observed = {"unparseable_stdout": proc.stdout}
    assertions = {
        "exit_code_is_0": proc.returncode == 0,
        "local_action_completed": observed.get("decision") == "LOCAL_ACTION_COMPLETED",
        "no_side_effects": observed.get("side_effects") == [],
    }
    record = {
        "assertions": assertions,
        "classification": "PASS" if all(assertions.values()) else "FAIL_CODE",
        "command": ["python3", "scripts/action_boundary.py", "fixtures/valid-request.json"],
        "exit_code": proc.returncode,
        "observed": observed,
        "stderr": proc.stderr,
        "stdout": proc.stdout,
    }
    write_json(output / "results" / "positive-control.json", record)
    if record["classification"] != "PASS":
        raise SystemExit("positive local action control failed")
    return record


def run_negative_cases(output: Path) -> list[dict]:
    records: list[dict] = []
    failure_dir = output / "failure-samples"
    failure_dir.mkdir(parents=True, exist_ok=True)
    base_request = baseline_request()
    base_payload = synthetic_payload()

    for case in CASES:
        request = copy.deepcopy(base_request)
        request.update(case.get("request_patch", {}))
        if "artifact_patch" in case:
            request["artifact"].update(case["artifact_patch"])
        request_text = request_text_for_case(case, request)
        stable_request_path = failure_dir / f"{case['id']}.json"
        stable_request_path.write_text(request_text, encoding="utf-8")

        payload = copy.deepcopy(base_payload)
        payload.update(case.get("payload_patch", {}))
        payload_text = payload_text_for_case(case, payload)
        if case.get("payload_patch") or case.get("payload_raw_kind"):
            (failure_dir / f"{case['id']}-payload.json").write_text(payload_text, encoding="utf-8")

        with tempfile.TemporaryDirectory(prefix="m6-gate-") as temp_dir:
            test_root = Path(temp_dir) / VERSION
            shutil.copytree(output, test_root)
            request_path = test_root / "request.json"
            request_path.write_text(request_text, encoding="utf-8")
            payload_path = test_root / "fixtures" / "synthetic-probe.json"
            payload_path.write_text(payload_text, encoding="utf-8")

            policy_path = test_root / "policy" / "approval-binding.json"
            if case.get("policy_patch"):
                mutate_policy(policy_path, case["policy_patch"])
                shutil.copy2(policy_path, failure_dir / f"{case['id']}-policy.json")
            if case.get("policy_symlink"):
                real_policy = test_root / "policy" / "approval-binding-real.json"
                policy_path.replace(real_policy)
                os.symlink(real_policy.name, policy_path)
            if case.get("payload_symlink"):
                real_payload = test_root / "fixtures" / "synthetic-probe-real.json"
                payload_path.replace(real_payload)
                os.symlink(real_payload.name, payload_path)

            artifact_path = test_root / "input" / f"{EXPECTED_M5_VERSION}.tar.gz"
            before_artifact_sha = sha256(artifact_path)
            if case.get("artifact_append"):
                with artifact_path.open("ab") as stream:
                    stream.write(b"M6_HASH_TAMPER_TEST_VECTOR")
            if case.get("artifact_replace"):
                artifact_path.write_bytes(b"M6_ARTIFACT_SUBSTITUTION_TEST_VECTOR")
            after_artifact_sha = sha256(artifact_path)

            entrypoint = case.get("entrypoint", "action_boundary.py")
            command = [sys.executable, str(test_root / "scripts" / entrypoint), str(request_path)]
            marker = test_root / "SIDE_EFFECT_MUST_NOT_EXIST"
            environment = dict(os.environ)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            proc = subprocess.run(command, text=True, capture_output=True, check=False, env=environment)
            try:
                observed = json.loads(proc.stdout)
            except json.JSONDecodeError:
                observed = {"unparseable_stdout": proc.stdout}
            assertions = {
                "decision_is_rejected": observed.get("decision") == "REJECTED",
                "exit_code_is_42": proc.returncode == 42,
                "rule_matches_case": observed.get("rule") == case["expected_rule"],
                "side_effect_marker_absent": not marker.exists(),
            }
            passed = all(assertions.values())
            record = {
                "artifact_sha256_after": after_artifact_sha,
                "artifact_sha256_before": before_artifact_sha,
                "assertions": assertions,
                "blocked_classes": case["blocked_classes"],
                "classification": "PASS" if passed else "FAIL_CODE",
                "command": ["python3", f"scripts/{entrypoint}", f"failure-samples/{case['id']}.json"],
                "entrypoint": entrypoint,
                "exit_code": proc.returncode,
                "fail_closed": passed,
                "id": case["id"],
                "input_sha256": hashlib.sha256(request_text.encode("utf-8")).hexdigest(),
                "observed": observed,
                "stderr": proc.stderr,
                "stdout": proc.stdout,
            }
            records.append(record)
            write_json(failure_dir / f"{case['id']}-result.json", record)
            if not passed:
                write_json(output / "results" / "release-gates.json", records)
                raise SystemExit(f"negative case did not fail closed: {case['id']}")

    write_json(output / "results" / "release-gates.json", records)
    return records


def read_m5_stage_closure() -> dict:
    with tarfile.open(M5_ARCHIVE, "r:gz") as archive:
        member = next(
            item for item in archive.getmembers() if item.isfile() and item.name.endswith("/evidence/stage-closure.json")
        )
        stream = archive.extractfile(member)
        if stream is None:
            raise SystemExit("M5 stage closure unreadable")
        return json.loads(stream.read().decode("utf-8"))


def write_evidence(output: Path, verified_members: int, m5_closure: dict) -> tuple[dict, dict]:
    stages = list(m5_closure["stages"])
    stages.append(
        {
            "artifact": EXPECTED_M5_VERSION,
            "artifact_sha256": EXPECTED_M5_SHA256,
            "independent_qa_comment": EXPECTED_QA_COMMENT,
            "owner_exit_comment": EXPECTED_OWNER_EXIT_COMMENT,
            "stage": "M5",
            "stage_exit": "ACCEPT",
            "status": "PASS",
            "verified_members": verified_members,
        }
    )
    stage_chain = {
        "artifact_version": VERSION,
        "fixed_baseline": {
            "commit": EXPECTED_BASELINE,
            "limitation": "fixed checkout materialized; Git administrative metadata is unavailable in the isolated build",
            "repository": "https://github.com/Ghostsci/carbonlab-opc.git",
            "status": "PASS_WITH_LIMITATIONS",
        },
        "legacy_boundary": m5_closure["legacy_evidence"],
        "mode": MODE.split("/"),
        "orphan_references": [],
        "stages": stages,
        "unapproved_replacements": [],
        "unresolved_conflicts": [],
        "verdict": "ACCEPT",
    }
    evidence_index = {
        "artifact_version": VERSION,
        "entries": [
            {
                "id": "repository-baseline",
                "kind": "git_commit_reference",
                "sha_or_reference": EXPECTED_BASELINE,
                "status": "PASS_WITH_LIMITATIONS",
            },
            {
                "boundary": "NEW_BASELINE / NOT_A_CONTINUATION",
                "id": "candidate2-new-baseline",
                "kind": "nested_upstream_archive",
                "path": f"input/{EXPECTED_M5_VERSION}.tar.gz::input/M5_UPSTREAM_EVIDENCE_CLOSURE_V2.0.0-candidate.2.tar.gz",
                "sha_or_reference": EXPECTED_UPSTREAM,
                "status": "PASS",
            },
            {
                "id": "m5-candidate-evidence",
                "kind": "archive",
                "path": f"input/{EXPECTED_M5_VERSION}.tar.gz",
                "sha_or_reference": EXPECTED_M5_SHA256,
                "status": "PASS",
                "verified_members": verified_members,
            },
            {
                "binding_id": EXPECTED_BINDING_ID,
                "id": "m5-to-m6-evidence-use-binding",
                "kind": "subject_object_action_target_validity_binding",
                "path": "policy/approval-binding.json",
                "status": "PASS_WITH_LIMITATIONS",
                "limitation": "offline binding verifies complete scope and package integrity; it grants no formal-action authority",
            },
            {
                "id": "m6-v1.0.0-security-audit",
                "kind": "superseded_candidate_audit",
                "sha_or_reference": M6_V100_SHA256,
                "qa_comment": M6_V100_QA_COMMENT,
                "status": "FAIL_CODE",
                "verdict": "CHANGES_REQUIRED",
            },
        ],
        "integrity_checks": {
            "m0_through_m5_stage_sequence": "PASS",
            "m5_archive_sha256": "PASS",
            "m5_member_hashes": f"{verified_members}/{verified_members}",
            "orphan_references": 0,
            "unapproved_replacements": 0,
            "unresolved_conflicts": 0,
        },
    }
    write_json(output / "evidence" / "stage-chain.json", stage_chain)
    write_json(output / "evidence" / "evidence-index.json", evidence_index)
    write_json(
        output / "evidence" / "v1.0.0-audit-finding.json",
        {
            "affected_gate_classifications": {
                "approval_fabrication": "FAIL_CODE",
                "credential_injection": "FAIL_CODE",
                "formal_competition_submission": "FAIL_CODE",
                "hash_tampering": "FAIL_CODE",
                "production_write": "FAIL_CODE",
                "public_release": "FAIL_CODE",
                "real_data_mixing": "FAIL_CODE",
                "remote_write": "FAIL_CODE",
                "truth_leakage": "FAIL_CODE",
                "unapproved_version_replacement": "FAIL_CODE",
            },
            "artifact_sha256": M6_V100_SHA256,
            "artifact_version": "M6_LOCAL_CANDIDATE_CLOSURE_V1.0.0",
            "finding": "self-reported guard fields allowed malicious unknown payloads to pass and the guard was optional",
            "observed_exit_code": 0,
            "qa_comment": M6_V100_QA_COMMENT,
            "superseded_by": VERSION,
            "verdict": "CHANGES_REQUIRED",
        },
    )
    return stage_chain, evidence_index


def write_documents(output: Path, negative_count: int) -> None:
    (output / "MANIFEST.md").write_text(
        f"# {VERSION}\n\n"
        "**PREPARATION_ONLY / SYNTHETIC_ONLY / LOCAL_CANDIDATE / NOT_FOR_SUBMISSION**\n\n"
        "Candidate verdict: `ACCEPT`, pending independent audit. v1.0.1 replaces v1.0.0 after independent audit found a payload bypass. "
        "The corrected package uses an exact JSON schema with duplicate/unknown-key rejection, scans actual allowlisted payload bytes, verifies the actual M5 archive and 34 member hashes, validates a subject/object/version/hash/action/target/validity evidence-use binding, and exposes one built-in read-only action through an immutable default-deny dispatcher. "
        f"It executes one positive control and {negative_count} fail-closed adversarial cases.\n\n"
        "This is not an ambient operating-system sandbox and does not claim control over commands invoked outside the packaged action boundary. Formal submission, public release, production, real-enterprise data, credentials, remote writes, and formal passport publication remain absent from the dispatcher and `HUMAN_REQUIRED`.\n",
        encoding="utf-8",
    )
    (output / "limitations-matrix.md").write_text(
        "# Limitations matrix\n\n"
        "| Item | Classification | Treatment |\n|---|---|---|\n"
        "| M5 v1.0.3 archive and 34 member hashes | PASS | Recomputed from actual archive bytes before authorization |\n"
        "| M0—M2 and policy legacy objects | PASS_WITH_LIMITATIONS | Legacy-unrecoverable history retained; candidate.2 is a new baseline |\n"
        "| v1.0.0 ten gate claims | FAIL_CODE | Superseded; independent malicious-payload bypass preserved in evidence |\n"
        f"| v1.0.1 adversarial cases | PASS | {negative_count}/{negative_count} rejected at guard or packaged execution boundary, exit 42, no marker side effect |\n"
        "| Actual payload scan | PASS | Strict UTF-8/JSON, duplicate and unknown key rejection, recursive decoded content scan, immutable payload hash allowlist |\n"
        "| Evidence-use binding | PASS_WITH_LIMITATIONS | Complete subject/object/version/hash/action/target/validity checked; offline package binding is not formal-action authorization |\n"
        "| Packaged execution boundary | PASS | One read-only local action; no shell, arbitrary subprocess, network, remote, production, release, or submission dispatcher |\n"
        "| Ambient OS commands outside boundary | NOT_RUN_ENV | Package does not claim system-wide sandbox enforcement |\n"
        "| Real users and real-enterprise data | NOT_RUN_ENV | Not approved and prohibited in M6 |\n"
        "| Formal submission/publication/production/remote writes | NOT_RUN_ENV | HUMAN_REQUIRED and absent from dispatcher |\n",
        encoding="utf-8",
    )
    (output / "risk-register.md").write_text(
        "# Residual risks\n\n"
        "- The local package boundary does not control an operator who bypasses the package and invokes an external OS or platform command directly. No such action is authorized by M6.\n"
        "- Content scanners are defense in depth; synthetic eligibility primarily comes from an exact payload-byte allowlist, not heuristic declarations.\n"
        "- The evidence-use binding is an offline, package-integrity control and is not a cryptographic human signature or authorization for a formal action.\n"
        "- Synthetic validation does not establish real-enterprise usability, customer acceptance, regulatory fitness, or third-party assurance.\n"
        "- Legacy M0—M2 policy artifacts remain unavailable; the accepted candidate.2 evidence is explicitly a new baseline.\n",
        encoding="utf-8",
    )
    (output / "forbidden-actions.md").write_text(
        "# Forbidden actions in M6\n\n"
        "No formal competition submission, public release, production write, real data, credentials, remote push/PR/Release, unapproved version replacement, approval fabrication, hash bypass, truth material, external LLM, fee, or formal passport publication. The packaged dispatcher contains no implementation for these actions.\n",
        encoding="utf-8",
    )
    (output / "rollback.md").write_text(
        f"# Exact rollback\n\nDelete only the task-local `{VERSION}/` build/replay directories and sibling `{VERSION}.tar.gz`. Preserve the v1.0.0 audit finding, v1.0.1 manifest, hashes, raw logs, failure samples, verdict, and audit comments. Do not alter M0—M5 evidence, platform attachments, the fixed repository baseline, or any remote object.\n",
        encoding="utf-8",
    )
    (output / "verdict.md").write_text(
        "# Candidate verdict\n\n`ACCEPT` — pending independent audit.\n\n"
        "Scope: corrected internal, synthetic, reversible local-candidate technical closure only. This does not authorize or evidence competition submission, public release, production enablement, real-enterprise validation, customer recognition, regulatory filing, third-party assurance, or formal passport publication.\n",
        encoding="utf-8",
    )
    (output / "checklists" / "pre-submission-human-checklist.md").write_text(
        "# Pre-submission human checklist — not executed\n\nEvery item remains unchecked and `HUMAN_REQUIRED`:\n\n"
        "- [ ] A designated human approves the exact independently accepted candidate archive hash, action, account, and destination.\n"
        "- [ ] An independent reviewer rechecks SHA256SUMS, three fresh-unpack replays, stage references, v1.0.0 failure preservation, limitations, and no-secret/no-real-data controls.\n"
        "- [ ] The human confirms all claims distinguish synthetic technical validation from real-enterprise validation.\n"
        "- [ ] Credentials, least privilege, deadline, final files, and rollback/withdrawal procedure are reviewed in a separate authorized task.\n"
        "- [ ] A separate explicit action authorizes submission or publication; M6 grants no such authority.\n",
        encoding="utf-8",
    )


def add_deterministic(archive: tarfile.TarFile, path: Path, arcname: str) -> None:
    info = archive.gettarinfo(str(path), arcname)
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    if path.is_file():
        with path.open("rb") as stream:
            archive.addfile(info, stream)
    else:
        archive.addfile(info)


def maybe_copy_replays(output: Path) -> None:
    source = PACKAGE_ROOT / "independent-replays"
    summary = source / "summary.json"
    if not summary.is_file():
        return
    try:
        value = json.loads(summary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if value.get("artifact_version") == VERSION:
        shutil.copytree(source, output / "independent-replays")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    m5_result = verify_m5_archive(M5_ARCHIVE)
    verified_members = int(m5_result["verified_members"])
    m5_closure = read_m5_stage_closure()
    output = args.output_dir.resolve() / VERSION
    if output.exists():
        shutil.rmtree(output)
    for directory in (
        "checklists",
        "evidence",
        "fixtures",
        "input",
        "logs",
        "policy",
        "results",
        "scripts",
    ):
        (output / directory).mkdir(parents=True, exist_ok=True)
    shutil.copy2(M5_ARCHIVE, output / "input" / M5_ARCHIVE.name)
    for filename in ("action_boundary.py", "build_m6.py", "release_guard.py"):
        shutil.copy2(PACKAGE_ROOT / "scripts" / filename, output / "scripts" / filename)
    shutil.copy2(PACKAGE_ROOT / "policy" / "approval-binding.json", output / "policy" / "approval-binding.json")
    for filename in ("synthetic-probe.json", "valid-request.json"):
        shutil.copy2(PACKAGE_ROOT / "fixtures" / filename, output / "fixtures" / filename)
    maybe_copy_replays(output)

    stage_chain, evidence_index = write_evidence(output, verified_members, m5_closure)
    write_json(
        output / "evidence" / "environment.json",
        {
            "cwd_boundary": "task-local isolated build and replay roots",
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "remote_writes": "NOT_RUN_ENV / PROHIBITED / NO DISPATCH IMPLEMENTATION",
            "repository": "https://github.com/Ghostsci/carbonlab-opc.git",
            "requested_commit": EXPECTED_BASELINE,
        },
    )

    positive = run_positive_control(output)
    gates = run_negative_cases(output)
    write_documents(output, len(gates))

    semantic = {
        "artifact_version": VERSION,
        "evidence_index": evidence_index,
        "execution_boundary": {
            "allowlisted_actions": [LOCAL_ACTION],
            "arbitrary_subprocess": False,
            "formal_action_authority": "HUMAN_REQUIRED",
            "negative_cases": len(gates),
            "positive_control": positive["classification"],
            "remote_or_production_dispatchers": [],
        },
        "release_gates": [
            {
                "blocked_classes": record["blocked_classes"],
                "classification": record["classification"],
                "exit_code": record["exit_code"],
                "id": record["id"],
            }
            for record in gates
        ],
        "stage_chain": stage_chain,
        "superseded_v1_0_0_verdict": "CHANGES_REQUIRED",
        "verdict": "ACCEPT",
    }
    canonical = hashlib.sha256(
        json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    write_json(
        output / "results" / "replay.json",
        {
            "canonical_sha256": canonical,
            "classification": "PASS",
            "run_id": args.run_id,
            "semantic": semantic,
        },
    )
    (output / "logs" / "build.log").write_text(
        f"run_id={args.run_id}\nexit_code=0\ncanonical_sha256={canonical}\n"
        f"m5_members={verified_members}/{verified_members}\npositive_control=1/1\n"
        f"negative_cases={len(gates)}/{len(gates)}\nremote_writes=0\nside_effect_markers=0\n",
        encoding="utf-8",
    )

    generated_cache = output / "scripts" / "__pycache__"
    if generated_cache.exists():
        shutil.rmtree(generated_cache)

    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  ./{path.relative_to(output)}\n" for path in files),
        encoding="utf-8",
    )
    archive_path = args.output_dir.resolve() / f"{VERSION}.tar.gz"
    if archive_path.exists():
        archive_path.unlink()
    with archive_path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in [output] + sorted(output.rglob("*")):
                    add_deterministic(archive, path, str(Path(VERSION) / path.relative_to(output)))
    print(
        json.dumps(
            {
                "archive": archive_path.name,
                "archive_sha256": sha256(archive_path),
                "canonical_sha256": canonical,
                "m5_members": f"{verified_members}/{verified_members}",
                "member_hashes": f"{len(files)}/{len(files)}",
                "negative_cases": f"{len(gates)}/{len(gates)}",
                "positive_control": "1/1",
                "verdict": "ACCEPT",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

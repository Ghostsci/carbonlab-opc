#!/usr/bin/env python3
"""Strict, content-aware authorization for the M6 local execution boundary."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import sys
import tarfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote


VERSION = "M6_LOCAL_CANDIDATE_CLOSURE_V1.0.1"
MODE = "PREPARATION_ONLY/SYNTHETIC_ONLY/LOCAL_CANDIDATE/NOT_FOR_SUBMISSION"
LOCAL_ACTION = "LOCAL_VALIDATE_FIXED_M5"
LOCAL_TARGET = VERSION
REQUEST_SCHEMA = "m6.local-action-request.v1"
PAYLOAD_SCHEMA = "m6.synthetic-probe.v1"
EXPECTED_M5_VERSION = "M5_CANDIDATE_DELIVERY_EVIDENCE_PACK_V1.0.3"
EXPECTED_M5_SHA256 = "0e900c68ad6dffcac32152c2f19a3e355c2680a0b1cf30d20cc32234c2a4311e"
EXPECTED_QA_COMMENT = "d3249ac5-6e15-4d25-acb2-154debe15883"
EXPECTED_OWNER_EXIT_COMMENT = "a71f3665-e338-48b3-a0ab-5a9c6df4359a"
EXPECTED_BINDING_ID = "M5_TO_M6_LOCAL_EVIDENCE_USE_V1"
EXPECTED_PAYLOAD_SHA256 = "1fb1385de7dee01f8f9f2d751e4ca19c85b14653ee0e75ac130b9edc56334679"
MAX_JSON_BYTES = 1024 * 1024

REQUEST_KEYS = {
    "action",
    "approval_binding_id",
    "artifact",
    "mode",
    "payload_files",
    "schema_version",
    "target",
}
ARTIFACT_KEYS = {"path", "version"}
PAYLOAD_KEYS = {"dataset_id", "notice", "records", "schema_version"}
RECORD_KEYS = {"document_id", "unit", "value"}

EXPECTED_BINDING = {
    "action": LOCAL_ACTION,
    "authority_scope": "LOCAL_EVIDENCE_VALIDATION_ONLY / NO_FORMAL_ACTION_AUTHORITY",
    "binding_id": EXPECTED_BINDING_ID,
    "object": {
        "sha256": EXPECTED_M5_SHA256,
        "type": "evidence_archive",
        "version": EXPECTED_M5_VERSION,
    },
    "schema_version": "m6.approval-binding.v1",
    "subjects": [
        {
            "actor_id": "39aab9d9-d5ff-4556-a761-c94f4640e417",
            "actor_type": "agent",
            "comment_id": EXPECTED_QA_COMMENT,
            "role": "independent_qa",
            "verdict": "ACCEPT",
        },
        {
            "actor_id": "ad3e35d5-2e86-4306-b0f5-1b78e692da3a",
            "actor_type": "agent",
            "comment_id": EXPECTED_OWNER_EXIT_COMMENT,
            "role": "stage_owner_exit_record",
            "verdict": "ACCEPT",
        },
    ],
    "target": LOCAL_TARGET,
    "validity": {
        "not_after": "2030-12-31T23:59:59Z",
        "not_before": "2026-08-14T00:00:00Z",
    },
}


@dataclass
class Rejection(Exception):
    rule: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"decision": "REJECTED", "reason": self.reason, "rule": self.rule}


class DuplicateKey(ValueError):
    pass


def _pairs_to_dict(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKey(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is prohibited: {value}")


def load_json_strict(path: Path) -> Any:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise Rejection("invalid_input", str(exc)) from exc
    if len(payload) > MAX_JSON_BYTES:
        raise Rejection("invalid_input", f"JSON input exceeds {MAX_JSON_BYTES} bytes")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Rejection("invalid_input", f"JSON must be UTF-8: {exc}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_to_dict,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, DuplicateKey, ValueError) as exc:
        raise Rejection("invalid_schema", str(exc)) from exc


def exact_keys(value: Any, expected: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Rejection("invalid_schema", f"{location} must be an object")
    actual = set(value)
    if actual != expected:
        unknown = sorted(actual - expected)
        missing = sorted(expected - actual)
        raise Rejection(
            "invalid_schema",
            f"{location} keys differ; unknown={unknown}, missing={missing}",
        )
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_relative_file(package_root: Path, relative: str, rule: str) -> Path:
    if not isinstance(relative, str):
        raise Rejection("invalid_schema", "file path must be a string")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
        raise Rejection(rule, f"unsafe or non-canonical relative path: {relative}")
    candidate = package_root / Path(*pure.parts)
    if candidate.is_symlink():
        raise Rejection(rule, f"symbolic links are prohibited: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise Rejection(rule, str(exc)) from exc
    root = package_root.resolve(strict=True)
    if root not in resolved.parents or not resolved.is_file():
        raise Rejection(rule, f"file escapes package boundary or is not regular: {relative}")
    return resolved


def safe_tar_member(member: tarfile.TarInfo) -> None:
    name = PurePosixPath(member.name)
    if name.is_absolute() or ".." in name.parts:
        raise Rejection("hash_tampering", f"unsafe M5 archive path: {member.name}")
    if member.issym() or member.islnk() or member.isdev():
        raise Rejection("hash_tampering", f"unsafe M5 member type: {member.name}")


def verify_m5_archive(path: Path) -> dict[str, Any]:
    observed_sha = sha256(path)
    if observed_sha != EXPECTED_M5_SHA256:
        raise Rejection("hash_tampering", "actual M5 archive hash does not match the frozen hash")
    try:
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                safe_tar_member(member)
            files = {member.name: member for member in members if member.isfile()}
            checksum_member = next(
                (member for member in files.values() if member.name.endswith("/SHA256SUMS")),
                None,
            )
            if checksum_member is None:
                raise Rejection("hash_tampering", "M5 SHA256SUMS is missing")
            checksum_stream = archive.extractfile(checksum_member)
            if checksum_stream is None:
                raise Rejection("hash_tampering", "M5 SHA256SUMS is unreadable")
            checksum_lines = checksum_stream.read().decode("utf-8").splitlines()
            archive_root = checksum_member.name.rsplit("/", 1)[0]
            verified = 0
            for line in checksum_lines:
                if not line.strip():
                    continue
                try:
                    expected, relative = line.split(None, 1)
                except ValueError as exc:
                    raise Rejection("hash_tampering", "invalid M5 checksum record") from exc
                relative = relative.strip().lstrip("./")
                member = files.get(f"{archive_root}/{relative}")
                if member is None:
                    raise Rejection("hash_tampering", f"M5 member missing: {relative}")
                stream = archive.extractfile(member)
                if stream is None or hashlib.sha256(stream.read()).hexdigest() != expected:
                    raise Rejection("hash_tampering", f"M5 member hash mismatch: {relative}")
                verified += 1
            if verified != 34:
                raise Rejection("hash_tampering", f"M5 checksum count is {verified}, expected 34")
            closure_member = next(
                (member for member in files.values() if member.name.endswith("/evidence/stage-closure.json")),
                None,
            )
            if closure_member is None:
                raise Rejection("hash_tampering", "M5 stage closure is missing")
            closure_stream = archive.extractfile(closure_member)
            if closure_stream is None:
                raise Rejection("hash_tampering", "M5 stage closure is unreadable")
            closure = json.loads(closure_stream.read().decode("utf-8"))
    except (OSError, tarfile.TarError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejection("hash_tampering", f"M5 verification failed: {exc}") from exc
    if closure.get("artifact_version") != EXPECTED_M5_VERSION:
        raise Rejection("unapproved_version", "actual M5 artifact version is not frozen v1.0.3")
    if closure.get("verdict") != "ACCEPT_CANDIDATE":
        raise Rejection("forged_approval", "M5 package candidate verdict is not accepted")
    return {"archive_sha256": observed_sha, "verified_members": verified}


def normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def decoded_variants(value: str) -> set[str]:
    variants = {unicodedata.normalize("NFKC", value)}
    for _ in range(2):
        variants |= {unquote(item) for item in list(variants)}
        variants |= {html.unescape(item) for item in list(variants)}
    for item in list(variants):
        compact = re.sub(r"\s+", "", item)
        if len(compact) >= 8 and len(compact) % 4 == 0 and re.fullmatch(r"[A-Za-z0-9+/=]+", compact):
            try:
                decoded = base64.b64decode(compact, validate=True).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                continue
            if all(character.isprintable() or character.isspace() for character in decoded):
                variants.add(decoded)
        if len(compact) >= 8 and len(compact) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
            try:
                decoded = bytes.fromhex(compact).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                continue
            if all(character.isprintable() or character.isspace() for character in decoded):
                variants.add(decoded)
    return {unicodedata.normalize("NFKC", item).casefold() for item in variants}


def scan_node(value: Any, location: str = "$") -> None:
    secret_keys = {
        "api_key",
        "apikey",
        "authorization",
        "bearer_token",
        "credential",
        "credentials",
        "password",
        "private_key",
        "secret",
        "token",
    }
    truth_keys = {
        "answer_key",
        "expected",
        "expected_answer",
        "gold",
        "ground_truth",
        "label",
        "truth",
    }
    real_keys = {
        "business_registration_number",
        "enterprise_name",
        "real_enterprise",
        "tax_id",
        "unified_social_credit_code",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = normalize_key(key)
            if normalized in secret_keys:
                raise Rejection("credential_injection", f"credential-like key in actual payload at {location}.{key}")
            if normalized in truth_keys:
                raise Rejection("truth_leakage", f"truth-like key in actual payload at {location}.{key}")
            if normalized in real_keys:
                raise Rejection("real_data_mixing", f"real-enterprise key in actual payload at {location}.{key}")
            scan_node(item, f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            scan_node(item, f"{location}[{index}]")
        return
    if not isinstance(value, str):
        return
    for variant in decoded_variants(value):
        if re.search(r"(?:api[_ -]?key|password|private[_ -]?key|bearer|credential|token)\s*[:=]", variant):
            raise Rejection("credential_injection", f"credential pattern in actual payload at {location}")
        if re.search(r"\b(?:sk|rk|pk)-(?:test|live)-[a-z0-9_-]{6,}\b", variant):
            raise Rejection("credential_injection", f"secret-like value in actual payload at {location}")
        if re.search(r"(?:expected[_ -]?answer|ground[_ -]?truth|answer[_ -]?key)\s*[:=]", variant):
            raise Rejection("truth_leakage", f"truth pattern in actual payload at {location}")
        if "real enterprise" in variant or "real_enterprise" in variant:
            raise Rejection("real_data_mixing", f"real-enterprise marker in actual payload at {location}")
        if re.search(r"\bgit\s+push\b|submit[-_ ]competition|publish\s+--production|\bproduction[_ -]?write\b", variant):
            raise Rejection("remote_write", f"forbidden action content in actual payload at {location}")


def verify_payload(path: Path) -> dict[str, Any]:
    value = load_json_strict(path)
    scan_node(value)
    payload = exact_keys(value, PAYLOAD_KEYS, "payload")
    if payload["schema_version"] != PAYLOAD_SCHEMA:
        raise Rejection("real_data_mixing", "payload schema is not the frozen synthetic schema")
    if payload["dataset_id"] != "M6_SYNTHETIC_CONTROL" or payload["notice"] != "SYNTHETIC_ONLY":
        raise Rejection("real_data_mixing", "payload identity is not the frozen synthetic control")
    records = payload["records"]
    if not isinstance(records, list) or len(records) != 1:
        raise Rejection("real_data_mixing", "synthetic payload must contain exactly one control record")
    record = exact_keys(records[0], RECORD_KEYS, "payload.records[0]")
    if record != {"document_id": "SYNTHETIC-001", "unit": "kWh", "value": 1}:
        raise Rejection("real_data_mixing", "payload record differs from the frozen synthetic control")
    observed = sha256(path)
    if observed != EXPECTED_PAYLOAD_SHA256:
        raise Rejection("real_data_mixing", "actual payload hash is not on the immutable synthetic allowlist")
    return {"path": "fixtures/synthetic-probe.json", "sha256": observed}


def parse_rfc3339(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Rejection("forged_approval", f"invalid approval validity timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise Rejection("forged_approval", "approval validity timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def verify_binding(package_root: Path, binding_id: str) -> dict[str, Any]:
    if binding_id != EXPECTED_BINDING_ID:
        raise Rejection("forged_approval", "request does not reference the frozen evidence-use binding")
    path = safe_relative_file(package_root, "policy/approval-binding.json", "forged_approval")
    binding = load_json_strict(path)
    if binding != EXPECTED_BINDING:
        raise Rejection(
            "forged_approval",
            "approval binding must match subject, object version/hash, action, target, scope, and validity",
        )
    now = datetime.now(timezone.utc)
    not_before = parse_rfc3339(binding["validity"]["not_before"])
    not_after = parse_rfc3339(binding["validity"]["not_after"])
    if not not_before <= now <= not_after:
        raise Rejection("forged_approval", "approval binding is outside its validity period")
    digest = hashlib.sha256(
        json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"binding_id": binding_id, "canonical_sha256": digest, "scope": binding["authority_scope"]}


def forbidden_action_rule(action: Any) -> str | None:
    if not isinstance(action, str):
        return "invalid_schema"
    normalized = " ".join(
        re.sub(r"[^a-z0-9]+", " ", variant).strip()
        for variant in decoded_variants(action)
    )
    if re.search(
        r"\bgit\s+push\b|\bremote\b|\bpull request\b|\bcreate pr\b|\bgit release\b|\bremote release\b",
        normalized,
    ):
        return "remote_write"
    if re.search(r"submit[-_ ]competition|formal[_ -]?submission|competition[_ -]?submit", normalized):
        return "unauthorized_submission"
    if re.search(r"public release|publish production", normalized):
        return "public_release"
    if re.search(r"production[_ -]?write|write[_ -]?production|production[_ -]?enable", normalized):
        return "production_write"
    return None


def authorize(request_path: Path, package_root: Path) -> dict[str, Any]:
    request = exact_keys(load_json_strict(request_path), REQUEST_KEYS, "request")
    if request["schema_version"] != REQUEST_SCHEMA:
        raise Rejection("invalid_schema", "request schema version is not frozen")
    if request["mode"] != MODE:
        raise Rejection("unauthorized_submission", "execution mode is outside the local-candidate boundary")
    action_rule = forbidden_action_rule(request["action"])
    if request["action"] != LOCAL_ACTION:
        raise Rejection(action_rule or "unauthorized_submission", "action is absent from the immutable local allowlist")
    if request["target"] != LOCAL_TARGET:
        raise Rejection("unauthorized_submission", "target is not the local M6 v1.0.1 candidate")
    artifact = exact_keys(request["artifact"], ARTIFACT_KEYS, "request.artifact")
    if artifact["path"] != f"input/{EXPECTED_M5_VERSION}.tar.gz":
        raise Rejection("unapproved_version", "artifact path is not the frozen M5 v1.0.3 path")
    if artifact["version"] != EXPECTED_M5_VERSION:
        raise Rejection("unapproved_version", "artifact version is not frozen M5 v1.0.3")
    payload_files = request["payload_files"]
    if payload_files != ["fixtures/synthetic-probe.json"]:
        raise Rejection("real_data_mixing", "payload list is not the immutable synthetic allowlist")

    binding = verify_binding(package_root, request["approval_binding_id"])
    artifact_path = safe_relative_file(package_root, artifact["path"], "hash_tampering")
    archive = verify_m5_archive(artifact_path)
    payload_path = safe_relative_file(package_root, payload_files[0], "real_data_mixing")
    payload = verify_payload(payload_path)
    return {
        "action": LOCAL_ACTION,
        "approval_binding": binding,
        "artifact": archive,
        "decision": "AUTHORIZED_FOR_LOCAL_VALIDATION_ONLY",
        "payloads": [payload],
        "target": LOCAL_TARGET,
    }


def run_cli(request_path: Path, package_root: Path) -> int:
    try:
        result = authorize(request_path, package_root)
    except Rejection as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False, sort_keys=True))
        return 42
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: release_guard.py REQUEST.json", file=sys.stderr)
        return 2
    package_root = Path(__file__).resolve().parent.parent
    return run_cli(Path(sys.argv[1]), package_root)


if __name__ == "__main__":
    raise SystemExit(main())

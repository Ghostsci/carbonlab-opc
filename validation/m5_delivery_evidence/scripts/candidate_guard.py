#!/usr/bin/env python3
"""Fail-closed policy guard for the local M5 candidate evidence package."""
import json
import sys
from pathlib import Path

EXPECTED_M4 = "d60d30cf2e124d4b7c9e59c33dc777397fadcb1c13350bebe55eee405dfa4219"
EXPECTED_M3 = "1.0.3"


def reject(rule, reason):
    print(json.dumps({"decision": "REJECTED", "rule": rule, "reason": reason}, sort_keys=True))
    return 42


def evaluate(value):
    if value.get("publish_allowed") is not False:
        return reject("unauthorized_publish", "candidate mode requires publish_allowed=false")
    if value.get("approval") != "immutable_external_records":
        return reject("forged_approval", "approval must bind to immutable independent records")
    if value.get("m4_sha256") != EXPECTED_M4:
        return reject("attachment_substitution", "fixed M4 digest mismatch")
    if value.get("manifest_verified") is not True:
        return reject("hash_tampering", "manifest verification must succeed")
    if "truth" in value or "expected" in value:
        return reject("truth_leakage", "truth and expected fields are prohibited")
    if value.get("data_class") != "SYNTHETIC":
        return reject("real_data_mixing", "only synthetic data is permitted")
    if value.get("m3_version") != EXPECTED_M3:
        return reject("unapproved_version", "unapproved M3 version")
    if value.get("formal_write_allowed") is not False:
        return reject("production_write", "formal writes are prohibited")
    print(json.dumps({"decision": "ACCEPTED_FOR_LOCAL_VALIDATION_ONLY"}, sort_keys=True))
    return 0


def main():
    if len(sys.argv) != 2:
        print("usage: candidate_guard.py INPUT.json", file=sys.stderr)
        return 2
    try:
        value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"decision": "REJECTED", "rule": "invalid_input", "reason": str(exc)}, sort_keys=True))
        return 42
    if not isinstance(value, dict):
        return reject("invalid_input", "top-level JSON must be an object")
    return evaluate(value)


if __name__ == "__main__":
    raise SystemExit(main())

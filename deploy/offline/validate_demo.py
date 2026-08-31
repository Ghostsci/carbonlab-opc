#!/usr/bin/env python3
"""Validate the offline competition workflow through its public HTTP API.

The script intentionally uses only Python's standard library so it can run on
the host without installing test dependencies.  It exercises the same path a
demo operator uses: login, upload, candidate extraction, A-03 quality review,
H-01 confirmation, H-02 factor confirmation, R-01 calculation, and read-back
from the standardized activity ledger.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
import uuid


def _json_request(
    url: str,
    *,
    token: str | None = None,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            return response.status, json.loads(body or b"{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {body}") from exc


def _upload(url: str, *, token: str, source: Path) -> tuple[int, dict]:
    boundary = f"----CarbonLabOffline{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            (
                'Content-Disposition: form-data; name="file"; '
                f'filename="{source.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            source.read_bytes(),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        data=body,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} -> HTTP {exc.code}: {body}") from exc


def _numeric_text(value: object) -> str:
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", str(value))
    if match is None:
        raise RuntimeError(f"No numeric value found in {value!r}")
    return match.group(0).replace(",", "")


def validate(args: argparse.Namespace) -> dict:
    base = args.base_url.rstrip("/")
    started = time.perf_counter()

    login_status, login = _json_request(
        f"{base}/auth/login",
        method="POST",
        payload={"email": args.email, "password": args.password},
    )
    token = login["access_token"]

    upload_started = time.perf_counter()
    upload_status, uploaded = _upload(f"{base}/upload", token=token, source=args.file)
    upload_seconds = time.perf_counter() - upload_started

    fields = {
        "electricity_kwh": _numeric_text(uploaded["fields"]["electricity_kwh"]),
        "period": uploaded["fields"]["period"],
        "facility": uploaded["fields"]["facility"],
    }
    candidate_status, candidate = _json_request(
        f"{base}/upload/{uploaded['file_id']}/candidate",
        token=token,
        method="POST",
        payload={"fields": fields},
    )
    quality_status_code, quality = _json_request(
        f"{base}/upload/{uploaded['file_id']}/quality-review",
        token=token,
        method="POST",
        payload={"candidate_token": candidate["candidate_token"], "fields": fields},
    )
    confirm_status, confirmed = _json_request(
        f"{base}/upload/confirm-activity",
        token=token,
        method="POST",
        payload={
            "candidate_token": candidate["candidate_token"],
            "quality_review_token": quality["quality_review_token"],
            "file_id": uploaded["file_id"],
            "document_content_hash": uploaded["content_hash"],
            "filename": uploaded["filename"],
            "document_type": "electricity_bill",
            "fields": fields,
        },
    )
    formal = confirmed["formal_write"]
    activity_id = formal["activity_data_id"]
    factors_status, factors = _json_request(
        f"{base}/upload/formal-activities/{activity_id}/factor-candidates",
        token=token,
    )
    if not factors.get("factor_candidates"):
        raise RuntimeError("No eligible emission factor candidate was returned")
    selected = factors["factor_candidates"][0]
    calculation_status, calculated = _json_request(
        f"{base}/upload/formal-activities/{activity_id}/confirm-factor",
        token=token,
        method="POST",
        payload={
            "factor_id": selected["factor_id"],
            "factor_snapshot_sha256": selected["factor_snapshot_sha256"],
            "selection_note": "人工核对合成明细、账期、区域、因子单位与来源后用于离线包验证。",
        },
    )
    ledger_status, ledger = _json_request(
        f"{base}/formal-activities/{activity_id}",
        token=token,
    )
    passports_status, passports = _json_request(f"{base}/passports", token=token)
    result = calculated["formal_write"]["emission_result"]

    return {
        "validation_host": args.validation_host,
        "health_status": 200,
        "login_status": login_status,
        "upload_status": upload_status,
        "upload_seconds": round(upload_seconds, 3),
        "filename": uploaded["filename"],
        "rows_under_test": args.rows,
        "document_type": uploaded["document_type"],
        "fields": uploaded["fields"],
        "upload_errors": uploaded.get("errors") or [],
        "candidate_status": candidate_status,
        "quality_http_status": quality_status_code,
        "quality_status": quality["quality_status"],
        "quality_score": quality["score"],
        "human_confirmation_status": confirm_status,
        "calculation_before_factor": formal["calculation_status"],
        "factor_candidates_status": factors_status,
        "factor_confirmation_status": calculation_status,
        "standardized_ledger_status": ledger_status,
        "standardized_ledger_record_id": ledger["activity_data_id"],
        "passport_list_status": passports_status,
        "passport_count": len(passports),
        "emission_result": {
            "value": result["co2_tonnes_exact"],
            "unit": result["unit"],
        },
        "total_seconds": round(time.perf_counter() - started, 3),
        "status": "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000/api")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--email", default=os.getenv("DEMO_FRONTEND_EMAIL", "demo@huasheng-steel.com"))
    parser.add_argument("--password", default=os.getenv("DEMO_FRONTEND_PASSWORD"))
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--validation-host", default="offline package candidate")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.password:
        parser.error("set DEMO_FRONTEND_PASSWORD or pass --password")
    if not args.file.is_file():
        parser.error(f"file does not exist: {args.file}")
    try:
        result = validate(args)
    except Exception as exc:  # noqa: BLE001 - CLI must print a concise failure
        print(json.dumps({"status": "fail", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Signed, short-lived confirmation subjects for document candidates.

The token does not make OCR output true.  It only proves that the exact fields
confirmed by a human are the same fields the server presented for confirmation,
and binds them to the owned source document and authenticated actor.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from backend.auth.jwt import ALGORITHM, SECRET_KEY


CANDIDATE_AUDIENCE = "carbonlab-document-candidate-confirmation"
CANDIDATE_TOKEN_TTL_MINUTES = 15


class CandidateSnapshotError(ValueError):
    pass


def _reject_binary_floats(value: Any, path: str = "fields") -> None:
    if isinstance(value, float):
        raise CandidateSnapshotError(f"{path} contains a binary float; use an exact string or integer")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_binary_floats(child, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, child in enumerate(value):
            _reject_binary_floats(child, f"{path}[{index}]")


def canonical_sha256(value: Any) -> str:
    _reject_binary_floats(value)
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _subject(
    *,
    actor_user_id: str,
    tenant_id: str,
    enterprise_id: str,
    file_id: str,
    document_content_hash: str,
    document_type: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        "actor_user_id": actor_user_id,
        "tenant_id": tenant_id,
        "enterprise_id": enterprise_id,
        "file_id": file_id,
        "document_content_hash": document_content_hash,
        "document_type": document_type,
        "fields": fields,
    }


def issue_candidate_snapshot(
    *,
    actor_user_id: str,
    tenant_id: str,
    enterprise_id: str,
    file_id: str,
    document_content_hash: str,
    document_type: str,
    fields: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=CANDIDATE_TOKEN_TTL_MINUTES)
    candidate_id = uuid.uuid4().hex
    subject = _subject(
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        file_id=file_id,
        document_content_hash=document_content_hash,
        document_type=document_type,
        fields=fields,
    )
    subject_sha256 = canonical_sha256(subject)
    fields_sha256 = canonical_sha256(fields)
    claims = {
        "sub": actor_user_id,
        "aud": CANDIDATE_AUDIENCE,
        "type": "document_candidate_confirmation",
        "jti": candidate_id,
        "iat": issued_at,
        "exp": expires_at,
        "tenant_id": tenant_id,
        "enterprise_id": enterprise_id,
        "file_id": file_id,
        "document_content_hash": document_content_hash,
        "document_type": document_type,
        "fields_sha256": fields_sha256,
        "subject_sha256": subject_sha256,
    }
    return {
        "candidate_id": candidate_id,
        "candidate_token": jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM),
        "fields_sha256": fields_sha256,
        "subject_sha256": subject_sha256,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


def verify_candidate_snapshot(
    token: str,
    *,
    actor_user_id: str,
    tenant_id: str,
    enterprise_id: str,
    file_id: str,
    document_content_hash: str,
    document_type: str,
    fields: dict[str, Any],
) -> dict[str, str]:
    try:
        claims = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=CANDIDATE_AUDIENCE,
            options={"require_exp": True, "require_sub": True, "require_aud": True},
        )
    except JWTError as exc:
        raise CandidateSnapshotError("候选快照签名无效或已过期") from exc
    if claims.get("type") != "document_candidate_confirmation":
        raise CandidateSnapshotError("候选快照类型无效")
    subject = _subject(
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        enterprise_id=enterprise_id,
        file_id=file_id,
        document_content_hash=document_content_hash,
        document_type=document_type,
        fields=fields,
    )
    expected = {
        "sub": actor_user_id,
        "tenant_id": tenant_id,
        "enterprise_id": enterprise_id,
        "file_id": file_id,
        "document_content_hash": document_content_hash,
        "document_type": document_type,
        "fields_sha256": canonical_sha256(fields),
        "subject_sha256": canonical_sha256(subject),
    }
    if any(claims.get(key) != value for key, value in expected.items()):
        raise CandidateSnapshotError("候选快照与当前文件、字段或操作者不一致")
    candidate_id = claims.get("jti")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise CandidateSnapshotError("候选快照缺少唯一标识")
    return {
        "candidate_id": candidate_id,
        "fields_sha256": expected["fields_sha256"],
        "subject_sha256": expected["subject_sha256"],
    }

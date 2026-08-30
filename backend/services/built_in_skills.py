"""Versioned built-in skills for the governed product workforce.

The files under ``backend/agent_skills`` are the auditable source of truth.
They are intentionally kept in the repository instead of editable database
rows so a run can record the exact version and package hash it used.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


SKILLS_ROOT = Path(__file__).resolve().parents[1] / "agent_skills"
REQUIRED_AI_ROLES = frozenset({"A-01", "A-02", "A-03", "A-04"})
SENSITIVE_SKILL_KEYS = frozenset({"api_key", "password", "secret", "token", "credential"})


class BuiltInSkillError(RuntimeError):
    """Raised when a checked-in skill package is incomplete or inconsistent."""


@dataclass(frozen=True)
class BuiltInSkill:
    skill_id: str
    role_id: str
    display_name: str
    version: str
    category: str
    execution_mode: str
    allowed_tools: tuple[str, ...]
    human_handoff: tuple[str, ...]
    stores_raw_chain_of_thought: bool
    package_sha256: str
    instruction_sha256: str
    skill_markdown: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    eval_cases: tuple[dict[str, Any], ...]
    package_path: str

    def to_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "skill_id": self.skill_id,
            "role_id": self.role_id,
            "display_name": self.display_name,
            "version": self.version,
            "category": self.category,
            "execution_mode": self.execution_mode,
            "allowed_tools": list(self.allowed_tools),
            "human_handoff": list(self.human_handoff),
            "stores_raw_chain_of_thought": self.stores_raw_chain_of_thought,
            "package_sha256": self.package_sha256,
            "instruction_sha256": self.instruction_sha256,
            "eval_case_count": len(self.eval_cases),
            "package_path": self.package_path,
        }
        if include_content:
            payload.update(
                {
                    "skill_markdown": self.skill_markdown,
                    "input_schema": self.input_schema,
                    "output_schema": self.output_schema,
                    "eval_cases": list(self.eval_cases),
                }
            )
        return payload


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuiltInSkillError(f"invalid built-in skill JSON: {path}") from exc


def _package_hash(package_dir: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in package_dir.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(package_dir).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def _validate_manifest(manifest: dict[str, Any], package_dir: Path) -> None:
    required = {
        "skill_id",
        "role_id",
        "display_name",
        "version",
        "category",
        "execution_mode",
        "input_schema",
        "output_schema",
        "allowed_tools",
        "human_handoff",
        "stores_raw_chain_of_thought",
    }
    missing = sorted(required - set(manifest))
    if missing:
        raise BuiltInSkillError(f"skill manifest missing {missing}: {package_dir}")
    if manifest["role_id"] not in REQUIRED_AI_ROLES:
        raise BuiltInSkillError(f"unsupported built-in AI role: {manifest['role_id']}")
    if manifest["stores_raw_chain_of_thought"] is not False:
        raise BuiltInSkillError("built-in skills must not retain raw chain of thought")
    if any(key in manifest for key in SENSITIVE_SKILL_KEYS):
        raise BuiltInSkillError("skill manifest must not embed credentials")
    for field in ("skill_id", "display_name", "version", "category", "execution_mode"):
        if not isinstance(manifest[field], str) or not manifest[field].strip():
            raise BuiltInSkillError(f"skill manifest field must be non-empty: {field}")
    for field in ("allowed_tools", "human_handoff"):
        if not isinstance(manifest[field], list) or not all(
            isinstance(value, str) and value.strip() for value in manifest[field]
        ):
            raise BuiltInSkillError(f"skill manifest field must be a string list: {field}")


def _load_package(package_dir: Path) -> BuiltInSkill:
    manifest_path = package_dir / "manifest.json"
    skill_path = package_dir / "SKILL.md"
    if not manifest_path.is_file() or not skill_path.is_file():
        raise BuiltInSkillError(f"built-in skill is missing SKILL.md or manifest: {package_dir}")
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise BuiltInSkillError(f"skill manifest must be an object: {manifest_path}")
    _validate_manifest(manifest, package_dir)

    input_path = package_dir / str(manifest["input_schema"])
    output_path = package_dir / str(manifest["output_schema"])
    eval_path = package_dir / "evals" / "cases.json"
    input_schema = _read_json(input_path)
    output_schema = _read_json(output_path)
    eval_cases = _read_json(eval_path)
    if not isinstance(input_schema, dict) or not isinstance(output_schema, dict):
        raise BuiltInSkillError(f"skill schemas must be JSON objects: {package_dir}")
    if not isinstance(eval_cases, list) or not eval_cases:
        raise BuiltInSkillError(f"skill must provide non-empty eval cases: {package_dir}")

    skill_markdown = skill_path.read_text(encoding="utf-8")
    if not skill_markdown.startswith("---\n") or "name:" not in skill_markdown[:500]:
        raise BuiltInSkillError(f"SKILL.md frontmatter is invalid: {skill_path}")
    instruction_sha256 = hashlib.sha256(skill_markdown.encode("utf-8")).hexdigest()
    return BuiltInSkill(
        skill_id=manifest["skill_id"],
        role_id=manifest["role_id"],
        display_name=manifest["display_name"],
        version=manifest["version"],
        category=manifest["category"],
        execution_mode=manifest["execution_mode"],
        allowed_tools=tuple(manifest["allowed_tools"]),
        human_handoff=tuple(manifest["human_handoff"]),
        stores_raw_chain_of_thought=False,
        package_sha256=_package_hash(package_dir),
        instruction_sha256=instruction_sha256,
        skill_markdown=skill_markdown,
        input_schema=input_schema,
        output_schema=output_schema,
        eval_cases=tuple(eval_cases),
        package_path=package_dir.relative_to(SKILLS_ROOT.parent).as_posix(),
    )


@lru_cache(maxsize=1)
def load_built_in_skills() -> tuple[BuiltInSkill, ...]:
    if not SKILLS_ROOT.is_dir():
        raise BuiltInSkillError(f"built-in skill root does not exist: {SKILLS_ROOT}")
    skills = tuple(
        _load_package(package_dir)
        for package_dir in sorted(SKILLS_ROOT.iterdir())
        if package_dir.is_dir()
    )
    role_ids = [skill.role_id for skill in skills]
    skill_ids = [skill.skill_id for skill in skills]
    if len(role_ids) != len(set(role_ids)) or len(skill_ids) != len(set(skill_ids)):
        raise BuiltInSkillError("built-in role and skill identifiers must be unique")
    if set(role_ids) != REQUIRED_AI_ROLES:
        missing = sorted(REQUIRED_AI_ROLES - set(role_ids))
        unexpected = sorted(set(role_ids) - REQUIRED_AI_ROLES)
        raise BuiltInSkillError(
            f"built-in skill coverage mismatch; missing={missing}, unexpected={unexpected}"
        )
    return skills


def get_skill_for_role(role_id: str) -> BuiltInSkill | None:
    return next((skill for skill in load_built_in_skills() if skill.role_id == role_id), None)


def get_skill(skill_id: str) -> BuiltInSkill | None:
    return next((skill for skill in load_built_in_skills() if skill.skill_id == skill_id), None)

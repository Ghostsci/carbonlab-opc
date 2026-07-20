"""Pinned qualification lock that prevents a self-rehashed test set from passing."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Iterable

from pydantic import Field

from backend.validation.contracts import StrictModel
from backend.validation.prompting import PromptPackage, prompt_set_sha256


ROOT = Path(__file__).resolve().parents[2]
EVALUATION_POLICY_PATHS = (
    ROOT / "backend" / "validation" / "contracts.py",
    ROOT / "backend" / "validation" / "evaluator.py",
    ROOT / "backend" / "validation" / "prompting.py",
    ROOT / "backend" / "validation" / "providers.py",
    ROOT / "backend" / "validation" / "qualification.py",
    ROOT / "backend" / "validation" / "reporting.py",
    ROOT / "backend" / "validation" / "synthetic_factory.py",
    ROOT / "scripts" / "compare_llm_conformance.py",
    ROOT / "scripts" / "run_llm_conformance.py",
    ROOT / "validation" / "RELEASE_GATES.json",
)
FROZEN_QUALIFICATION_PATHS = (
    *EVALUATION_POLICY_PATHS,
    ROOT / "validation" / "datasets" / "synthetic_factory_v1",
    ROOT / "validation" / "llm" / "LLM_OPERATING_CONTRACT.md",
    ROOT / "validation" / "llm" / "TASK_CATALOG.json",
)


class QualificationLock(StrictModel):
    version: str
    frozen_at: str
    frozen_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    frozen_git_tag: str
    dataset_version: str
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    splits: list[str]


def evaluation_policy_sha256() -> str:
    """Fingerprint the executable rules that turn model output into a verdict."""

    return _hash_evaluation_policy(lambda path: path.read_bytes())


def _hash_evaluation_policy(read_bytes) -> str:
    digest = hashlib.sha256()
    for path in EVALUATION_POLICY_PATHS:
        relative_path = path.relative_to(ROOT).as_posix().encode("utf-8")
        digest.update(len(relative_path).to_bytes(4, "big"))
        digest.update(relative_path)
        content = read_bytes(path)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _evaluation_policy_sha256_at_revision(revision: str) -> str:
    def read_revision(path: Path) -> bytes:
        relative_path = path.relative_to(ROOT).as_posix()
        result = subprocess.run(
            ["git", "show", f"{revision}:{relative_path}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            raise ValueError(
                "qualification frozen Git anchor is missing a policy file: "
                + relative_path
            )
        return result.stdout

    return _hash_evaluation_policy(read_revision)


def _verify_frozen_git_anchor(lock: QualificationLock) -> None:
    resolved = subprocess.run(
        ["git", "rev-list", "-n", "1", lock.frozen_git_tag],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if resolved.returncode != 0 or resolved.stdout.strip() != lock.frozen_git_commit:
        raise ValueError("qualification frozen Git tag does not match its commit")
    frozen_policy_hash = _evaluation_policy_sha256_at_revision(
        lock.frozen_git_commit
    )
    if frozen_policy_hash != lock.evaluation_policy_sha256:
        raise ValueError(
            "qualification frozen evaluator policy does not match its Git anchor"
        )
    relative_paths = [
        path.relative_to(ROOT).as_posix() for path in FROZEN_QUALIFICATION_PATHS
    ]
    diff = subprocess.run(
        ["git", "diff", "--quiet", lock.frozen_git_commit, "--", *relative_paths],
        cwd=ROOT,
        check=False,
    )
    if diff.returncode == 1:
        raise ValueError("qualification files drifted from the frozen Git anchor")
    if diff.returncode != 0:
        raise ValueError("qualification frozen Git comparison failed")
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *relative_paths,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise ValueError("qualification files are dirty or untracked")


def load_and_verify_qualification_lock(
    path: Path,
    *,
    manifest: dict,
    packages: Iterable[PromptPackage],
    splits: set[str],
) -> QualificationLock:
    if not path.is_file():
        raise ValueError(f"qualification lock is missing: {path}")
    lock = QualificationLock.model_validate_json(path.read_text(encoding="utf-8"))
    _verify_frozen_git_anchor(lock)
    selected = tuple(packages)
    if not selected:
        raise ValueError("qualification requires at least one prompt package")
    actual = {
        "dataset_version": manifest["dataset_version"],
        "dataset_sha256": manifest["dataset_sha256"],
        "contract_sha256": selected[0].contract_sha256,
        "task_sha256": selected[0].task_sha256,
        "schema_sha256": selected[0].schema_sha256,
        "prompt_set_sha256": prompt_set_sha256(selected),
        "evaluation_policy_sha256": evaluation_policy_sha256(),
        "splits": sorted(splits),
    }
    expected = {
        "dataset_version": lock.dataset_version,
        "dataset_sha256": lock.dataset_sha256,
        "contract_sha256": lock.contract_sha256,
        "task_sha256": lock.task_sha256,
        "schema_sha256": lock.schema_sha256,
        "prompt_set_sha256": lock.prompt_set_sha256,
        "evaluation_policy_sha256": lock.evaluation_policy_sha256,
        "splits": sorted(lock.splits),
    }
    mismatches = [name for name in expected if actual[name] != expected[name]]
    if mismatches:
        raise ValueError(
            "qualification lock mismatch: " + ", ".join(sorted(mismatches))
        )
    return lock

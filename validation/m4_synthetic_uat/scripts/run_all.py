#!/usr/bin/env python3
"""Execute and capture the M3 preflight and M4 three-replay evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--deps-dir", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args()
    script = args.artifact_root / "scripts" / "run_synthetic_uat.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(args.deps_dir), str(args.source_root)))
    commands = []

    def execute(name: str, command: list[str], cwd: Path) -> int:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log_path = args.artifact_root / "logs" / f"{name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(completed.stdout, encoding="utf-8")
        commands.append(
            {
                "name": name,
                "command": command,
                "cwd_boundary": "task_isolated_baseline_copy"
                if cwd == args.source_root
                else "task_artifact_root",
                "exit_code": completed.returncode,
                "log": str(log_path.relative_to(args.artifact_root)),
            }
        )
        return completed.returncode

    exit_codes = []
    for index in (1, 2, 3):
        exit_codes.append(
            execute(
                f"m3-pytest-replay-{index}",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "backend/tests/test_candidate_passport_v1.py",
                    "-q",
                ],
                args.source_root,
            )
        )
    for index in (1, 2, 3):
        exit_codes.append(
            execute(
                f"m4-uat-replay-{index}-stdout",
                [
                    sys.executable,
                    str(script),
                    "--output-dir",
                    str(args.artifact_root),
                    "--run-index",
                    str(index),
                ],
                args.artifact_root,
            )
        )
    exit_codes.append(
        execute(
            "m4-finalize",
            [
                sys.executable,
                str(script),
                "--output-dir",
                str(args.artifact_root),
                "--finalize",
            ],
            args.artifact_root,
        )
    )
    exit_codes.append(
        execute(
            "isolated-pip-check",
            [sys.executable, "-m", "pip", "check"],
            args.artifact_root,
        )
    )
    write_json(
        args.artifact_root / "environment" / "execution-ledger.json",
        {
            "executed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "source_boundary": "disposable baseline copy plus accepted M3 V1.0.3 patch",
            "dependency_boundary": "task-only target directory under /tmp",
            "artifact_boundary": "M4_SYNTHETIC_UAT_V1.0.0",
            "networked_model_calls": 0,
            "remote_writes": 0,
            "commands": commands,
        },
    )
    return 0 if all(code == 0 for code in exit_codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())

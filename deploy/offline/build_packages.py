#!/usr/bin/env python3
"""Assemble reproducible Mac arm64 and Windows x64 offline demo packages."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import tempfile
from zoneinfo import ZoneInfo
import zipfile


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = ROOT / "deploy" / "offline" / "templates"
COMPOSE_SOURCE = ROOT / "deploy" / "offline" / "compose.slim.yml"
SAMPLE_1000 = ROOT / "validation" / "competition_1000row" / "DEMO_ONLY_202601_HR_1000rows.xlsx"
SAMPLE_50_DIR = ROOT / "validation" / "competition_batch_v2" / "positive"
DEMO_EMAIL = "demo@huasheng-steel.com"
DEMO_PASSWORD = "Ea9buCDi_cFRQ-aSvk29UA"


def _run(*command: str) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _image_info(image: str) -> dict:
    payload = json.loads(_run("docker", "image", "inspect", image))[0]
    return {
        "name": image,
        "id": payload["Id"],
        "architecture": payload["Architecture"],
        "os": payload["Os"],
        "size_bytes": payload["Size"],
    }


def _save_images(images: list[str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        saver = subprocess.Popen(
            ["docker", "save", *images],
            cwd=ROOT,
            stdout=subprocess.PIPE,
        )
        assert saver.stdout is not None
        zipper = subprocess.Popen(["gzip", "-9", "-c"], stdin=saver.stdout, stdout=output)
        saver.stdout.close()
        gzip_status = zipper.wait()
        save_status = saver.wait()
    if save_status != 0 or gzip_status != 0:
        raise RuntimeError(
            f"failed to save images: docker={save_status}, gzip={gzip_status}"
        )


def _copy_tree_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.iterdir()):
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _write_env(path: Path, *, platform: str, image_tag: str) -> None:
    values = {
        "CARBONLAB_PLATFORM": platform,
        "CARBONLAB_IMAGE_TAG": image_tag,
        "FRONTEND_PORT": "15173",
        "BACKEND_PORT": "18000",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "POSTGRES_APP_USER": "carbonlab_app",
        "POSTGRES_APP_PASSWORD": secrets.token_urlsafe(32),
        "JWT_SECRET": secrets.token_urlsafe(64),
        "CARBONLAB_DEMO_PASSWORD": DEMO_PASSWORD,
        "DEMO_FRONTEND_EMAIL": DEMO_EMAIL,
        "DEMO_FRONTEND_PASSWORD": DEMO_PASSWORD,
    }
    text = "# DEMO ONLY. These credentials are local to the competition package.\n"
    text += "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_samples(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SAMPLE_1000, destination / SAMPLE_1000.name)
    workbook_zip = destination / "carbonlab-competition-50-row-workbooks-v2.zip"
    with zipfile.ZipFile(workbook_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for workbook in sorted(SAMPLE_50_DIR.glob("*.xlsx")):
            archive.write(workbook, workbook.name)


def _write_checksums(package_root: Path) -> None:
    lines = []
    for path in sorted(package_root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        relative = path.relative_to(package_root).as_posix()
        lines.append(f"{_sha256(path)}  {relative}")
    (package_root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _zip_directory(package_root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(package_root.rglob("*")):
            if path.is_file():
                archive.write(path, (Path(package_root.name) / path.relative_to(package_root)).as_posix())


def _read_report(path: Path | None) -> dict | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _build_one(
    *,
    output: Path,
    platform_key: str,
    platform: str,
    image_tag: str,
    package_name: str,
    code_commit: str,
    rollback_tag: str,
    screenshots: Path | None,
    validation_report: Path | None,
) -> dict:
    package_root = output / package_name
    archive_path = output / f"{package_name}.zip"
    if package_root.exists() or archive_path.exists():
        raise FileExistsError(f"refusing to overwrite existing package: {package_name}")
    package_root.mkdir(parents=True)

    if platform_key == "macos":
        _copy_tree_contents(TEMPLATE_ROOT / "macos", package_root)
    else:
        _copy_tree_contents(TEMPLATE_ROOT / "windows", package_root)
    shutil.copy2(TEMPLATE_ROOT / "README_现场演示.md", package_root / "README_现场演示.md")
    shutil.copy2(COMPOSE_SOURCE, package_root / "compose.offline.yml")
    _write_env(package_root / "config" / "demo.env", platform=platform, image_tag=image_tag)
    _write_samples(package_root / "sample-data")

    screenshot_count = 0
    if screenshots and screenshots.is_dir():
        target = package_root / "backup" / "screenshots"
        target.mkdir(parents=True, exist_ok=True)
        for source in sorted(screenshots.glob("*.png")):
            shutil.copy2(source, target / source.name)
            screenshot_count += 1

    validation = _read_report(validation_report)
    if validation_report:
        validation_target = package_root / "validation" / validation_report.name
        validation_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(validation_report, validation_target)

    images = [
        f"carbonlab-offline-backend:{image_tag}",
        f"carbonlab-offline-postgres-slim:{image_tag}",
    ]
    image_info = [_image_info(image) for image in images]
    expected_arch = "arm64" if platform == "linux/arm64" else "amd64"
    if any(item["architecture"] != expected_arch for item in image_info):
        raise RuntimeError(f"image architecture mismatch for {platform}: {image_info}")
    image_archive = package_root / "images" / "carbonlab-offline-images.tar.gz"
    _save_images(images, image_archive)

    account_text = (
        "零碳云比赛离线演示账号（仅限合成演示环境）\n\n"
        f"邮箱：{DEMO_EMAIL}\n"
        f"密码：{DEMO_PASSWORD}\n\n"
        "推荐：打开登录页后点击『一键进入演示』。\n"
        "本账号与包内数据均非真实客户或生产凭证。\n"
    )
    (package_root / "演示账号.txt").write_text(account_text, encoding="utf-8")

    built_at = datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(timespec="seconds")
    build_info = {
        "product": "CarbonLab / 零碳云",
        "edition": "competition-slim-offline-demo",
        "built_at": built_at,
        "git_commit": code_commit,
        "rollback_tag": rollback_tag,
        "platform": platform,
        "image_tag": image_tag,
        "images": image_info,
        "image_archive": {
            "path": "images/carbonlab-offline-images.tar.gz",
            "size_bytes": image_archive.stat().st_size,
            "sha256": _sha256(image_archive),
        },
        "runtime_topology": "compiled React SPA + FastAPI in one app container; PostgreSQL 16 slim database container",
        "external_llm_key_required_for_core_demo": False,
        "videos_included": False,
        "video_delivery": "separate file on the competition platform or presentation USB drive",
        "screenshots_included": screenshot_count,
        "validation": validation,
        "truth_boundary": (
            "Mac arm64 is natively exercised. Windows x64 images are exercised under Docker amd64 "
            "emulation on Mac; physical Windows double-click validation remains a host-specific check."
        ),
    }
    (package_root / "BUILD_INFO.json").write_text(
        json.dumps(build_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    optimization_note = (
        "# 轻量离线包说明\n\n"
        "本包未删减登录、文件上传、AI 候选提取、A-03 质检、H-01/H-02 人工确认、"
        "R-01 确定性核算、标准化数据台账、碳护照与数字员工治理等核心演示能力。\n\n"
        "体积优化来自运行架构收敛，而不是删除业务数据：\n\n"
        "1. React 前端在构建阶段编译，运行时不再携带 Node.js 与 node_modules；\n"
        "2. 后端只安装离线闭环实际使用的依赖；\n"
        "3. PostgreSQL 改为保留 vector/pgcrypto 的精简镜像；\n"
        "4. 视频独立交付，不重复塞入 Mac、Windows 两个包。\n"
    )
    (package_root / "轻量离线包说明.md").write_text(optimization_note, encoding="utf-8")

    for command in package_root.glob("*.command"):
        command.chmod(command.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _write_checksums(package_root)
    _zip_directory(package_root, archive_path)
    return {
        "platform": platform,
        "directory": str(package_root),
        "archive": str(archive_path),
        "archive_size_bytes": archive_path.stat().st_size,
        "archive_sha256": _sha256(archive_path),
        "image_archive_size_bytes": image_archive.stat().st_size,
        "image_count": len(images),
        "screenshots": screenshot_count,
        "videos": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--arm-validation", type=Path)
    parser.add_argument("--amd-validation", type=Path)
    parser.add_argument("--rollback-tag", default="zcy-pre-offline-package-slim-20260831")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    code_commit = _run("git", "rev-parse", "HEAD")
    products = [
        _build_one(
            output=args.output,
            platform_key="macos",
            platform="linux/arm64",
            image_tag="20260831-slim-arm64",
            package_name="CarbonLab_Demo_macOS_AppleSilicon_轻量离线版_20260831",
            code_commit=code_commit,
            rollback_tag=args.rollback_tag,
            screenshots=args.screenshots,
            validation_report=args.arm_validation,
        ),
        _build_one(
            output=args.output,
            platform_key="windows",
            platform="linux/amd64",
            image_tag="20260831-slim-amd64",
            package_name="CarbonLab_Demo_Windows_x64_轻量离线版_20260831",
            code_commit=code_commit,
            rollback_tag=args.rollback_tag,
            screenshots=args.screenshots,
            validation_report=args.amd_validation,
        ),
    ]
    result = {
        "built_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(timespec="seconds"),
        "git_commit": code_commit,
        "products": products,
    }
    manifest = args.output / "CarbonLab_轻量离线包_MANIFEST_20260831.json"
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

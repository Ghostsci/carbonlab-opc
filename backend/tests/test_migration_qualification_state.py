import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVE_LOCK = ROOT / "validation" / "QUALIFICATION_LOCK.json"
LEGACY_LOCK = ROOT / "validation" / "history" / "QUALIFICATION_LOCK_SOURCE_20260711.json"
REGISTRY = ROOT / "validation" / "MODEL_BASELINE_REGISTRY.json"


def test_clean_migration_has_no_active_model_qualification_lock() -> None:
    assert not ACTIVE_LOCK.exists()
    assert LEGACY_LOCK.is_file()


def test_registry_explicitly_disallows_shadow_and_production_use() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["status"] == "requalification_required_after_evaluator_hardening"
    assert registry["shadow_eligible"] is False
    assert registry["production_eligible"] is False


def test_historical_registry_artifacts_remain_hash_verifiable() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entries = [registry["default_shadow_model"], *registry["qualified_alternates"]]
    for entry in entries:
        assert entry["current_qualification_valid"] is False
        for path_key, hash_key in (
            ("qualification_report", "qualification_report_sha256"),
            ("repeatability_report", "repeatability_report_sha256"),
            ("repeatability_comparison", "repeatability_comparison_sha256"),
            ("comparison_report", "comparison_report_sha256"),
        ):
            if path_key not in entry:
                continue
            artifact = ROOT / entry[path_key]
            assert artifact.is_file(), artifact
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == entry[hash_key]

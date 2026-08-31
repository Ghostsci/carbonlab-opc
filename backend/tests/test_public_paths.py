from backend.auth.public_paths import is_public_path


def test_non_api_spa_paths_are_public() -> None:
    assert is_public_path("/")
    assert is_public_path("/login")
    assert is_public_path("/assets/index-demo.js")
    assert is_public_path("/passports")


def test_api_paths_remain_exactly_scoped() -> None:
    assert is_public_path("/api/health")
    assert is_public_path("/api/auth/login")
    assert not is_public_path("/api/auth/me")
    assert not is_public_path("/api/unknown")

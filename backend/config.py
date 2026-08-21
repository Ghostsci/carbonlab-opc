from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./carbonlab_opc.db"
    app_env: str = "development"
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    security_hsts_enabled: bool = False
    security_hsts_max_age: int = 31536000

    # JWT
    jwt_secret: str = ""
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    auth_cookie_secure: bool = False

    # WeChat
    wechat_appid: str = ""
    wechat_secret: str = ""

    # LLM / RAG
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"

    # MinIO / S3
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "carbon-footprint"
    minio_secure: bool = False
    storage_backend: str = "local"  # "local" or "minio"
    local_storage_dir: str = ""

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()


def get_cors_allowed_origins() -> list[str]:
    return [
        origin.strip().rstrip("/")
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ]

# Production safety: assert JWT secret is not the default
import secrets
if not settings.jwt_secret:
    if settings.app_env == "production":
        raise ValueError("JWT_SECRET must be set in production environment")
    settings.jwt_secret = secrets.token_urlsafe(64)

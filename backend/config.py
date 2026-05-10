from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    upload_dir: Path = Path("uploads")
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB per file

    supabase_url: str = ""
    supabase_service_role_key: str = ""


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)

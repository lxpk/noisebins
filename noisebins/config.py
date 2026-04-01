from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg_async://noisebins:noisebins@localhost:5432/noisebins"
    secret_key: str = "dev-secret-change-in-production"
    access_token_expire_minutes: int = 60 * 24 * 7
    users_jwt_secret: str = "dev-users-jwt-secret-min-32-characters-long!!"
    cors_origins: str = ""

    storage_backend: str = "local"
    local_storage_path: str = "./data/blobs"
    public_base_url: str = "http://127.0.0.1:8000"
    max_upload_bytes: int = 5 * 1024 * 1024

    vision_assist_enabled: bool = False
    noiseport_oauth_enabled: bool = False
    noiseport_client_id: str = ""
    noiseport_client_secret: str = ""
    noiseport_authorize_url: str = ""
    noiseport_token_url: str = ""
    noiseport_userinfo_url: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str
    owner_telegram_id: int
    database_url: str
    public_bot_url: str = ""
    webhook_secret: str = "change-me"
    web_service_port: int = 10000
    worker_poll_seconds: int = 3
    max_upload_mb: int = 20
    max_duration_seconds: int = 300
    temp_root: str = "/tmp/autotune"
    music_dir: str = "./music"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        value = str(value)
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value[len("postgres://"):]
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value[len("postgresql://"):]
        if value.startswith("postgresql+psycopg://"):
            return "postgresql+asyncpg://" + value[len("postgresql+psycopg://"):]
        return value

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

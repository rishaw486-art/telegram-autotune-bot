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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

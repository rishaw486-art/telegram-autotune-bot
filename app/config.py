from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
            value = "postgresql+asyncpg://" + value[len("postgres://"):]
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value[len("postgresql://"):]
        elif value.startswith("postgresql+psycopg://"):
            value = "postgresql+asyncpg://" + value[len("postgresql+psycopg://"):]
        parts = urlsplit(value)
        query = parse_qsl(parts.query, keep_blank_values=True)
        normalized = []
        sslmode = None
        for key, item in query:
            if key == "sslmode":
                sslmode = item
            elif key != "channel_binding":
                normalized.append((key, item))
        if sslmode and not any(key == "ssl" for key, _ in normalized):
            normalized.append(("ssl", "require" if sslmode in {"require", "verify-ca", "verify-full"} else sslmode))
        hostname = parts.hostname
        if hostname and parts.port is None:
            userinfo = ""
            if parts.username:
                userinfo = parts.username
                if parts.password:
                    userinfo += ":" + parts.password
                userinfo += "@"
            netloc = f"{userinfo}{hostname}:5432"
        else:
            netloc = parts.netloc
        return urlunsplit((parts.scheme, netloc, parts.path, urlencode(normalized), parts.fragment))

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

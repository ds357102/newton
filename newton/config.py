"""Settings, loaded from env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://newton:newton@db:5432/newton"
    redis_url: str = "redis://redis:6379/0"

    anthropic_api_key: str | None = None

    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "newton/0.1"

    x_bearer_token: str | None = None
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None

    owner_email: str | None = None


settings = Settings()

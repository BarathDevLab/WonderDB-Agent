from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_env_file = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Application and infrastructure settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_env_file) if _env_file.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="AI Database Assistant", alias="APP_NAME")
    env: str = Field(default="development", alias="ENV")
    port: int = Field(default=8000, alias="PORT")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="enterprise_db", alias="POSTGRES_DB")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    enable_semantic_cache: bool = Field(default=True, alias="ENABLE_SEMANTIC_CACHE")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-flash-latest", alias="GEMINI_MODEL")
    gemini_embedding_model: str = Field(default="text-embedding-004", alias="GEMINI_EMBEDDING_MODEL")
    app_api_key: str = Field(default="", alias="APP_API_KEY")
    max_prompt_length: int = Field(default=2000, alias="MAX_PROMPT_LENGTH")

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings to avoid re-reading environment variables."""

    return Settings()

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)
    database_url: str = "postgresql+psycopg://operations:operations@localhost:55432/operations"
    redis_url: str = "redis://localhost:56379/0"
    environment: str = "development"
    allowed_origins: str = "http://localhost:5173,http://localhost:8080"
    ai_provider: str = "demo"
    openai_api_key: str = ""
    chat_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    upload_dir: str = "uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    session_hours: int = 12
    model_input_cost_per_million: float | None = None
    model_output_cost_per_million: float | None = None
    demo_email: str = "owner@example.com"
    demo_password: str = ""
    langsmith_tracing: bool = False

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def postgres_dsn(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")

    @model_validator(mode="after")
    def validate_provider(self):
        if self.ai_provider not in {"demo", "openai"}:
            raise ValueError("AI_PROVIDER must be demo or openai")
        if self.ai_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider")
        if self.embedding_dimensions != 1536:
            raise ValueError("This migration uses 1536-dimensional vectors")
        if self.environment == "production" and any(x.startswith("http:") for x in self.origins):
            raise ValueError("Production origins must use HTTPS")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()

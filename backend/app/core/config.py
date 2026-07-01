from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Qdrant
    QDRANT_URL: str
    QDRANT_API_KEY: str

    # Ollama — only required when llm_provider or embedding_provider is "local"
    OLLAMA_BASE_URL: str = ""

    # JWT — no default for SECRET_KEY; must be supplied via env
    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    @field_validator("SECRET_KEY")
    @classmethod
    def _validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. "
                "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS — stored as comma-separated string in env; split at use-time to avoid
    # pydantic-settings attempting JSON-parse on a plain string value.
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Reranker
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RERANKER_TOP_K: int = Field(5, ge=1, le=100)
    RERANKER_SCORE_THRESHOLD: float = Field(0.5, ge=0.0, le=1.0)

    # HyDE + Multi-query expansion (PLANEJAMENTO.md §4.2)
    HYDE_TEMPERATURE: float = Field(0.3, ge=0.0, le=1.0)
    MULTIQUERY_TEMPERATURE: float = Field(0.3, ge=0.0, le=1.0)
    MULTIQUERY_COUNT: int = Field(2, ge=1, le=5)

    # Contextual Compression (PLANEJAMENTO.md §5.3)
    CONTEXTUAL_COMPRESSION_ENABLED: bool = True
    CONTEXTUAL_COMPRESSION_TEMPERATURE: float = Field(0.1, ge=0.0, le=1.0)

    # Proprietary LLM API keys (optional — only required when llm_provider != 'local')
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def allowed_origins_list(self) -> list[str]:
        """Return ALLOWED_ORIGINS as a list split on commas."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

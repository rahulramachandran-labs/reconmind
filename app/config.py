from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"

    corpus_dir: Path = ROOT / "corpus"
    index_dir: Path = ROOT / ".index"
    embeddings_backend: Literal["sentence-transformers", "hashing"] = "sentence-transformers"
    embeddings_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    retrieval_k: int = 5

    llm_provider: Literal["openai", "ollama", "none"] = "ollama"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:1.5b"
    llm_timeout_s: float = 60.0

    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "https://reconmind-labs.vercel.app"]
    )
    max_question_chars: int = 1000


@lru_cache
def get_settings() -> Settings:
    return Settings()

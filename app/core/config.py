from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"

    corpus_dir: Path = ROOT / "corpus"
    index_dir: Path = ROOT / ".index"
    dbt_models_dir: Path = ROOT / "dbt" / "models"
    embeddings_backend: Literal["sentence-transformers", "fastembed", "openai", "hashing"] = (
        "sentence-transformers"
    )
    embeddings_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    openai_embeddings_model: str = "text-embedding-3-small"
    retriever: Literal["hybrid", "dense", "bm25"] = "hybrid"
    reranker: Literal["cross-encoder", "none"] = "cross-encoder"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_candidates: int = 10
    vector_store: Literal["faiss", "pinecone"] = "faiss"
    pinecone_api_key: SecretStr | None = None
    pinecone_index: str = "reconmind"

    # tried in order; DEMO_MODE drops the paid ones so a demo never costs anything
    llm_providers: list[str] = Field(
        default=["openai", "anthropic", "groq", "gemini", "openrouter", "ollama"]
    )
    demo_mode: bool = False
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5-mini"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-4-5"
    # free tiers, all spoken to through the OpenAI-compatible chat API
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_free_tier: bool = True
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_free_tier: bool = True
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str = "deepseek/deepseek-v4-flash-0731:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:1.5b"
    llm_timeout_s: float = 60.0
    llm_cooldown_s: float = 60.0
    llm_concurrency: int = 2  # model calls at once; free tiers limit tokens per minute

    database_url: str | None = None

    # agents
    agents_enabled: bool = True
    domain_adapter: str = "retail_recon"
    # stdio: servers as subprocesses; inprocess: same process, for one small container
    mcp_transport: Literal["stdio", "inprocess"] = "stdio"
    warehouse_mcp_url: str | None = None
    orchestration_mcp_url: str | None = None
    planner_confidence_threshold: float = 0.5
    review_confidence_threshold: float = 0.6
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str | None = None

    # operations
    scan_interval_minutes: int = 0  # 0 turns the scheduler off
    write_token: SecretStr | None = None  # when set, scans and reviews need it as a bearer token
    rate_limit_chat: str = "20/minute"
    rate_limit_scan: str = "4/minute"
    rate_limit_ask: str = "30/minute"
    rate_limits_enabled: bool = True

    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "https://reconmind-labs.vercel.app"]
    )
    max_question_chars: int = 1000
    public_url: str = "https://reconmind-labs.vercel.app"
    history_turns: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item.strip() for item in value if item and item.strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    app_name: str = "Fact Cookie"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = Field(default_factory=list)
    enable_dev_endpoints: bool = True

    # --- Security ---
    secret_key: str = "dev-only-change-me-please-32-bytes-minimum"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    password_min_length: int = 8
    api_key_prefix: str = "fc_live_"
    max_request_body_bytes: int = 20 * 1024 * 1024

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./factcookie.db"
    db_echo: bool = False

    # --- Rate limits (requests per window seconds) ---
    rate_limit_login: int = 5
    rate_limit_login_window: int = 60
    rate_limit_register: int = 10
    rate_limit_register_window: int = 3600
    rate_limit_verification: int = 30
    rate_limit_verification_window: int = 60

    # --- LLM ---
    llm_mode: Literal["mock", "live"] = "mock"
    orchestration_mode: Literal["pipeline", "agents"] = "pipeline"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = ""
    openrouter_x_title: str = "Fact Cookie"
    model_fast: str = "qwen/qwen3-next-80b-a3b-instruct:free"
    model_strong: str = "qwen/qwen3-235b-a22b-04-28:free"
    model_fallbacks: list[str] = Field(
        default_factory=lambda: [
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "qwen/qwen3-32b",
        ]
    )
    llm_timeout_seconds: float = 90.0
    llm_max_retries: int = 2
    llm_repair_attempts: int = 1
    llm_max_concurrency: int = 4
    llm_temperature: float = 0.0
    llm_trace_dir: str = "logs"

    # --- Verification caps ---
    max_input_chars: int = 20000
    sync_max_chars: int = 2000
    max_claims_per_verification: int = 8
    max_claims_async: int = 12
    max_searches_per_claim: int = 2
    max_fetches_per_claim: int = 2
    max_evidence_chars: int = 8000
    max_page_chars: int = 20000
    snippet_max_chars: int = 500

    # --- Budgets (free-tier protection) ---
    user_daily_verification_budget: int = 100
    user_daily_search_budget: int = 200
    global_daily_verification_budget: int = 2000
    global_daily_search_budget: int = 1500

    # --- Tavily ---
    tavily_api_key: str = ""
    tavily_search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = "basic"
    tavily_advanced_search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] = "advanced"
    tavily_max_results: int = 5
    tavily_extract_depth: Literal["basic", "advanced"] = "basic"
    tavily_timeout_seconds: float = 30.0
    cache_ttl_search_seconds: int = 3600
    cache_ttl_page_seconds: int = 86400

    # --- HTTP fetcher ---
    http_fetch_timeout_seconds: float = 15.0
    http_fetch_max_bytes: int = 3 * 1024 * 1024
    http_fetch_max_redirects: int = 3
    http_fetch_user_agent: str = "FactCookieBot/1.0 (+https://factcookie.example/bot)"

    # --- Documents ---
    upload_dir: str = "data/uploads"
    document_max_bytes: int = 10 * 1024 * 1024
    document_allowed_extensions: list[str] = Field(
        default_factory=lambda: [".pdf", ".txt", ".md", ".markdown"]
    )
    document_chunk_chars: int = 1000
    document_chunk_overlap: int = 150

    # --- Billing ---
    billing_provider: Literal["mock", "stripe"] = "mock"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_free: str = ""
    stripe_price_pro: str = ""
    stripe_price_team: str = ""
    stripe_price_enterprise: str = ""
    stripe_api_base: str = "https://api.stripe.com"
    billing_success_url: str = "http://localhost:3000/billing/success"
    billing_cancel_url: str = "http://localhost:3000/billing/cancel"
    billing_portal_return_url: str = "http://localhost:3000/billing"

    # --- OAuth for MCP connector ---
    oauth_access_token_ttl_seconds: int = 3600
    oauth_refresh_token_ttl_seconds: int = 30 * 24 * 3600
    oauth_auth_code_ttl_seconds: int = 300
    oauth_scopes: list[str] = Field(default_factory=lambda: ["factcookie:verify"])
    oauth_allow_dynamic_registration: bool = True

    # --- Jobs ---
    job_worker_concurrency: int = 2
    job_poll_interval_seconds: float = 1.0

    @field_validator("cors_origins", "model_fallbacks", "document_allowed_extensions", "oauth_scopes", mode="before")
    @classmethod
    def _parse_list(cls, value: object) -> list[str]:
        return _split_csv(value)  # type: ignore[arg-type]

    @property
    def effective_cors_origins(self) -> list[str]:
        origins = list(self.cors_origins)
        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)
        if self.debug:
            for origin in ("http://localhost:3000", "http://localhost:8000"):
                if origin not in origins:
                    origins.append(origin)
        return origins

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def live_llm_enabled(self) -> bool:
        return self.llm_mode == "live" and bool(self.openrouter_api_key)

    @property
    def tavily_enabled(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def stripe_enabled(self) -> bool:
        return self.billing_provider == "stripe" and bool(
            self.stripe_secret_key and self.stripe_webhook_secret
        )

    @property
    def oauth_issuer(self) -> str:
        return self.base_url.rstrip("/")

    def ensure_directories(self) -> None:
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.llm_trace_dir, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings


settings = get_settings()

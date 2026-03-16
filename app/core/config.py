from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "InvestAI Signal Alert Service"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"
    timezone: str = "Asia/Seoul"
    default_market: str = "KR"
    default_lookback_days: int = 365
    downloads_dir: str = Field(default="downloads", alias="DOWNLOADS_DIR")

    database_url: str = Field(
        default="postgresql+psycopg://investai:investai@localhost:5432/investai",
        alias="DATABASE_URL",
    )

    google_application_credentials: str = Field(
        default="pjt-dev-hdegis-app-454401-b7c65a0d9543.json",
        alias="GOOGLE_APPLICATION_CREDENTIALS",
    )
    gemini_project_id: str = Field(default="pjt-dev-hdegis-app-454401", alias="GEMINI_PROJECT_ID")
    gemini_location: str = Field(default="us-central1", alias="GEMINI_LOCATION")
    gemini_model: str = Field(default="gemini-2.5-pro", alias="GEMINI_MODEL")
    gemini_enabled: bool = Field(default=True, alias="GEMINI_ENABLED")
    llm_task_timeout_seconds: int = Field(default=90, alias="LLM_TASK_TIMEOUT_SECONDS")
    llm_task_concurrency: int = Field(default=2, alias="LLM_TASK_CONCURRENCY")
    product_cache_ttl_seconds: int = Field(default=300, alias="PRODUCT_CACHE_TTL_SECONDS")
    connector_cache_ttl_seconds: int = Field(default=180, alias="CONNECTOR_CACHE_TTL_SECONDS")
    kis_token_ttl_seconds: int = Field(default=3300, alias="KIS_TOKEN_TTL_SECONDS")

    telegram_enabled: bool = Field(default=False, alias="TELEGRAM_ENABLED")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    alert_cooldown_minutes: int = Field(default=45, alias="ALERT_COOLDOWN_MINUTES")

    kis_app_key: str = Field(default="", alias="KIS_APP_KEY")
    kis_app_secret: str = Field(default="", alias="KIS_APP_SECRET")
    kis_base_url: str = Field(default="", alias="KIS_BASE_URL")
    kis_mock_base_url: str = Field(default="https://openapivts.koreainvestment.com:29443", alias="KIS_MOCK_BASE_URL")
    kis_prod_base_url: str = Field(default="https://openapi.koreainvestment.com:9443", alias="KIS_PROD_BASE_URL")

    dart_api_key: str = Field(default="", alias="DART_API_KEY")
    naver_client_id: str = Field(default="", alias="NAVER_CLIENT_ID")
    naver_client_secret: str = Field(default="", alias="NAVER_CLIENT_SECRET")
    bok_api_key: str = Field(default="", alias="BOK_API_KEY")
    kosis_api_key: str = Field(default="", alias="KOSIS_API_KEY")
    news_api_key: str = Field(default="", alias="NEWS_API_KEY")
    oecd_id: str = Field(default="", alias="OECD_ID")
    oecd_pw: str = Field(default="", alias="OECD_PW")
    fred_api_key: str = Field(default="", alias="FRED_API_KEY")
    bls_api_key: str = Field(default="", alias="BLS_API_KEY")
    bea_api_key: str = Field(default="", alias="BEA_API_KEY")
    world_bank_api_key: str = Field(default="", alias="WORLD_BANK_API_KEY")
    imf_api_key: str = Field(default="", alias="IMF_API_KEY")
    eurostat_api_key: str = Field(default="", alias="EUROSTAT_API_KEY")
    x_bearer_token: str = Field(default="", alias="X_BEARER_TOKEN")

    def credentials_path(self) -> Path:
        """Return the ADC credential file path."""
        return Path(self.google_application_credentials).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()

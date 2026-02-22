from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "InvestAI Signal Alert Service"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"
    timezone: str = "Asia/Seoul"
    default_market: str = "KR"
    default_lookback_days: int = 365

    database_url: str = Field(
        default="postgresql+psycopg://investai:investai@localhost:5432/investai",
        alias="DATABASE_URL",
    )

    # Gemini ADC
    google_application_credentials: str = Field(
        default="pjt-dev-hdegis-app-454401-b7c65a0d9543.json",
        alias="GOOGLE_APPLICATION_CREDENTIALS",
    )
    gemini_project_id: str = Field(default="pjt-dev-hdegis-app-454401", alias="GEMINI_PROJECT_ID")
    gemini_location: str = Field(default="us-central1", alias="GEMINI_LOCATION")
    gemini_model: str = Field(default="gemini-2.5-pro", alias="GEMINI_MODEL")
    gemini_enabled: bool = Field(default=True, alias="GEMINI_ENABLED")

    # Alerts
    telegram_enabled: bool = Field(default=False, alias="TELEGRAM_ENABLED")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    alert_cooldown_minutes: int = Field(default=45, alias="ALERT_COOLDOWN_MINUTES")

    # External providers (MVP)
    kis_app_key: str = Field(default="", alias="KIS_APP_KEY")
    kis_app_secret: str = Field(default="", alias="KIS_APP_SECRET")
    dart_api_key: str = Field(default="", alias="DART_API_KEY")
    naver_client_id: str = Field(default="", alias="NAVER_CLIENT_ID")
    naver_client_secret: str = Field(default="", alias="NAVER_CLIENT_SECRET")
    x_bearer_token: str = Field(default="", alias="X_BEARER_TOKEN")

    def credentials_path(self) -> Path:
        return Path(self.google_application_credentials).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()

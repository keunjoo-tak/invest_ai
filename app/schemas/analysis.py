from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import MarketFeatureSet, SignalResult


class AnalyzeTickerRequest(BaseModel):
    ticker_or_name: str = Field(min_length=1, max_length=100)
    as_of_date: date | None = None
    lookback_days: int = Field(default=365, ge=60, le=730)
    analysis_mode: str = Field(default="full", pattern="^(quick|full)$")
    notify: bool = True
    channels: list[str] = Field(default_factory=lambda: ["telegram"])


class AlertPayload(BaseModel):
    should_send: bool
    dedup_blocked: bool = False
    channel_results: dict[str, Any] = Field(default_factory=dict)
    message: str


class AnalyzeTickerResponse(BaseModel):
    request_id: str
    ticker: str
    instrument_name: str
    as_of_date: date
    generated_at_utc: datetime
    features: MarketFeatureSet
    signal: SignalResult
    explanation: dict[str, Any]
    alert: AlertPayload

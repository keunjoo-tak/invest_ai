from datetime import date, datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    env: str
    time_utc: datetime


class SignalReason(BaseModel):
    code: str
    description: str
    score_contribution: float = 0.0


class MarketFeatureSet(BaseModel):
    as_of_date: date
    close: float
    ma_20: float
    ma_60: float
    rsi_14: float
    volatility_20d: float
    rel_volume: float
    news_sentiment_7d: float
    disclosure_impact_30d: float
    macro_pressure_score: float


class SignalResult(BaseModel):
    signal_type: str
    direction: str
    score: float
    quality_score: float
    reasons: list[SignalReason] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)

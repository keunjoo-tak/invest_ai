from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import MarketFeatureSet, SignalResult


class StockInsightResponse(BaseModel):
    """레거시 Stock Insight 응답 모델."""

    ticker: str
    instrument_name: str
    as_of_date: date
    generated_at_utc: datetime
    one_line_diagnosis: str
    state_label: str
    valuation_summary: str
    event_summary: list[str] = Field(default_factory=list)
    earnings_summary: str
    flow_summary: str
    technical_summary: str
    sector_relative_strength: float
    risk_factors: list[str] = Field(default_factory=list)
    checkpoints: list[str] = Field(default_factory=list)
    features: MarketFeatureSet
    signal: SignalResult
    explanation: dict[str, Any] = Field(default_factory=dict)


class TradeCompassRequest(BaseModel):
    """레거시 Trade Compass 요청 모델."""

    ticker_or_name: str = Field(min_length=1, max_length=100, description='분석 대상 종목명 또는 티커')
    as_of_date: date | None = Field(default=None, description='분석 기준일')
    investment_horizon: str = Field(default='swing', description='투자 기간(swing/midterm)')
    risk_profile: str = Field(default='balanced', description='위험 성향(conservative/balanced/aggressive)')
    objective: str = Field(default='new_entry', description='투자 목적(new_entry/add/buy_hold/partial_take/full_exit)')
    has_position: bool = Field(default=False, description='현재 보유 여부')
    avg_buy_price: float | None = Field(default=None, ge=0, description='평균단가(보유 시)')
    response_language: str = Field(default='ko', pattern='^(ko|en)$', description='응답 언어')


class TradeScenario(BaseModel):
    """레거시 시나리오 모델."""

    scenario: str
    trigger: str
    action: str
    rationale: str


class TradeCompassResponse(BaseModel):
    """레거시 Trade Compass 응답 모델."""

    ticker: str
    instrument_name: str
    as_of_date: date
    generated_at_utc: datetime
    recommended_action: str
    confidence_band: str
    buy_interest_zone: str
    invalidation_zone: str
    target_zone_primary: str
    target_zone_secondary: str
    scenarios: list[TradeScenario] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    source_insight: StockInsightResponse


class MarketPulseOverviewResponse(BaseModel):
    """레거시 Market Pulse overview 응답 모델."""

    as_of_date: date
    generated_at_utc: datetime
    market_one_line: str
    regime: str
    regime_score: float
    strong_sectors: list[dict[str, Any]] = Field(default_factory=list)
    weak_sectors: list[dict[str, Any]] = Field(default_factory=list)
    macro_summary: list[dict[str, Any]] = Field(default_factory=list)
    strategy_hints: list[str] = Field(default_factory=list)
    representative_symbols: list[dict[str, Any]] = Field(default_factory=list)
    headline_news_briefs: list[dict[str, Any]] = Field(default_factory=list)
    research_briefs: list[dict[str, Any]] = Field(default_factory=list)

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.analysis import AnalyzeTickerResponse
from app.schemas.common import SignalResult


class MarketRegimeResponse(BaseModel):
    as_of_date: date
    generated_at_utc: datetime
    regime: str
    regime_score: float
    market_one_line: str
    global_macro_pressure: list[dict[str, Any]] = Field(default_factory=list)
    strong_sectors: list[dict[str, Any]] = Field(default_factory=list)
    weak_sectors: list[dict[str, Any]] = Field(default_factory=list)
    strategy_hints: list[str] = Field(default_factory=list)
    representative_symbols: list[dict[str, Any]] = Field(default_factory=list)
    headline_news_briefs: list[dict[str, Any]] = Field(default_factory=list)
    research_briefs: list[dict[str, Any]] = Field(default_factory=list)
    pipeline_status: dict[str, Any] = Field(default_factory=dict)


class StockDecisionResponse(BaseModel):
    ticker: str
    instrument_name: str
    as_of_date: date
    generated_at_utc: datetime
    market_regime: str
    conclusion: str
    state_label: str
    confidence_score: float
    quality_score: float
    short_term_score: float
    swing_score: float
    midterm_score: float
    market_score: float
    sector_score: float
    stock_specific_score: float
    event_score: float
    valuation_score: float
    bullish_factors: list[str] = Field(default_factory=list)
    bearish_factors: list[str] = Field(default_factory=list)
    change_triggers: list[str] = Field(default_factory=list)
    recent_timeline: list[dict[str, Any]] = Field(default_factory=list)
    sector_name: str | None = None
    sector_leader_ticker: str | None = None
    sector_leader_name: str | None = None
    sector_coupling_score: float = 0.5
    sector_fund_flow_score: float = 0.0
    sector_breadth_score: float = 0.5
    sector_relative_strength: float = 0.0
    sector_momentum_summary: list[str] = Field(default_factory=list)
    sector_peer_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    financial_summary: list[str] = Field(default_factory=list)
    policy_macro_summary: list[str] = Field(default_factory=list)
    research_consensus: dict[str, Any] = Field(default_factory=dict)
    research_summary: list[str] = Field(default_factory=list)
    research_evidence_docs: list[dict[str, Any]] = Field(default_factory=list)
    source_analysis: AnalyzeTickerResponse
    pipeline_status: dict[str, Any] = Field(default_factory=dict)


class ActionPlannerRequest(BaseModel):
    ticker_or_name: str = Field(min_length=1, max_length=100)
    as_of_date: date | None = None
    lookback_days: int = Field(default=365, ge=60, le=730)
    investment_horizon: str = Field(default='swing', pattern='^(short_term|swing|midterm)$')
    risk_profile: str = Field(default='balanced', pattern='^(conservative|balanced|aggressive)$')
    objective: str = Field(default='new_entry')
    has_position: bool = False
    avg_buy_price: float | None = Field(default=None, ge=0)


class ActionScenario(BaseModel):
    scenario: str
    trigger: str
    expected_path: str
    action: str


class ActionPlannerResponse(BaseModel):
    ticker: str
    instrument_name: str
    as_of_date: date
    generated_at_utc: datetime
    recommended_action: str
    action_reason: str
    investment_horizon: str
    risk_profile: str
    objective: str
    has_position: bool
    avg_buy_price: float | None = None
    action_score: float
    plan_validity_window: str
    preconditions: list[str] = Field(default_factory=list)
    buy_interest_zone: str
    invalidation_zone: str
    target_zone: str
    holding_plan: str
    no_position_plan: str
    scenarios: list[ActionScenario] = Field(default_factory=list)
    source_decision: StockDecisionResponse
    pipeline_status: dict[str, Any] = Field(default_factory=dict)


class WatchlistAlertRequest(BaseModel):
    ticker_or_name: str = Field(min_length=1, max_length=100)
    as_of_date: date | None = None
    lookback_days: int = Field(default=365, ge=60, le=730)
    notify: bool = False
    force_send: bool = False


class WatchlistAlertResponse(BaseModel):
    ticker: str
    instrument_name: str
    as_of_date: date
    generated_at_utc: datetime
    should_alert_now: bool
    monitoring_state: str
    key_triggers: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    catalyst_watchlist: list[str] = Field(default_factory=list)
    alert_preview: str
    source_signal: SignalResult
    source_analysis: AnalyzeTickerResponse
    pipeline_status: dict[str, Any] = Field(default_factory=dict)


class WatchlistSubscriptionRequest(BaseModel):
    ticker_or_name: str = Field(min_length=1, max_length=100)
    channel: str = Field(default='telegram', pattern='^(telegram)$')
    notes: str | None = Field(default=None, max_length=500)


class WatchlistSubscriptionResponse(BaseModel):
    id: int
    ticker: str
    instrument_name: str
    channel: str
    is_active: bool
    notes: str | None = None
    created_at_utc: datetime
    updated_at_utc: datetime


class WatchlistSubscriptionDeleteResponse(BaseModel):
    deleted: bool
    ticker: str
    channel: str

from datetime import date, datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str = 'ok'
    app: str
    env: str
    time_utc: datetime


class SignalReason(BaseModel):
    """Single reason item that contributes to the signal score."""

    code: str = Field(description='Reason code')
    description: str = Field(description='User-facing reason description')
    score_contribution: float = Field(default=0.0, description='Score contribution')


class MarketFeatureSet(BaseModel):
    """Normalized feature set used by the analysis pipeline."""

    as_of_date: date = Field(description='Analysis date')
    close: float = Field(description='Close price')
    ma_20: float = Field(description='20-day moving average')
    ma_60: float = Field(description='60-day moving average')
    rsi_14: float = Field(description='14-day RSI')
    volatility_20d: float = Field(description='20-day volatility')
    atr_14_pct: float = Field(description='14-day ATR ratio')
    return_1d: float = Field(description='1-day return')
    return_5d: float = Field(description='5-day return')
    return_20d: float = Field(description='20-day return')
    gap_return_1d: float = Field(description='Gap return')
    price_vs_ma20: float = Field(description='Distance from 20-day moving average')
    price_vs_ma60: float = Field(description='Distance from 60-day moving average')
    rel_volume: float = Field(description='Relative volume')
    turnover_value_zscore: float = Field(description='Turnover z-score')
    intraday_range_pct: float = Field(description='Intraday range ratio')
    news_sentiment_7d: float = Field(description='7-day news sentiment')
    news_attention_score: float = Field(description='News attention score')
    text_keyword_density: float = Field(description='Event keyword density')
    disclosure_impact_30d: float = Field(description='30-day disclosure impact score')
    disclosure_bullish_score: float = Field(default=0.0, description='Disclosure bullish score')
    disclosure_bearish_score: float = Field(default=0.0, description='Disclosure bearish score')
    disclosure_net_score: float = Field(default=0.0, description='Disclosure net score')
    material_disclosure_severity: float = Field(default=0.0, description='Material disclosure severity')
    overnight_us_beta: float = Field(default=0.0, description='US overnight transmission beta')
    overnight_us_correlation: float = Field(default=0.0, description='US overnight transmission correlation')
    overnight_us_index_return: float = Field(default=0.0, description='US index return used for premarket transmission')
    overnight_us_signal: float = Field(default=0.0, description='Premarket spillover signal from US index to KR stock')
    overnight_us_vol_spillover: float = Field(default=0.0, description='Premarket volatility spillover intensity')
    event_volatility_score: float = Field(default=0.0, description='Event-day volatility caution score')
    event_pattern_bias: float = Field(default=0.0, description='Historical event pattern bias')
    event_pattern_confidence: float = Field(default=0.0, description='Historical event pattern confidence')
    supply_contract_score: float = Field(description='Supply contract score')
    financing_risk_score: float = Field(description='Financing risk score')
    shareholder_return_score: float = Field(description='Shareholder return score')
    governance_score: float = Field(description='Governance score')
    earnings_event_ratio: float = Field(description='Earnings event ratio')
    contract_event_ratio: float = Field(description='Contract event ratio')
    macro_pressure_score: float = Field(description='Macro pressure score')
    macro_support_score: float = Field(description='Macro support score')
    macro_global_score: float = Field(description='Global macro score')
    macro_surprise_index: float = Field(default=0.0, description='Macro surprise index')
    macro_surprise_abs_mean: float = Field(default=0.0, description='Mean absolute macro surprise')
    macro_consensus_coverage: float = Field(default=0.0, description='Macro consensus coverage')
    sector_coupling_score: float = Field(default=0.5, description='Sector leader coupling score')
    sector_fund_flow_score: float = Field(default=0.0, description='Sector fund flow score')
    sector_breadth_score: float = Field(default=0.5, description='Sector breadth score')
    sector_leader_relative_strength: float = Field(default=0.0, description='Relative strength versus sector leader')
    revenue_growth_yoy: float = Field(description='Revenue growth yoy')
    operating_margin: float = Field(description='Operating margin')
    net_margin: float = Field(description='Net margin')
    debt_ratio: float = Field(description='Debt ratio')
    current_ratio: float = Field(description='Current ratio')
    operating_cashflow_margin: float = Field(description='Operating cashflow margin')


class SignalResult(BaseModel):
    """Final signal result returned by the scoring pipeline."""

    signal_type: str = Field(description='User-facing signal type')
    direction: str = Field(description='User-facing direction label')
    score: float = Field(description='Signal score')
    quality_score: float = Field(description='Signal quality score')
    reasons: list[SignalReason] = Field(default_factory=list, description='Positive or negative reasons')
    risk_flags: list[str] = Field(default_factory=list, description='User-facing risk flags')
    signal_type_code: str | None = Field(default=None, description='Internal signal type code')
    direction_code: str | None = Field(default=None, description='Internal direction code')
    risk_flag_codes: list[str] = Field(default_factory=list, description='Internal risk flag codes')

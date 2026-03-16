from __future__ import annotations

from app.schemas.common import MarketFeatureSet, SignalReason, SignalResult


def evaluate_signal(features: MarketFeatureSet) -> SignalResult:
    """Calculate the final signal and quality score from the feature set."""
    score = 50.0
    reasons: list[SignalReason] = []
    risk_flags: list[str] = []

    if features.price_vs_ma20 > 0:
        score += 8
        reasons.append(SignalReason(code="PRICE_ABOVE_MA20", description="Price is above the 20-day moving average.", score_contribution=8))
    else:
        score -= 6
        reasons.append(SignalReason(code="PRICE_BELOW_MA20", description="Price is below the 20-day moving average.", score_contribution=-6))

    if features.ma_20 > features.ma_60:
        score += 10
        reasons.append(SignalReason(code="MA20_ABOVE_MA60", description="Medium-term trend is upward.", score_contribution=10))
    else:
        score -= 8
        reasons.append(SignalReason(code="MA20_BELOW_MA60", description="Medium-term trend is weakening.", score_contribution=-8))

    if features.return_5d > 0:
        contribution = min(features.return_5d * 120, 8)
        score += contribution
        reasons.append(SignalReason(code="RETURN_5D_POSITIVE", description="5-day return is positive.", score_contribution=round(contribution, 2)))
    elif features.return_5d < -0.05:
        score -= 5
        risk_flags.append("SHORT_TERM_WEAKNESS")

    if features.rsi_14 >= 75:
        score -= 10
        risk_flags.append("RSI_OVERHEATED")
    elif features.rsi_14 <= 30:
        score += 4
        reasons.append(SignalReason(code="RSI_RECOVERY_ZONE", description="RSI is in a possible rebound zone.", score_contribution=4))

    if features.rel_volume > 1.3:
        score += 6
        reasons.append(SignalReason(code="VOLUME_EXPANSION", description="Trading volume expanded versus average.", score_contribution=6))
    if features.turnover_value_zscore > 1.0:
        score += 4
        reasons.append(SignalReason(code="TURNOVER_SURGE", description="Turnover is above the recent mean.", score_contribution=4))

    score += features.news_sentiment_7d * 8
    score += features.news_attention_score * 4
    score += features.disclosure_impact_30d * 10
    score += features.disclosure_bullish_score * 7
    score -= features.disclosure_bearish_score * 8
    score += features.disclosure_net_score * 10
    score += features.material_disclosure_severity * 4
    score += features.overnight_us_signal * 60
    score += max(0.0, features.overnight_us_correlation) * 2
    score += features.supply_contract_score * 5
    score += features.shareholder_return_score * 4
    score += features.governance_score * 2
    score += features.contract_event_ratio * 3
    score += features.earnings_event_ratio * 2
    score += features.sector_fund_flow_score * 6
    score += max(0.0, features.sector_coupling_score - 0.5) * 8
    score += features.sector_breadth_score * 4
    score += features.sector_leader_relative_strength * 10
    score += features.macro_support_score * 3
    score += features.macro_global_score * 2
    score += features.macro_surprise_index * 4
    score += max(0.0, features.macro_consensus_coverage - 0.5) * 2
    score += features.event_pattern_bias * 20 * max(0.3, features.event_pattern_confidence)

    score += min(max(features.revenue_growth_yoy, -0.5), 0.5) * 12
    score += min(max(features.operating_margin, -0.3), 0.3) * 18
    score += min(max(features.net_margin, -0.3), 0.3) * 12
    score += min(max(features.current_ratio - 1.0, -1.0), 1.0) * 4
    score += min(max(features.operating_cashflow_margin, -0.2), 0.2) * 10
    score -= min(max(features.debt_ratio - 1.0, 0.0), 2.5) * 6

    if features.revenue_growth_yoy >= 0.08:
        reasons.append(SignalReason(code="REVENUE_GROWTH_STRONG", description="Revenue growth is strong in the latest financial statement.", score_contribution=round(min(features.revenue_growth_yoy, 0.5) * 12, 2)))
    if features.operating_margin >= 0.08:
        reasons.append(SignalReason(code="OPERATING_MARGIN_HEALTHY", description="Operating margin is at a healthy level.", score_contribution=round(min(features.operating_margin, 0.3) * 18, 2)))
    if features.debt_ratio >= 2.0:
        risk_flags.append("LEVERAGE_HIGH")
    if features.current_ratio < 0.9:
        risk_flags.append("LIQUIDITY_PRESSURE")
    if features.operating_cashflow_margin < 0:
        risk_flags.append("CASHFLOW_WEAK")

    score -= features.financing_risk_score * 9
    score -= max(0.0, features.material_disclosure_severity - 0.7) * 5
    score -= max(0.0, -features.overnight_us_signal) * 70
    score -= max(0.0, features.macro_pressure_score) * 7
    score -= features.macro_surprise_abs_mean * 2.5
    score -= max(0.0, features.event_volatility_score - 0.6) * 15

    quality_score = 82.0
    if features.volatility_20d > 0.08:
        quality_score -= 12
        risk_flags.append("VOLATILITY_HIGH")
    if features.atr_14_pct > 0.06:
        quality_score -= 8
        risk_flags.append("ATR_HIGH")
    if features.rel_volume < 0.5:
        quality_score -= 10
        risk_flags.append("LIQUIDITY_WEAK")
    if features.sector_fund_flow_score < 0.2:
        quality_score -= 4
        risk_flags.append("SECTOR_FLOW_WEAK")
    if features.sector_coupling_score < 0.35:
        quality_score -= 3
        risk_flags.append("SECTOR_COUPLING_LOW")
    if features.financing_risk_score >= 0.5:
        quality_score -= 8
        risk_flags.append("FINANCING_OVERHANG")
    if features.disclosure_bearish_score >= 0.6:
        quality_score -= 7
        risk_flags.append("DISCLOSURE_BEARISH")
    if features.material_disclosure_severity >= 0.75:
        quality_score -= 4
        risk_flags.append("DISCLOSURE_EVENT_HEAVY")
    if features.overnight_us_vol_spillover >= 0.35:
        quality_score -= 4
        risk_flags.append("US_OVERNIGHT_VOL_SPILLOVER")
    if features.overnight_us_signal <= -0.015:
        risk_flags.append("US_OVERNIGHT_PRESSURE")
    if features.macro_surprise_abs_mean >= 0.8:
        quality_score -= 5
        risk_flags.append("MACRO_EVENT_VOLATILE")
    if features.macro_surprise_index <= -0.6:
        risk_flags.append("MACRO_SURPRISE_RISK")
    if features.event_volatility_score >= 0.65:
        quality_score -= 8
        risk_flags.append("EVENT_DAY_VOLATILITY_MODE")
    if features.event_pattern_confidence >= 0.5 and features.event_pattern_bias < -0.01:
        risk_flags.append("NEGATIVE_EVENT_PATTERN_MATCH")
    if features.text_keyword_density > 0.08:
        quality_score -= 4
        risk_flags.append("TEXT_EVENT_CROWDING")
    if features.debt_ratio >= 2.0:
        quality_score -= 6
    if features.current_ratio < 0.9:
        quality_score -= 5

    score = max(0.0, min(100.0, round(score, 2)))
    quality_score = max(0.0, min(100.0, round(quality_score, 2)))

    if score >= 80:
        signal_type, direction = "SWING_CANDIDATE", "BUY_WATCH"
    elif score >= 60:
        signal_type, direction = "EVENT_MONITOR", "OBSERVE"
    elif score >= 45:
        signal_type, direction = "NEUTRAL", "HOLD"
    else:
        signal_type, direction = "RISK_WARNING", "CAUTION"

    return SignalResult(
        signal_type=signal_type,
        direction=direction,
        score=score,
        quality_score=quality_score,
        reasons=reasons,
        risk_flags=sorted(set(risk_flags)),
    )

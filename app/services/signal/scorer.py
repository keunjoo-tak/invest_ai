from __future__ import annotations

from app.schemas.common import MarketFeatureSet, SignalReason, SignalResult


def evaluate_signal(features: MarketFeatureSet) -> SignalResult:
    """동작 설명은 인수인계 문서를 참고하세요."""
    score = 50.0
    reasons: list[SignalReason] = []
    risk_flags: list[str] = []

    if features.close > features.ma_20:
        score += 8
        reasons.append(SignalReason(code="PRICE_ABOVE_MA20", description="종가가 20일 이동평균 위", score_contribution=8))
    else:
        score -= 6
        reasons.append(SignalReason(code="PRICE_BELOW_MA20", description="종가가 20일 이동평균 아래", score_contribution=-6))

    if features.ma_20 > features.ma_60:
        score += 10
        reasons.append(SignalReason(code="MA20_ABOVE_MA60", description="중기 추세 우상향", score_contribution=10))
    else:
        score -= 8
        reasons.append(SignalReason(code="MA20_BELOW_MA60", description="중기 추세 약화", score_contribution=-8))

    if features.rsi_14 >= 75:
        score -= 10
        risk_flags.append("RSI_OVERHEATED")
    elif features.rsi_14 <= 30:
        score += 4
        reasons.append(SignalReason(code="RSI_RECOVERY_ZONE", description="과매도 구간 반등 가능", score_contribution=4))

    if features.rel_volume > 1.3:
        score += 7
        reasons.append(SignalReason(code="VOLUME_EXPANSION", description="거래량 확대", score_contribution=7))

    score += features.news_sentiment_7d * 10
    score += features.disclosure_impact_30d * 12
    score -= max(0.0, features.macro_pressure_score) * 6

    quality_score = 80.0
    if features.volatility_20d > 0.08:
        quality_score -= 15
        risk_flags.append("VOLATILITY_HIGH")
    if features.rel_volume < 0.5:
        quality_score -= 10
        risk_flags.append("LIQUIDITY_WEAK")

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
        risk_flags=risk_flags,
    )

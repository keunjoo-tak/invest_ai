from datetime import date

from app.schemas.common import MarketFeatureSet
from app.services.signal.scorer import evaluate_signal


def test_signal_scorer_bullish_case() -> None:
    """강한 가격·이벤트·재무 조합에서 시그널 점수가 충분히 높게 형성되는지 검증한다."""
    features = MarketFeatureSet(
        as_of_date=date.today(),
        close=110.0,
        ma_20=100.0,
        ma_60=95.0,
        rsi_14=58.0,
        volatility_20d=0.03,
        atr_14_pct=0.025,
        return_1d=0.012,
        return_5d=0.045,
        return_20d=0.12,
        gap_return_1d=0.004,
        price_vs_ma20=0.1,
        price_vs_ma60=0.1579,
        rel_volume=1.8,
        turnover_value_zscore=1.6,
        intraday_range_pct=0.022,
        news_sentiment_7d=0.4,
        news_attention_score=0.6,
        text_keyword_density=0.025,
        disclosure_impact_30d=0.5,
        supply_contract_score=0.7,
        financing_risk_score=0.05,
        shareholder_return_score=0.45,
        governance_score=0.2,
        earnings_event_ratio=0.2,
        contract_event_ratio=0.4,
        macro_pressure_score=0.1,
        macro_support_score=0.25,
        macro_global_score=0.15,
        revenue_growth_yoy=0.14,
        operating_margin=0.12,
        net_margin=0.09,
        debt_ratio=0.6,
        current_ratio=1.5,
        operating_cashflow_margin=0.11,
    )
    result = evaluate_signal(features)
    assert result.score >= 60
    assert result.quality_score >= 60


def test_signal_scorer_risk_case() -> None:
    """약한 가격 흐름과 높은 재무 리스크에서 경고 플래그가 생성되는지 검증한다."""
    features = MarketFeatureSet(
        as_of_date=date.today(),
        close=90.0,
        ma_20=100.0,
        ma_60=110.0,
        rsi_14=80.0,
        volatility_20d=0.12,
        atr_14_pct=0.085,
        return_1d=-0.03,
        return_5d=-0.08,
        return_20d=-0.16,
        gap_return_1d=-0.02,
        price_vs_ma20=-0.1,
        price_vs_ma60=-0.1818,
        rel_volume=0.2,
        turnover_value_zscore=-0.8,
        intraday_range_pct=0.065,
        news_sentiment_7d=-0.3,
        news_attention_score=0.7,
        text_keyword_density=0.12,
        disclosure_impact_30d=-0.2,
        supply_contract_score=0.0,
        financing_risk_score=0.7,
        shareholder_return_score=0.0,
        governance_score=0.0,
        earnings_event_ratio=0.0,
        contract_event_ratio=0.0,
        macro_pressure_score=0.6,
        macro_support_score=0.0,
        macro_global_score=-0.4,
        revenue_growth_yoy=-0.18,
        operating_margin=-0.04,
        net_margin=-0.07,
        debt_ratio=2.6,
        current_ratio=0.72,
        operating_cashflow_margin=-0.06,
    )
    result = evaluate_signal(features)
    assert result.score < 60
    assert "VOLATILITY_HIGH" in result.risk_flags
    assert "FINANCING_OVERHANG" in result.risk_flags
    assert "LEVERAGE_HIGH" in result.risk_flags

from datetime import date

from app.schemas.common import MarketFeatureSet
from app.services.signal.scorer import evaluate_signal


def test_signal_scorer_bullish_case() -> None:
    """동작 설명은 인수인계 문서를 참고하세요."""
    features = MarketFeatureSet(
        as_of_date=date.today(),
        close=110.0,
        ma_20=100.0,
        ma_60=95.0,
        rsi_14=58.0,
        volatility_20d=0.03,
        rel_volume=1.8,
        news_sentiment_7d=0.4,
        disclosure_impact_30d=0.5,
        macro_pressure_score=0.1,
    )
    result = evaluate_signal(features)
    assert result.score >= 60
    assert result.quality_score >= 60


def test_signal_scorer_risk_case() -> None:
    """동작 설명은 인수인계 문서를 참고하세요."""
    features = MarketFeatureSet(
        as_of_date=date.today(),
        close=90.0,
        ma_20=100.0,
        ma_60=110.0,
        rsi_14=80.0,
        volatility_20d=0.12,
        rel_volume=0.2,
        news_sentiment_7d=-0.3,
        disclosure_impact_30d=-0.2,
        macro_pressure_score=0.6,
    )
    result = evaluate_signal(features)
    assert result.score < 60
    assert "VOLATILITY_HIGH" in result.risk_flags

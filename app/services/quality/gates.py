from app.schemas.common import MarketFeatureSet, SignalResult


def passes_quality_gate(features: MarketFeatureSet, signal: SignalResult) -> tuple[bool, list[str]]:
    """동작 설명은 인수인계 문서를 참고하세요."""
    failures: list[str] = []
    if signal.quality_score < 60:
        failures.append("quality_score_below_threshold")
    if features.rel_volume < 0.3:
        failures.append("liquidity_too_low")
    if features.close <= 0:
        failures.append("invalid_price")
    return (len(failures) == 0, failures)

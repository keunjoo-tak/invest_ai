from app.schemas.common import SignalReason, SignalResult
from app.services.localization.signal_localizer import has_risk_flag, localize_signal_result


def test_localize_signal_result_to_korean_labels() -> None:
    signal = SignalResult(
        signal_type='EVENT_MONITOR',
        direction='OBSERVE',
        score=67.0,
        quality_score=72.0,
        reasons=[SignalReason(code='PRICE_ABOVE_MA20', description='Price is above the 20-day moving average.', score_contribution=8.0)],
        risk_flags=['EVENT_DAY_VOLATILITY_MODE', 'VOLATILITY_HIGH'],
    )

    localized = localize_signal_result(signal, 'ko')

    assert localized.signal_type == '이벤트 관찰'
    assert localized.direction == '관찰'
    assert localized.signal_type_code == 'EVENT_MONITOR'
    assert localized.direction_code == 'OBSERVE'
    assert localized.reasons[0].description == '주가가 20일 이동평균 위에 있습니다.'
    assert localized.risk_flags == ['이벤트 당일 변동성 주의', '변동성 높음']
    assert localized.risk_flag_codes == ['EVENT_DAY_VOLATILITY_MODE', 'VOLATILITY_HIGH']


def test_has_risk_flag_uses_codes_after_localization() -> None:
    signal = SignalResult(
        signal_type='위험 경고',
        direction='주의',
        score=40.0,
        quality_score=55.0,
        risk_flags=['이벤트 당일 변동성 주의'],
        risk_flag_codes=['EVENT_DAY_VOLATILITY_MODE'],
    )

    assert has_risk_flag(signal, 'EVENT_DAY_VOLATILITY_MODE') is True
    assert has_risk_flag(signal, 'VOLATILITY_HIGH') is False

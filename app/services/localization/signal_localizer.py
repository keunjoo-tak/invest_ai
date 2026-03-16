from __future__ import annotations

from app.schemas.common import SignalReason, SignalResult

_SIGNAL_TYPE_LABELS = {
    'SWING_CANDIDATE': '스윙 후보',
    'EVENT_MONITOR': '이벤트 관찰',
    'NEUTRAL': '중립',
    'RISK_WARNING': '위험 경고',
}

_DIRECTION_LABELS = {
    'BUY_WATCH': '매수 관찰',
    'OBSERVE': '관찰',
    'HOLD': '보유',
    'CAUTION': '주의',
}

_RISK_FLAG_LABELS = {
    'SHORT_TERM_WEAKNESS': '단기 약세',
    'RSI_OVERHEATED': 'RSI 과열',
    'LEVERAGE_HIGH': '레버리지 부담',
    'LIQUIDITY_PRESSURE': '유동성 압박',
    'CASHFLOW_WEAK': '현금흐름 약화',
    'VOLATILITY_HIGH': '변동성 높음',
    'ATR_HIGH': 'ATR 변동성 높음',
    'LIQUIDITY_WEAK': '거래 유동성 약함',
    'SECTOR_FLOW_WEAK': '섹터 자금 유입 약함',
    'SECTOR_COUPLING_LOW': '섹터 대장주 연동 약함',
    'FINANCING_OVERHANG': '자금조달 부담',
    'DISCLOSURE_BEARISH': '공시 악재 우위',
    'DISCLOSURE_EVENT_HEAVY': '중요 공시 이벤트 집중',
    'US_OVERNIGHT_VOL_SPILLOVER': '미국 야간 변동성 전이',
    'US_OVERNIGHT_PRESSURE': '미국 야간 하방 압력',
    'MACRO_EVENT_VOLATILE': '거시 이벤트 변동성 확대',
    'MACRO_SURPRISE_RISK': '거시 서프라이즈 리스크',
    'EVENT_DAY_VOLATILITY_MODE': '이벤트 당일 변동성 주의',
    'NEGATIVE_EVENT_PATTERN_MATCH': '유사 이벤트 약세 패턴 일치',
    'TEXT_EVENT_CROWDING': '이벤트 과밀 구간',
    'quality_score_below_threshold': '품질 점수 기준 미달',
    'liquidity_too_low': '거래 유동성 기준 미달',
    'invalid_price': '유효하지 않은 가격 데이터',
}

_REASON_LABELS = {
    'PRICE_ABOVE_MA20': '주가가 20일 이동평균 위에 있습니다.',
    'PRICE_BELOW_MA20': '주가가 20일 이동평균 아래에 있습니다.',
    'MA20_ABOVE_MA60': '중기 추세가 상승 방향입니다.',
    'MA20_BELOW_MA60': '중기 추세가 약화되고 있습니다.',
    'RETURN_5D_POSITIVE': '최근 5거래일 수익률이 플러스입니다.',
    'RSI_RECOVERY_ZONE': 'RSI가 반등 가능 구간에 있습니다.',
    'VOLUME_EXPANSION': '거래량이 최근 평균 대비 확대되었습니다.',
    'TURNOVER_SURGE': '거래대금이 최근 평균을 상회합니다.',
    'REVENUE_GROWTH_STRONG': '최근 재무제표 기준 매출 성장세가 견조합니다.',
    'OPERATING_MARGIN_HEALTHY': '영업이익률이 양호한 수준입니다.',
}


def localize_signal_type(code: str, language: str = 'ko') -> str:
    if language != 'ko':
        return code
    return _SIGNAL_TYPE_LABELS.get(code, code)


def localize_direction(code: str, language: str = 'ko') -> str:
    if language != 'ko':
        return code
    return _DIRECTION_LABELS.get(code, code)


def localize_risk_flag(code: str, language: str = 'ko') -> str:
    if language != 'ko':
        return code
    return _RISK_FLAG_LABELS.get(code, code)


def localize_reason(reason: SignalReason, language: str = 'ko') -> SignalReason:
    if language != 'ko':
        return reason
    return reason.model_copy(update={'description': _REASON_LABELS.get(reason.code, reason.description)}, deep=True)


def localize_signal_result(signal: SignalResult, language: str = 'ko') -> SignalResult:
    if language != 'ko':
        return signal
    risk_codes = list(signal.risk_flag_codes or signal.risk_flags or [])
    signal_type_code = signal.signal_type_code or signal.signal_type
    direction_code = signal.direction_code or signal.direction
    return signal.model_copy(
        update={
            'signal_type': localize_signal_type(signal_type_code, language),
            'direction': localize_direction(direction_code, language),
            'signal_type_code': signal_type_code,
            'direction_code': direction_code,
            'reasons': [localize_reason(reason, language) for reason in signal.reasons],
            'risk_flags': [localize_risk_flag(code, language) for code in risk_codes],
            'risk_flag_codes': risk_codes,
        },
        deep=True,
    )


def has_risk_flag(signal: SignalResult, code: str) -> bool:
    codes = list(signal.risk_flag_codes or signal.risk_flags or [])
    return code in codes

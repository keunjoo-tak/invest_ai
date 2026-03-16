from app.schemas.common import MarketFeatureSet, SignalResult
from app.services.localization.signal_localizer import localize_signal_result


def format_alert_message(ticker: str, name_kr: str, features: MarketFeatureSet, signal: SignalResult, explanation: dict) -> str:
    """텔레그램 알림 메시지 본문을 생성합니다."""
    localized_signal = localize_signal_result(signal, 'ko')
    reasons = ', '.join([reason.description for reason in localized_signal.reasons][:4]) or '없음'
    risks = ', '.join(localized_signal.risk_flags) if localized_signal.risk_flags else '없음'
    summary = explanation.get('summary_short', '설명 생성에 실패해 기본 요약을 사용했습니다.')
    return (
        f'[InvestAI] {name_kr}({ticker})\n'
        f'- 신호: {localized_signal.signal_type} / {localized_signal.direction}\n'
        f'- 점수: {signal.score} (품질:{signal.quality_score})\n'
        f'- 가격: {features.close} / MA20:{features.ma_20} / MA60:{features.ma_60}\n'
        f'- RSI14:{features.rsi_14} / 상대거래량:{features.rel_volume}\n'
        f'- 주요 근거: {reasons}\n'
        f'- 위험 요인: {risks}\n'
        f'- 요약: {summary}\n'
        f'- 참고: 자동매매가 아닌 수동 검토용 정보입니다.'
    )

from app.schemas.common import MarketFeatureSet, SignalResult


def format_alert_message(ticker: str, name_kr: str, features: MarketFeatureSet, signal: SignalResult, explanation: dict) -> str:
    """텔레그램 알림 본문 포맷을 생성한다."""
    reasons = ", ".join([f"{r.code}" for r in signal.reasons][:4]) or "N/A"
    risks = ", ".join(signal.risk_flags) if signal.risk_flags else "없음"
    summary = explanation.get("summary_short", "설명 생성 실패로 대체 요약이 적용되었습니다.")
    return (
        f"[InvestAI] {name_kr}({ticker})\n"
        f"- 신호: {signal.signal_type} / {signal.direction}\n"
        f"- 점수: {signal.score} (품질:{signal.quality_score})\n"
        f"- 가격: {features.close} / MA20:{features.ma_20} / MA60:{features.ma_60}\n"
        f"- RSI14:{features.rsi_14} / 상대거래량:{features.rel_volume}\n"
        f"- 주요 근거: {reasons}\n"
        f"- 위험요인: {risks}\n"
        f"- 요약: {summary}\n"
        f"- 참고: 자동매매가 아닌 수동 검토용 정보입니다."
    )

from app.schemas.common import MarketFeatureSet, SignalResult


def format_alert_message(ticker: str, name_kr: str, features: MarketFeatureSet, signal: SignalResult, explanation: dict) -> str:
    reasons = ", ".join([f"{r.code}" for r in signal.reasons][:4]) or "N/A"
    risks = ", ".join(signal.risk_flags) if signal.risk_flags else "없음"
    summary = explanation.get("summary_short", "설명 생성 실패, 기본 요약 사용")
    return (
        f"[InvestAI] {name_kr}({ticker})\n"
        f"- Signal: {signal.signal_type} / {signal.direction}\n"
        f"- Score: {signal.score} (Q:{signal.quality_score})\n"
        f"- Price: {features.close} / MA20:{features.ma_20} / MA60:{features.ma_60}\n"
        f"- RSI14:{features.rsi_14} / RelVol:{features.rel_volume}\n"
        f"- Reasons: {reasons}\n"
        f"- Risks: {risks}\n"
        f"- Summary: {summary}\n"
        f"- Note: 자동주문 아님, 수동 검토 후 주문"
    )

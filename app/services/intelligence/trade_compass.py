from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.intelligence import TradeCompassRequest, TradeCompassResponse, TradeScenario
from app.services.intelligence.stock_insight import StockInsightEngine


class TradeCompassEngine:
    """Trade Compass 엔진."""

    def __init__(self) -> None:
        self.stock = StockInsightEngine()

    def _zone(self, center: float, pct: float) -> str:
        low = center * (1 - pct)
        high = center * (1 + pct)
        return f"{low:.0f} ~ {high:.0f}"

    def analyze(self, req: TradeCompassRequest) -> TradeCompassResponse:
        insight = self.stock.analyze(req.ticker_or_name, req.as_of_date)
        close = insight.features.close
        score = insight.signal.score

        if req.risk_profile == "conservative":
            buy_pct, invalid_pct, t1, t2 = 0.04, 0.05, 0.08, 0.13
        elif req.risk_profile == "aggressive":
            buy_pct, invalid_pct, t1, t2 = 0.02, 0.07, 0.1, 0.18
        else:
            buy_pct, invalid_pct, t1, t2 = 0.03, 0.06, 0.09, 0.15

        if score >= 70:
            action = "분할 진입"
            conf = "중상"
        elif score >= 60:
            action = "보유/관망"
            conf = "중"
        elif score >= 45:
            action = "관망"
            conf = "중하"
        else:
            action = "리스크 축소"
            conf = "낮음"

        scenarios = [
            TradeScenario(
                scenario="상승",
                trigger=f"종가가 MA20({insight.features.ma_20}) 위에서 유지",
                action="보유 비중 유지 또는 분할 추세추종",
                rationale="추세 지속 구간에서는 추격보다 눌림 분할이 유리함.",
            ),
            TradeScenario(
                scenario="기본",
                trigger="가격이 MA20 인근 박스권 유지",
                action="관망하며 거래량/공시 이벤트 체크",
                rationale="방향성 확정 전에는 과도한 포지션 확대를 지양.",
            ),
            TradeScenario(
                scenario="하락",
                trigger=f"가격이 무효화 구간({self._zone(close, invalid_pct)}) 하단 이탈",
                action="비중 축소 및 재진입 시그널 대기",
                rationale="무효화 조건 발생 시 손실 확대를 방지.",
            ),
        ]

        reasoning = [
            insight.one_line_diagnosis,
            f"현재 신호 점수 {score}, 품질 점수 {insight.signal.quality_score}.",
            f"상대거래량 {insight.features.rel_volume}, 뉴스감성 {insight.features.news_sentiment_7d}.",
        ]

        return TradeCompassResponse(
            ticker=insight.ticker,
            instrument_name=insight.instrument_name,
            as_of_date=insight.as_of_date,
            generated_at_utc=datetime.now(timezone.utc),
            recommended_action=action,
            confidence_band=conf,
            buy_interest_zone=self._zone(close, buy_pct),
            invalidation_zone=self._zone(close, invalid_pct),
            target_zone_primary=self._zone(close * (1 + t1), 0.01),
            target_zone_secondary=self._zone(close * (1 + t2), 0.015),
            scenarios=scenarios,
            risks=insight.risk_factors,
            reasoning=reasoning,
            source_insight=insight,
        )

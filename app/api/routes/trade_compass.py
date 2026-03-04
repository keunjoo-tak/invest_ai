from __future__ import annotations

from fastapi import APIRouter

from app.schemas.intelligence import TradeCompassRequest, TradeCompassResponse
from app.services.intelligence.trade_compass import TradeCompassEngine

router = APIRouter(prefix="/trade-compass", tags=["trade-compass"])
engine = TradeCompassEngine()


@router.post(
    "/analyze",
    response_model=TradeCompassResponse,
    summary="Trade Compass 전략 분석",
    description="Stock Insight 결과를 기반으로 시나리오별 대응 전략과 가격대를 제공합니다.",
)
def analyze_trade_compass(req: TradeCompassRequest) -> TradeCompassResponse:
    """전략 분석."""
    return engine.analyze(req)


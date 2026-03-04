from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.schemas.intelligence import MarketPulseOverviewResponse
from app.services.intelligence.market_pulse import MarketPulseEngine

router = APIRouter(prefix="/market-pulse", tags=["market-pulse"])
engine = MarketPulseEngine()


@router.get(
    "/overview",
    response_model=MarketPulseOverviewResponse,
    summary="Market Pulse 개요",
    description="섹터 강약/시장 체제/거시 스냅샷을 통합해 일일 시장 브리프를 반환합니다.",
)
def get_market_overview(
    as_of_date: date | None = Query(default=None, description="기준일(미입력 시 오늘)"),
) -> MarketPulseOverviewResponse:
    """시장 개요 조회."""
    return engine.overview(as_of_date=as_of_date)


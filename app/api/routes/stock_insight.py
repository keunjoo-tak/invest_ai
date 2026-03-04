from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.schemas.intelligence import StockInsightResponse
from app.services.intelligence.stock_insight import StockInsightEngine

router = APIRouter(prefix="/stock-insight", tags=["stock-insight"])
engine = StockInsightEngine()


@router.get(
    "/{ticker_or_name}",
    response_model=StockInsightResponse,
    summary="Stock Insight 종목 분석",
    description="종목 상태, 이벤트, 기술/수급/리스크 요인을 통합 분석해 종목 인사이트를 반환합니다.",
)
def get_stock_insight(
    ticker_or_name: str,
    as_of_date: date | None = Query(default=None, description="기준일(미입력 시 오늘)"),
) -> StockInsightResponse:
    """종목 인사이트 조회."""
    return engine.analyze(ticker_or_name=ticker_or_name, as_of_date=as_of_date)


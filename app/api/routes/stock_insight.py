from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.schemas.intelligence import StockInsightResponse
from app.services.intelligence.stock_insight import StockInsightEngine

router = APIRouter(prefix='/stock-insight', tags=['legacy-products'])
engine = StockInsightEngine()


@router.get(
    '/{ticker_or_name}',
    response_model=StockInsightResponse,
    summary='Legacy Stock Insight view',
    description='Deprecated. Use GET /api/v1/stock-decision/{ticker_or_name} for the current decision-centric product.',
    deprecated=True,
)
def get_stock_insight(
    ticker_or_name: str,
    as_of_date: date | None = Query(default=None, description='Analysis date'),
) -> StockInsightResponse:
    return engine.analyze(ticker_or_name=ticker_or_name, as_of_date=as_of_date)

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.schemas.intelligence import MarketPulseOverviewResponse
from app.services.intelligence.market_pulse import MarketPulseEngine

router = APIRouter(prefix='/market-pulse', tags=['legacy-products'])
engine = MarketPulseEngine()


@router.get(
    '/overview',
    response_model=MarketPulseOverviewResponse,
    summary='Legacy Market Pulse view',
    description='Deprecated. Use GET /api/v1/market-regime/overview for the current market regime product.',
    deprecated=True,
)
def get_market_overview(
    as_of_date: date | None = Query(default=None, description='Analysis date'),
) -> MarketPulseOverviewResponse:
    return engine.overview(as_of_date=as_of_date)

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.intelligence import TradeCompassRequest, TradeCompassResponse
from app.services.intelligence.trade_compass import TradeCompassEngine

router = APIRouter(prefix='/trade-compass', tags=['legacy-products'])
engine = TradeCompassEngine()


@router.post(
    '/analyze',
    response_model=TradeCompassResponse,
    summary='Legacy Trade Compass view',
    description='Deprecated. Use POST /api/v1/action-planner/analyze for the current execution product.',
    deprecated=True,
)
def analyze_trade_compass(req: TradeCompassRequest) -> TradeCompassResponse:
    return engine.analyze(req)

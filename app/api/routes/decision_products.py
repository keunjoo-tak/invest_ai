from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.decision_products import (
    ActionPlannerRequest,
    ActionPlannerResponse,
    MarketRegimeResponse,
    StockDecisionResponse,
    WatchlistAlertRequest,
    WatchlistAlertResponse,
    WatchlistSubscriptionDeleteResponse,
    WatchlistSubscriptionRequest,
    WatchlistSubscriptionResponse,
)
from app.services.intelligence.decision_products import DecisionProductService

router = APIRouter(tags=['decision-products'])
service = DecisionProductService()


@router.get(
    '/market-regime/overview',
    response_model=MarketRegimeResponse,
    summary='시장 체제 개요',
    description='시장 체제, 글로벌 거시 압력, 강세·약세 섹터, 전략 힌트를 통합해 반환합니다.',
)
async def get_market_regime_overview(
    as_of_date: date | None = Query(default=None, description='분석 기준일입니다. 비우면 오늘 기준으로 처리합니다.'),
    db: Session = Depends(get_db),
) -> MarketRegimeResponse:
    return await service.build_market_regime(as_of_date=as_of_date, db=db)


@router.get(
    '/stock-decision/{ticker_or_name}',
    response_model=StockDecisionResponse,
    summary='종목 통합 판단',
    description='공통 분석 결과를 바탕으로 종목 결론, 상승·하락 요인, 최근 이벤트, 재무·거시 요약을 제공합니다.',
)
async def get_stock_decision(
    ticker_or_name: str,
    as_of_date: date | None = Query(default=None, description='분석 기준일입니다.'),
    lookback_days: int = Query(default=365, ge=60, le=730, description='과거 조회 구간 일수입니다.'),
    db: Session = Depends(get_db),
) -> StockDecisionResponse:
    return await service.build_stock_decision(db, ticker_or_name, as_of_date, lookback_days)


@router.post(
    '/action-planner/analyze',
    response_model=ActionPlannerResponse,
    summary='행동 계획 생성',
    description='종목 판단 결과를 바탕으로 실행 가능한 매매 계획, 시나리오, 진입 구간과 무효화 구간을 생성합니다.',
)
async def analyze_action_plan(req: ActionPlannerRequest, db: Session = Depends(get_db)) -> ActionPlannerResponse:
    return await service.build_action_plan(db, req)


@router.post(
    '/watchlist-alerts/check',
    response_model=WatchlistAlertResponse,
    summary='관찰 알림 점검',
    description='현재 시점에서 바로 대응이 필요한지 점검하고, 핵심 트리거와 알림 미리보기를 반환합니다.',
)
async def check_watchlist_alert(req: WatchlistAlertRequest, db: Session = Depends(get_db)) -> WatchlistAlertResponse:
    return await service.build_watchlist_alert(db, req)


@router.post(
    '/watchlist-alerts/subscriptions',
    response_model=WatchlistSubscriptionResponse,
    summary='관찰 종목 구독 생성',
    description='종목을 저장형 워치리스트에 등록해 지속 관찰할 수 있도록 합니다.',
)
def create_watchlist_subscription(req: WatchlistSubscriptionRequest, db: Session = Depends(get_db)) -> WatchlistSubscriptionResponse:
    return service.add_watchlist_subscription(db, req)


@router.get(
    '/watchlist-alerts/subscriptions',
    response_model=list[WatchlistSubscriptionResponse],
    summary='관찰 종목 구독 목록',
    description='데이터베이스에 저장된 활성 워치리스트 구독 목록을 반환합니다.',
)
def list_watchlist_subscriptions(db: Session = Depends(get_db)) -> list[WatchlistSubscriptionResponse]:
    return service.list_watchlist_subscriptions(db)


@router.delete(
    '/watchlist-alerts/subscriptions/{ticker_or_name}',
    response_model=WatchlistSubscriptionDeleteResponse,
    summary='관찰 종목 구독 해제',
    description='지정한 종목과 채널의 워치리스트 구독을 비활성화합니다.',
)
def delete_watchlist_subscription(
    ticker_or_name: str,
    channel: str = Query(default='telegram', description='알림 채널입니다. 현재는 telegram만 지원합니다.'),
    db: Session = Depends(get_db),
) -> WatchlistSubscriptionDeleteResponse:
    return service.delete_watchlist_subscription(db, ticker_or_name, channel)

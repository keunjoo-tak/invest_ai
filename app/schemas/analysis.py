from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import MarketFeatureSet, SignalResult


class AnalyzeTickerRequest(BaseModel):
    """종목 통합 분석 요청 모델."""

    ticker_or_name: str = Field(min_length=1, max_length=100, description='티커 또는 공식 종목명')
    as_of_date: date | None = Field(default=None, description='분석 기준일입니다. 비우면 오늘 기준으로 처리합니다.')
    lookback_days: int = Field(default=365, ge=60, le=730, description='과거 조회 구간 일수')
    analysis_mode: str = Field(default='full', pattern='^(quick|full)$', description='분석 모드')
    notify: bool = Field(default=True, description='알림 발송 판단 포함 여부')
    force_send: bool = Field(default=False, description='개발용 강제 발송 플래그')
    channels: list[str] = Field(default_factory=lambda: ['telegram'], description='알림 채널 목록')
    response_language: str = Field(default='ko', pattern='^(ko|en)$', description='응답 언어')


class AlertPayload(BaseModel):
    """알림 실행 결과."""

    should_send: bool
    dedup_blocked: bool = False
    channel_results: dict[str, Any] = Field(default_factory=dict)
    message: str


class AnalyzeTickerResponse(BaseModel):
    """종목 통합 분석 응답 모델."""

    request_id: str
    ticker: str
    instrument_name: str
    as_of_date: date
    generated_at_utc: datetime
    response_language: str = Field(default='ko', description='응답 언어')
    features: MarketFeatureSet
    signal: SignalResult
    explanation: dict[str, Any]
    alert: AlertPayload

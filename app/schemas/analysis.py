from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import MarketFeatureSet, SignalResult


class AnalyzeTickerRequest(BaseModel):
    """종목 분석 요청 모델."""

    ticker_or_name: str = Field(min_length=1, max_length=100, description="분석 대상 종목의 티커 또는 종목명")
    as_of_date: date | None = Field(default=None, description="기준 분석일자 (미입력 시 오늘)")
    lookback_days: int = Field(default=365, ge=60, le=730, description="과거 조회 기간(일수)")
    analysis_mode: str = Field(default="full", pattern="^(quick|full)$", description="분석 모드 (quick/full)")
    notify: bool = Field(default=True, description="알림 발송 시도 여부")
    force_send: bool = Field(default=False, description="개발/테스트용 강제 발송 여부(임계치/쿨다운 우회)")
    channels: list[str] = Field(default_factory=lambda: ["telegram"], description="알림 채널 목록 (현재 telegram 지원)")
    response_language: str = Field(default="ko", pattern="^(ko|en)$", description="응답 언어(ko/en)")


class AlertPayload(BaseModel):
    """알림 실행 결과 모델."""

    should_send: bool
    dedup_blocked: bool = False
    channel_results: dict[str, Any] = Field(default_factory=dict)
    message: str


class AnalyzeTickerResponse(BaseModel):
    """종목 분석 응답 모델."""

    request_id: str
    ticker: str
    instrument_name: str
    as_of_date: date
    generated_at_utc: datetime
    response_language: str = Field(default="ko", description="응답 언어")
    features: MarketFeatureSet
    signal: SignalResult
    explanation: dict[str, Any]
    alert: AlertPayload

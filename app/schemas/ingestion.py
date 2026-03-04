from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class TickerIngestionRequest(BaseModel):
    """수집 점검 요청 모델."""

    ticker_or_name: str = Field(min_length=1, max_length=100, description="조회 대상 종목의 티커 또는 종목명")
    as_of_date: date | None = Field(default=None, description="기준 날짜 (미입력 시 오늘)")
    lookback_days: int = Field(default=365, ge=1, le=3650, description="가격 조회 lookback 일수")
    max_items: int = Field(default=20, ge=1, le=100, description="뉴스/X 조회 최대 건수")
    days: int = Field(default=30, ge=1, le=365, description="공시 조회 기간(일)")


class XRecentSearchRequest(BaseModel):
    """X 최근 검색 요청 모델."""

    query: str = Field(min_length=1, max_length=512, description="X Recent Search 쿼리 문자열")
    max_results: int = Field(default=10, ge=10, le=100, description="반환 최대 건수 (X API 제한 범위)")


class InstrumentSearchRequest(BaseModel):
    """종목 후보 검색 요청 모델."""

    query: str = Field(min_length=1, max_length=100, description="검색할 한국 주식 종목명 또는 티커 일부")
    limit: int = Field(default=10, ge=1, le=50, description="반환할 후보 최대 개수")


class InstrumentSearchCandidate(BaseModel):
    """종목 검색 후보 모델."""

    ticker: str = Field(description="공식 사용 티커(6자리)")
    name_kr: str = Field(description="공식 종목명(또는 법인명 기반)")
    market: str = Field(default="KR", description="시장 구분")
    score: float = Field(description="텍스트 유사도 점수(0~1)")
    match_type: str = Field(description="매칭 방식(exact/contains/fuzzy 등)")
    corp_code: str | None = Field(default=None, description="DART corp_code (있을 경우)")


class InstrumentSearchResponse(BaseModel):
    """종목 후보 검색 응답 모델."""

    query: str = Field(description="입력 검색어")
    normalized_query: str = Field(description="정규화 검색어(공백/기호 제거)")
    item_count: int = Field(description="후보 개수")
    candidates: list[InstrumentSearchCandidate] = Field(default_factory=list, description="종목 후보 목록")


class IngestionProbeResponse(BaseModel):
    """수집 소스별 점검 응답 모델."""

    source: str = Field(description="수집 테스트 소스명")
    success: bool = Field(description="수집/호출 성공 여부")
    as_of_utc: datetime = Field(description="응답 생성 시각(UTC)")
    used_fallback: bool = Field(default=False, description="fallback 데이터 사용 여부")
    item_count: int = Field(default=0, description="수집/반환 건수")
    details: dict[str, Any] = Field(default_factory=dict, description="테스트 상세 진단 정보")
    sample: list[dict[str, Any]] = Field(default_factory=list, description="샘플 레코드")


class CollectExternalBundleResponse(BaseModel):
    """외부 수집 번들 응답 모델."""

    ticker: str = Field(description="정규화된 티커")
    instrument_name: str = Field(description="종목명")
    as_of_date: date = Field(description="조회 기준일")
    sources: list[IngestionProbeResponse] = Field(description="소스별 수집 결과")

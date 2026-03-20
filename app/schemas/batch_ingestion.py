from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KindBatchRequest(BaseModel):
    """KRX KIND 공시 배치 요청."""

    ticker_or_name: str = Field(min_length=1, max_length=100, description='수집 대상 종목명 또는 티커')
    max_items: int = Field(default=20, ge=1, le=100, description='최대 수집 건수')


class GenericBatchRequest(BaseModel):
    """공용 배치 요청 모델."""

    max_items: int = Field(default=30, ge=1, le=200, description='최대 수집 건수')


class ResearchBatchRequest(GenericBatchRequest):
    """공개 리서치 문서 배치 요청."""

    group: str = Field(
        default='all',
        pattern='^(all|domestic|global|broker|bank|domestic_broker|domestic_bank|global_public)$',
        description='수집 대상 그룹',
    )


class BatchIngestionResponse(BaseModel):
    """배치 실행 결과."""

    source_system: str
    request_id: str
    started_at_utc: datetime
    finished_at_utc: datetime
    fetched_count: int
    stored_count: int
    skipped_count: int
    saved_call_dir: str
    message: str

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KindBatchRequest(BaseModel):
    """KRX KIND 공시 배치 요청."""

    ticker_or_name: str = Field(min_length=1, max_length=100, description="종목명 또는 티커")
    max_items: int = Field(default=20, ge=1, le=100, description="최대 수집 건수")


class GenericBatchRequest(BaseModel):
    """문서형 배치 요청."""

    max_items: int = Field(default=30, ge=1, le=200, description="최대 수집 건수")


class BatchIngestionResponse(BaseModel):
    """배치 수집 응답."""

    source_system: str
    request_id: str
    started_at_utc: datetime
    finished_at_utc: datetime
    fetched_count: int
    stored_count: int
    skipped_count: int
    saved_call_dir: str
    message: str

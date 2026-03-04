from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DataSourceItem(BaseModel):
    """데이터소스 카탈로그 항목."""

    source_id: str
    name: str
    category: str
    url: str
    collection_mode: str
    parser_required: bool


class CrawlPreviewRequest(BaseModel):
    """크롤링 미리보기 요청."""

    source_id: str = Field(min_length=2, max_length=20)
    target_url: str | None = Field(default=None)
    max_chars: int = Field(default=8000, ge=500, le=50000)


class CrawlCollectRequest(BaseModel):
    """원문 수집 요청."""

    source_id: str = Field(min_length=2, max_length=20)
    target_url: str | None = Field(default=None)
    request_label: str = Field(default="manual_collect", min_length=2, max_length=60)
    max_chars: int = Field(default=12000, ge=500, le=100000)


class ParsedDocument(BaseModel):
    """파싱/전처리 결과 문서."""

    source_id: str
    source_url: str
    title: str
    content_text: str
    entities: list[dict[str, Any]] = Field(default_factory=list)
    event_type: str
    scores: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str
    version: int
    created_at_utc: datetime


class CrawlPreviewResponse(BaseModel):
    """크롤링 미리보기 응답."""

    source_id: str
    fetched_url: str
    http_status: int
    content_type: str
    content_length: int
    sample_text: str
    parsed: ParsedDocument


class CrawlCollectResponse(BaseModel):
    """원문 수집 응답."""

    request_id: str
    source_id: str
    fetched_url: str
    http_status: int
    saved_call_dir: str
    saved_paths: dict[str, str] = Field(default_factory=dict)
    parsed: ParsedDocument

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.schemas.ingestion_pipeline import (
    CrawlCollectRequest,
    CrawlCollectResponse,
    CrawlPreviewRequest,
    CrawlPreviewResponse,
    DataSourceItem,
)
from app.services.ingestion.crawlers import CrawlCollector
from app.services.ingestion.source_catalog import SOURCE_CATALOG

router = APIRouter(prefix="/ingestion", tags=["ingestion-pipeline"])
collector = CrawlCollector()


@router.get(
    "/sources/catalog",
    response_model=list[DataSourceItem],
    summary="데이터소스 카탈로그 조회",
    description="investai_데이터소스설계_v2 기준 수집 소스 카탈로그를 반환합니다.",
)
def get_source_catalog() -> list[DataSourceItem]:
    """소스 카탈로그 조회."""
    return [
        DataSourceItem(
            source_id=x.source_id,
            name=x.name,
            category=x.category,
            url=x.url,
            collection_mode=x.collection_mode,
            parser_required=x.parser_required,
        )
        for x in SOURCE_CATALOG
    ]


@router.post(
    "/crawl/preview",
    response_model=CrawlPreviewResponse,
    summary="소스 크롤링/파싱 미리보기",
    description="소스별 페이지를 가져와 전처리, 엔터티 링크, 이벤트 분류, 점수화를 미리 확인합니다.",
)
def crawl_preview(req: CrawlPreviewRequest) -> CrawlPreviewResponse:
    """크롤링 미리보기."""
    out = collector.fetch_preview(source_id=req.source_id, target_url=req.target_url, max_chars=req.max_chars)
    return CrawlPreviewResponse(
        source_id=out["source_id"],
        fetched_url=out["fetched_url"],
        http_status=out["http_status"],
        content_type=out["content_type"],
        content_length=out["content_length"],
        sample_text=out["sample_text"],
        parsed=out["parsed"],
    )


@router.post(
    "/crawl/collect",
    response_model=CrawlCollectResponse,
    summary="원문 수집 및 로컬 저장",
    description="호출 단위 폴더를 생성해 원문/메타/파싱결과를 downloads 하위에 저장합니다.",
)
def crawl_collect(req: CrawlCollectRequest) -> CrawlCollectResponse:
    """원문 수집."""
    request_id = str(uuid.uuid4())
    out = collector.collect_and_save(
        source_id=req.source_id,
        request_id=request_id,
        request_label=req.request_label,
        target_url=req.target_url,
        max_chars=req.max_chars,
    )
    return CrawlCollectResponse(
        request_id=request_id,
        source_id=out["source_id"],
        fetched_url=out["fetched_url"],
        http_status=out["http_status"],
        saved_call_dir=out["saved_call_dir"],
        saved_paths=out["saved_paths"],
        parsed=out["parsed"],
    )

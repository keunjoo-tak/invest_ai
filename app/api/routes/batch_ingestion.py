from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.batch_ingestion import BatchIngestionResponse, GenericBatchRequest, KindBatchRequest
from app.services.ingestion.batch_ingestor import BatchIngestor

router = APIRouter(prefix="/batch", tags=["batch-ingestion"])
ingestor = BatchIngestor()


@router.post(
    "/kind/disclosures",
    response_model=BatchIngestionResponse,
    summary="KRX KIND 공시 배치 수집/적재",
    description="종목 기준으로 정기/수시 공시 문서를 수집·처리·적재합니다.",
)
def run_kind_disclosures(req: KindBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    """KRX KIND 공시 배치 실행."""
    return ingestor.ingest_kind_disclosures(db=db, ticker_or_name=req.ticker_or_name, max_items=req.max_items)


@router.post(
    "/policy-briefing",
    response_model=BatchIngestionResponse,
    summary="정책브리핑 배치 수집/적재",
    description="청와대/국무회의/부처브리핑/정책뉴스 자료를 수집·처리·적재합니다.",
)
def run_policy_briefing(req: GenericBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    """정책브리핑 배치 실행."""
    return ingestor.ingest_policy_briefing(db=db, max_items=req.max_items)


@router.post(
    "/bok/publications",
    response_model=BatchIngestionResponse,
    summary="한국은행 자료 배치 수집/적재",
    description="간행물/조사연구/지역/국외/업무별정보 자료를 수집·처리·적재합니다.",
)
def run_bok_publications(req: GenericBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    """한국은행 자료 배치 실행."""
    return ingestor.ingest_bok_publications(db=db, max_items=req.max_items)

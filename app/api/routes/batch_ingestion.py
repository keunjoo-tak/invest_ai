from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.batch_ingestion import BatchIngestionResponse, GenericBatchRequest, KindBatchRequest, ResearchBatchRequest
from app.services.ingestion.batch_ingestor import BatchIngestor

router = APIRouter(prefix='/batch', tags=['batch-ingestion'])
ingestor = BatchIngestor()


@router.post(
    '/kind/disclosures',
    response_model=BatchIngestionResponse,
    summary='KIND 공시 배치 수집',
    description='종목 기준 KIND 공시 문서를 수집하고 정제한 뒤 external_document 테이블에 적재합니다.',
)
def run_kind_disclosures(req: KindBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    return ingestor.ingest_kind_disclosures(db=db, ticker_or_name=req.ticker_or_name, max_items=req.max_items)


@router.post(
    '/research/public-reports',
    response_model=BatchIngestionResponse,
    summary='공개 리서치 문서 배치 수집',
    description='국내 증권사·은행 연구소와 글로벌 공개형 하우스 리포트를 수집하고 정제한 뒤 적재합니다.',
)
def run_public_research_reports(req: ResearchBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    return ingestor.ingest_public_research_reports(db=db, max_items=req.max_items, group=req.group)


@router.post(
    '/policy-briefing',
    response_model=BatchIngestionResponse,
    summary='정책브리핑 배치 수집',
    description='대통령실, 국무회의, 부처 브리핑, 정책뉴스 문서를 수집하고 정제한 뒤 적재합니다.',
)
def run_policy_briefing(req: GenericBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    return ingestor.ingest_policy_briefing(db=db, max_items=req.max_items)


@router.post(
    '/bok/publications',
    response_model=BatchIngestionResponse,
    summary='한국은행 자료 배치 수집',
    description='한국은행 간행물, 조사연구, 지역연구자료, 국외사무소자료, 업무별 정보를 수집하고 적재합니다.',
)
def run_bok_publications(req: GenericBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    return ingestor.ingest_bok_publications(db=db, max_items=req.max_items)


@router.post(
    '/global-macro-briefings',
    response_model=BatchIngestionResponse,
    summary='미국·글로벌 거시 브리핑 배치',
    description='OECD, FRED, BLS, BEA, Fiscal Data를 기반으로 거시 브리핑 문서를 생성하고 적재합니다.',
)
def run_global_macro_briefings(req: GenericBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    return ingestor.ingest_global_macro_briefings(db=db, max_items=req.max_items)


@router.post(
    '/international-macro-briefings',
    response_model=BatchIngestionResponse,
    summary='국제 거시 브리핑 배치',
    description='World Bank, IMF, Eurostat 데이터를 기반으로 국제 거시 브리핑 문서를 생성하고 적재합니다.',
)
def run_international_macro_briefings(req: GenericBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    return ingestor.ingest_international_macro_briefings(db=db, max_items=req.max_items)


@router.post(
    '/global-event-calendars',
    response_model=BatchIngestionResponse,
    summary='공식 이벤트 캘린더 배치',
    description='주요 기관의 공식 이벤트 일정을 수집해 release_calendar_event 테이블에 적재합니다.',
)
def run_global_event_calendars(req: GenericBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    return ingestor.ingest_global_event_calendars(db=db, max_items=req.max_items)


@router.post(
    '/global-issue-stream',
    response_model=BatchIngestionResponse,
    summary='글로벌 이슈 스트림 배치',
    description='GDELT와 공식 기관 발표 자료를 수집해 글로벌 이슈 스트림 문서로 적재합니다.',
)
def run_global_issue_stream(req: GenericBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    return ingestor.ingest_global_issue_stream(db=db, max_items=req.max_items)


@router.post(
    '/naver/headlines',
    response_model=BatchIngestionResponse,
    summary='네이버 헤드라인 뉴스 배치 수집',
    description='정치, 경제-금융, 경제-증권, 경제-부동산, IT/과학, 세계 섹션의 헤드라인 기사를 수집하고 요약해 적재합니다.',
)
def run_naver_headlines(req: GenericBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    return ingestor.ingest_naver_section_headlines(db=db, max_items=req.max_items)


@router.post(
    '/market-regime-snapshot',
    response_model=BatchIngestionResponse,
    summary='시장 체제 스냅샷 생성',
    description='시장 체제 데이터를 미리 계산해 product_snapshot_cache에 저장하고, 웹 첫 호출 속도를 단축합니다.',
)
def run_market_regime_snapshot(req: GenericBatchRequest, db: Session = Depends(get_db)) -> BatchIngestionResponse:
    return ingestor.ingest_market_regime_snapshot(db=db, max_items=req.max_items)

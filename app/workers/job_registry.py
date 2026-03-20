from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.schemas.batch_ingestion import BatchIngestionResponse
from app.services.ingestion.batch_ingestor import BatchIngestor


@dataclass(frozen=True)
class SchedulerJobDefinition:
    """배치 작업 정의."""

    job_id: str
    schedule_hour: int
    schedule_minute: int
    timezone: str
    description: str
    default_max_items: int


JOB_DEFINITIONS: tuple[SchedulerJobDefinition, ...] = (
    SchedulerJobDefinition('public_research_global', 5, 15, 'Asia/Seoul', '글로벌 공개 리서치 문서 배치 수집', 12),
    SchedulerJobDefinition('public_research_domestic', 6, 0, 'Asia/Seoul', '국내 증권사·은행 리서치 문서 배치 수집', 18),
    SchedulerJobDefinition('policy_briefing', 6, 15, 'Asia/Seoul', '정책브리핑 문서 배치 수집', 40),
    SchedulerJobDefinition('bok_publications', 6, 35, 'Asia/Seoul', '한국은행 자료 배치 수집', 40),
    SchedulerJobDefinition('global_macro_briefings', 6, 50, 'Asia/Seoul', '미국·글로벌 거시 브리핑 배치 생성', 20),
    SchedulerJobDefinition('international_macro_briefings', 6, 53, 'Asia/Seoul', '국제 거시 브리핑 배치 생성', 20),
    SchedulerJobDefinition('global_event_calendars', 6, 55, 'Asia/Seoul', '공식 이벤트 캘린더 배치 수집', 80),
    SchedulerJobDefinition('global_issue_stream', 7, 5, 'Asia/Seoul', '글로벌 이슈 스트림 배치 수집', 40),
    SchedulerJobDefinition('naver_headlines', 7, 7, 'Asia/Seoul', '네이버 섹션 헤드라인 배치 수집', 10),
    SchedulerJobDefinition('market_regime_snapshot', 7, 10, 'Asia/Seoul', '시장 체제 스냅샷 생성', 1),
)


def list_scheduler_jobs() -> list[SchedulerJobDefinition]:
    """등록된 배치 작업 목록을 반환한다."""
    return list(JOB_DEFINITIONS)


def get_scheduler_job_definition(job_id: str) -> SchedulerJobDefinition:
    """작업 ID로 배치 정의를 조회한다."""
    for item in JOB_DEFINITIONS:
        if item.job_id == job_id:
            return item
    raise KeyError(job_id)


def run_scheduler_job(job_id: str, db: Session, max_items_override: int | None = None) -> BatchIngestionResponse:
    """작업 ID에 해당하는 배치 작업을 실행한다."""
    ingestor = BatchIngestor()
    definition = get_scheduler_job_definition(job_id)
    max_items = max_items_override or definition.default_max_items

    if job_id == 'public_research_global':
        return ingestor.ingest_public_research_reports(db=db, max_items=max_items, group='global')
    if job_id == 'public_research_domestic':
        return ingestor.ingest_public_research_reports(db=db, max_items=max_items, group='domestic')
    if job_id == 'policy_briefing':
        return ingestor.ingest_policy_briefing(db=db, max_items=max_items)
    if job_id == 'bok_publications':
        return ingestor.ingest_bok_publications(db=db, max_items=max_items)
    if job_id == 'global_macro_briefings':
        return ingestor.ingest_global_macro_briefings(db=db, max_items=max_items)
    if job_id == 'international_macro_briefings':
        return ingestor.ingest_international_macro_briefings(db=db, max_items=max_items)
    if job_id == 'global_event_calendars':
        return ingestor.ingest_global_event_calendars(db=db, max_items=max_items)
    if job_id == 'global_issue_stream':
        return ingestor.ingest_global_issue_stream(db=db, max_items=max_items)
    if job_id == 'naver_headlines':
        return ingestor.ingest_naver_section_headlines(db=db, max_items=max_items)
    if job_id == 'market_regime_snapshot':
        return ingestor.ingest_market_regime_snapshot(db=db, max_items=max_items)

    raise KeyError(job_id)

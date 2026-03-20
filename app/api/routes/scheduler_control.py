from __future__ import annotations

from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.batch_ingestion import BatchIngestionResponse
from app.workers.job_registry import list_scheduler_jobs, run_scheduler_job
from app.core.config import get_settings
from pydantic import BaseModel, Field

router = APIRouter(prefix='/internal/scheduler', tags=['cloud-scheduler'])


class SchedulerTriggerRequest(BaseModel):
    """Cloud Scheduler 수동 트리거 요청 본문."""

    max_items: int | None = Field(default=None, ge=1, le=500, description='기본 설정을 덮어쓸 최대 처리 건수')


class SchedulerJobItem(BaseModel):
    """등록된 스케줄 작업 정보."""

    job_id: str
    schedule_hour: int
    schedule_minute: int
    timezone: str
    description: str
    default_max_items: int


class SchedulerTriggerResponse(BaseModel):
    """스케줄 작업 실행 응답."""

    job_id: str
    result: BatchIngestionResponse



def _verify_scheduler_secret(x_investai_scheduler_key: str | None = Header(default=None)) -> None:
    """Cloud Scheduler 전용 공유 비밀을 검증한다."""
    settings = get_settings()
    secret = settings.scheduler_shared_secret
    if not secret:
        raise HTTPException(status_code=503, detail='스케줄러 공유 비밀이 설정되지 않았습니다.')
    if not x_investai_scheduler_key or not compare_digest(x_investai_scheduler_key, secret):
        raise HTTPException(status_code=401, detail='유효하지 않은 스케줄러 호출입니다.')


@router.get(
    '/jobs',
    response_model=list[SchedulerJobItem],
    summary='Cloud Scheduler 작업 목록',
    description='Cloud Scheduler 또는 로컬 배치 스케줄러가 공통으로 사용하는 작업 정의를 조회합니다.',
)
def get_scheduler_jobs(_: None = Depends(_verify_scheduler_secret)) -> list[SchedulerJobItem]:
    return [SchedulerJobItem(**job.__dict__) for job in list_scheduler_jobs()]


@router.post(
    '/jobs/{job_id}',
    response_model=SchedulerTriggerResponse,
    summary='Cloud Scheduler 배치 작업 실행',
    description='Cloud Scheduler가 공유 비밀 헤더를 포함해 호출하는 전용 배치 실행 엔드포인트입니다.',
)
def trigger_scheduler_job(job_id: str, payload: SchedulerTriggerRequest, db: Session = Depends(get_db), _: None = Depends(_verify_scheduler_secret)) -> SchedulerTriggerResponse:
    try:
        result = run_scheduler_job(job_id=job_id, db=db, max_items_override=payload.max_items)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f'지원하지 않는 작업입니다: {job_id}') from exc
    return SchedulerTriggerResponse(job_id=job_id, result=result)

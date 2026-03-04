from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analysis import AnalyzeTickerRequest, AnalyzeTickerResponse
from app.services.pipeline.orchestrator import AnalysisPipeline

router = APIRouter(tags=["analysis"])
pipeline = AnalysisPipeline()


@router.post(
    "/analyze/ticker",
    response_model=AnalyzeTickerResponse,
    summary="종목 분석 및 신호 생성",
    description=(
        "종목(티커/종목명) 기준으로 외부 데이터를 수집(KIS/NAVER/DART)하고, "
        "피처 생성 -> 신호 평가 -> LLM 설명 생성 -> 알림 발송 후보 판단까지 수행합니다."
    ),
)
async def analyze_ticker(req: AnalyzeTickerRequest, db: Session = Depends(get_db)) -> AnalyzeTickerResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    return await pipeline.run(db, req)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analysis import AnalyzeTickerRequest, AnalyzeTickerResponse
from app.services.pipeline.orchestrator import AnalysisPipeline

router = APIRouter(tags=["analysis"])
pipeline = AnalysisPipeline()


@router.post("/analyze/ticker", response_model=AnalyzeTickerResponse)
async def analyze_ticker(req: AnalyzeTickerRequest, db: Session = Depends(get_db)) -> AnalyzeTickerResponse:
    return await pipeline.run(db, req)

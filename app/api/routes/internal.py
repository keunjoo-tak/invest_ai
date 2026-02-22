from datetime import date

from fastapi import APIRouter

from app.services.ingestion.providers import SourceProviderClient

router = APIRouter(prefix="/internal", tags=["internal"])
providers = SourceProviderClient()


@router.post("/jobs/recompute-features")
def recompute_features() -> dict:
    # 운영 확장 시 큐 워커 트리거로 대체
    sample = providers.fetch_macro(date.today())
    return {"status": "queued", "macro_rows": len(sample)}

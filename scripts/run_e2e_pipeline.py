from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.base import Base
from app.schemas.analysis import AnalyzeTickerRequest
from app.services.pipeline.orchestrator import AnalysisPipeline


async def main() -> int:
    database_url = os.getenv("DATABASE_URL", "sqlite:///investai_local.db")
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    req = AnalyzeTickerRequest(
        ticker_or_name=os.getenv("E2E_TICKER", "005930"),
        as_of_date=date.today(),
        lookback_days=365,
        notify=True,
        channels=["telegram"],
    )
    with Session() as db:
        result = await AnalysisPipeline().run(db, req)
    print(
        {
            "ticker": result.ticker,
            "signal_type": result.signal.signal_type,
            "score": result.signal.score,
            "quality_score": result.signal.quality_score,
            "alert_should_send": result.alert.should_send,
            "telegram_result": result.alert.channel_results.get("telegram"),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

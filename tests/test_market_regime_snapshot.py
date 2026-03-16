import asyncio
from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.schemas.intelligence import MarketPulseOverviewResponse
from app.services.intelligence.decision_products import DecisionProductService


def test_market_regime_snapshot_roundtrip(monkeypatch) -> None:
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    service = DecisionProductService()
    target_date = date(2026, 3, 13)

    def fake_overview(as_of_date=None):
        return MarketPulseOverviewResponse(
            as_of_date=target_date,
            generated_at_utc=datetime.now(timezone.utc),
            market_one_line='현재 시장은 위험선호 구간입니다.',
            regime='위험선호',
            regime_score=8.5,
            strong_sectors=[{'sector': '반도체', 'score': 77.0}],
            weak_sectors=[{'sector': '유틸리티', 'score': 28.0}],
            macro_summary=[],
            strategy_hints=['강한 섹터를 우선 확인합니다.'],
            representative_symbols=[{'ticker': '005930', 'ret20_pct': 9.1}],
        )

    monkeypatch.setattr(service.market, 'overview', fake_overview)

    with SessionLocal() as db:
        refreshed = service.refresh_market_regime_snapshot(db, target_date)
        service._cache.clear()
        loaded = asyncio.run(service.build_market_regime(as_of_date=target_date, db=db))

    assert refreshed.pipeline_status['response_source'] == 'batch_snapshot'
    assert refreshed.pipeline_status['snapshot_ready'] is True
    assert loaded.pipeline_status['response_source'] == 'batch_snapshot'
    assert loaded.regime == '위험선호'

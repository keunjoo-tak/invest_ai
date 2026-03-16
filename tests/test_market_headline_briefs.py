from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import ExternalDocument
from app.services.intelligence import market_pulse
from app.services.intelligence.market_pulse import MarketPulseEngine


UTC = timezone.utc


def _price_rows(start_price: float) -> list[dict]:
    rows = []
    d0 = date(2026, 2, 10)
    price = start_price
    for i in range(40):
        trade_date = d0 + timedelta(days=i)
        if trade_date.weekday() >= 5:
            continue
        price *= 1.01
        rows.append({'trade_date': trade_date, 'close': round(price, 2)})
    return rows


def test_market_regime_includes_headline_news_briefs(monkeypatch) -> None:
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    target_date = date(2026, 3, 16)

    monkeypatch.setattr(market_pulse, 'SessionLocal', SessionLocal)

    pulse = MarketPulseEngine()
    monkeypatch.setattr(pulse.providers, '_fallback_catalog', lambda: [{'ticker': '005930'}, {'ticker': '000660'}])
    monkeypatch.setattr(pulse.providers, 'fetch_price_daily', lambda ticker, as_of_date, lookback_days: _price_rows(100 if ticker == '005930' else 120))
    monkeypatch.setattr(pulse.providers, 'fetch_macro', lambda as_of_date: [])
    monkeypatch.setattr(pulse.providers, 'resolve_instrument', lambda ticker: SimpleNamespace(name_kr='삼성전자' if ticker == '005930' else 'SK하이닉스'))

    with SessionLocal() as db:
        db.add(ExternalDocument(
            source_system='NAVER_HEADLINE_NEWS',
            source_id='S40',
            source_doc_id='politics_001_1',
            category='naver_headline_politics',
            title='정치 헤드라인',
            url='https://n.news.naver.com/mnews/article/001/0000000001',
            publish_time_utc=datetime(2026, 3, 15, 3, 0, tzinfo=UTC),
            ticker=None,
            instrument_name=None,
            sector=None,
            event_type='macro_policy',
            content_text='정책과 외교 이슈가 위험선호에 영향을 주는 내용',
            summary_json={'summary': '정치 이슈가 정책 기대와 규제 우려를 함께 자극했습니다.'},
            metadata_json={
                'section_key': 'politics',
                'section_label': '정치',
                'scores': {'sentiment_score': 0.12, 'impact_score': 0.42, 'freshness_score': 0.88},
            },
            local_doc_dir='archive/test',
            fingerprint='fp-headline-1',
        ))
        db.commit()

    overview = pulse.overview(target_date)

    assert overview.headline_news_briefs
    assert overview.headline_news_briefs[0]['section_label'] == '정치'
    assert '위험' in overview.headline_news_briefs[0]['market_impact'] or '시장' in overview.headline_news_briefs[0]['market_impact']

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.services.intelligence.decision_products import DecisionProductService
from app.schemas.decision_products import WatchlistSubscriptionRequest


def test_watchlist_subscription_lifecycle() -> None:
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    service = DecisionProductService()

    with SessionLocal() as db:
        created = service.add_watchlist_subscription(
            db,
            WatchlistSubscriptionRequest(ticker_or_name='005930', channel='telegram', notes='event watch'),
        )
        listed = service.list_watchlist_subscriptions(db)
        deleted = service.delete_watchlist_subscription(db, '005930', 'telegram')
        listed_after = service.list_watchlist_subscriptions(db)

    assert created.ticker == '005930'
    assert len(listed) == 1
    assert deleted.deleted is True
    assert listed_after == []

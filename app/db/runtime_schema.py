from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_runtime_schema(engine: Engine) -> None:
    """기존 DB에 필요한 런타임 컬럼/테이블을 보강한다."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        if 'macro_snapshot' in tables:
            cols = {col['name'] for col in inspector.get_columns('macro_snapshot')}
            alter_map = {
                'observation_date': 'ALTER TABLE macro_snapshot ADD COLUMN IF NOT EXISTS observation_date DATE',
                'release_at': 'ALTER TABLE macro_snapshot ADD COLUMN IF NOT EXISTS release_at TIMESTAMPTZ',
                'available_at': 'ALTER TABLE macro_snapshot ADD COLUMN IF NOT EXISTS available_at TIMESTAMPTZ',
                'ingested_at': 'ALTER TABLE macro_snapshot ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMPTZ',
                'revision': 'ALTER TABLE macro_snapshot ADD COLUMN IF NOT EXISTS revision VARCHAR(40)',
                'source_tz': 'ALTER TABLE macro_snapshot ADD COLUMN IF NOT EXISTS source_tz VARCHAR(40)',
                'source_meta_json': "ALTER TABLE macro_snapshot ADD COLUMN IF NOT EXISTS source_meta_json JSON DEFAULT '{}'::json",
            }
            for name, sql in alter_map.items():
                if name not in cols:
                    conn.execute(text(sql))

        if 'watchlist_subscription' not in tables:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS watchlist_subscription (
                    id SERIAL PRIMARY KEY,
                    instrument_id INTEGER NOT NULL REFERENCES instrument_master(id),
                    channel VARCHAR(20) NOT NULL DEFAULT 'telegram',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    notes VARCHAR(500),
                    created_at_utc TIMESTAMPTZ DEFAULT now(),
                    updated_at_utc TIMESTAMPTZ DEFAULT now(),
                    CONSTRAINT uq_watchlist_subscription_instrument_channel UNIQUE (instrument_id, channel)
                )
            """))

        if 'product_snapshot_cache' not in tables:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS product_snapshot_cache (
                    id SERIAL PRIMARY KEY,
                    product_type VARCHAR(60) NOT NULL,
                    snapshot_key VARCHAR(120) NOT NULL,
                    as_of_date DATE NOT NULL,
                    snapshot_json JSON NOT NULL DEFAULT '{}'::json,
                    meta_json JSON NOT NULL DEFAULT '{}'::json,
                    expires_at_utc TIMESTAMPTZ,
                    created_at_utc TIMESTAMPTZ DEFAULT now(),
                    updated_at_utc TIMESTAMPTZ DEFAULT now(),
                    CONSTRAINT uq_product_snapshot_cache_product_key UNIQUE (product_type, snapshot_key)
                )
            """))

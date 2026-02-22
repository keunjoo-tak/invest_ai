CREATE TABLE IF NOT EXISTS instrument_master (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(30) NOT NULL UNIQUE,
  name_kr VARCHAR(120) NOT NULL,
  market VARCHAR(20) NOT NULL DEFAULT 'KR',
  sector VARCHAR(120),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS price_daily (
  id BIGSERIAL PRIMARY KEY,
  instrument_id BIGINT NOT NULL REFERENCES instrument_master(id),
  trade_date DATE NOT NULL,
  open DOUBLE PRECISION NOT NULL,
  high DOUBLE PRECISION NOT NULL,
  low DOUBLE PRECISION NOT NULL,
  close DOUBLE PRECISION NOT NULL,
  volume BIGINT NOT NULL,
  source VARCHAR(30) NOT NULL DEFAULT 'KIS',
  UNIQUE (instrument_id, trade_date)
);

CREATE TABLE IF NOT EXISTS news_parsed (
  id BIGSERIAL PRIMARY KEY,
  instrument_id BIGINT NOT NULL REFERENCES instrument_master(id),
  title VARCHAR(300) NOT NULL,
  url VARCHAR(1000) NOT NULL UNIQUE,
  publish_time_utc TIMESTAMPTZ NOT NULL,
  sentiment_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  impact_scope VARCHAR(40) NOT NULL DEFAULT 'single_stock',
  llm_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS disclosure_parsed (
  id BIGSERIAL PRIMARY KEY,
  instrument_id BIGINT NOT NULL REFERENCES instrument_master(id),
  source_disclosure_id VARCHAR(80) NOT NULL UNIQUE,
  title VARCHAR(300) NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  publish_time_utc TIMESTAMPTZ NOT NULL,
  impact_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  llm_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS macro_snapshot (
  id BIGSERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL,
  country VARCHAR(10) NOT NULL DEFAULT 'KR',
  indicator_name VARCHAR(100) NOT NULL,
  actual DOUBLE PRECISION,
  consensus DOUBLE PRECISION,
  surprise_std DOUBLE PRECISION,
  directional_interpretation VARCHAR(120)
);

CREATE TABLE IF NOT EXISTS signal_decision (
  id BIGSERIAL PRIMARY KEY,
  instrument_id BIGINT NOT NULL REFERENCES instrument_master(id),
  as_of_time_utc TIMESTAMPTZ NOT NULL,
  signal_type VARCHAR(40) NOT NULL,
  direction VARCHAR(20) NOT NULL,
  score DOUBLE PRECISION NOT NULL,
  quality_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  reasons_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  risk_flags_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS alert_history (
  id BIGSERIAL PRIMARY KEY,
  instrument_id BIGINT NOT NULL REFERENCES instrument_master(id),
  signal_direction VARCHAR(20) NOT NULL,
  reason_fingerprint VARCHAR(120) NOT NULL,
  channel VARCHAR(20) NOT NULL DEFAULT 'telegram',
  payload_text TEXT NOT NULL,
  sent_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status VARCHAR(20) NOT NULL DEFAULT 'sent'
);

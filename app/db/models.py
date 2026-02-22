from datetime import datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Instrument(Base):
    __tablename__ = "instrument_master"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name_kr: Mapped[str] = mapped_column(String(120))
    market: Mapped[str] = mapped_column(String(20), default="KR")
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceDaily(Base):
    __tablename__ = "price_daily"
    __table_args__ = (UniqueConstraint("instrument_id", "trade_date", name="uq_price_daily_instrument_trade_date"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument_master.id"), index=True)
    trade_date: Mapped[datetime] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30), default="KIS")


class NewsParsed(Base):
    __tablename__ = "news_parsed"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument_master.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    publish_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    impact_scope: Mapped[str] = mapped_column(String(40), default="single_stock")
    llm_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class DisclosureParsed(Base):
    __tablename__ = "disclosure_parsed"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument_master.id"), index=True)
    source_disclosure_id: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    event_type: Mapped[str] = mapped_column(String(80))
    publish_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    impact_score: Mapped[float] = mapped_column(Float, default=0.0)
    llm_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class MacroSnapshot(Base):
    __tablename__ = "macro_snapshot"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    as_of_date: Mapped[datetime] = mapped_column(Date, index=True)
    country: Mapped[str] = mapped_column(String(10), default="KR")
    indicator_name: Mapped[str] = mapped_column(String(100))
    actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    consensus: Mapped[float | None] = mapped_column(Float, nullable=True)
    surprise_std: Mapped[float | None] = mapped_column(Float, nullable=True)
    directional_interpretation: Mapped[str | None] = mapped_column(String(120), nullable=True)


class SignalDecision(Base):
    __tablename__ = "signal_decision"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument_master.id"), index=True)
    as_of_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    signal_type: Mapped[str] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    reasons_json: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_flags_json: Mapped[dict] = mapped_column(JSON, default=dict)


class AlertHistory(Base):
    __tablename__ = "alert_history"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument_master.id"), index=True)
    signal_direction: Mapped[str] = mapped_column(String(20))
    reason_fingerprint: Mapped[str] = mapped_column(String(120), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="telegram")
    payload_text: Mapped[str] = mapped_column(Text)
    sent_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="sent")

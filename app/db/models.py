from datetime import datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Instrument(Base):
    """종목 마스터."""

    __tablename__ = 'instrument_master'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='종목 마스터 PK')
    ticker: Mapped[str] = mapped_column(String(30), unique=True, index=True, comment='종목 티커/코드')
    name_kr: Mapped[str] = mapped_column(String(120), comment='종목명')
    market: Mapped[str] = mapped_column(String(20), default='KR', comment='시장 구분')
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True, comment='섹터명')
    is_active: Mapped[bool] = mapped_column(default=True, comment='활성 여부')
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment='생성 시각(UTC)')


class PriceDaily(Base):
    """일봉 가격."""

    __tablename__ = 'price_daily'
    __table_args__ = (UniqueConstraint('instrument_id', 'trade_date', name='uq_price_daily_instrument_trade_date'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='일봉 PK')
    instrument_id: Mapped[int] = mapped_column(ForeignKey('instrument_master.id'), index=True, comment='종목 FK')
    trade_date: Mapped[datetime] = mapped_column(Date, comment='거래일')
    open: Mapped[float] = mapped_column(Float, comment='시가')
    high: Mapped[float] = mapped_column(Float, comment='고가')
    low: Mapped[float] = mapped_column(Float, comment='저가')
    close: Mapped[float] = mapped_column(Float, comment='종가')
    volume: Mapped[int] = mapped_column(Integer, comment='거래량')
    source: Mapped[str] = mapped_column(String(30), default='KIS', comment='데이터 소스')


class NewsParsed(Base):
    """뉴스 파싱 결과."""

    __tablename__ = 'news_parsed'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='뉴스 PK')
    instrument_id: Mapped[int] = mapped_column(ForeignKey('instrument_master.id'), index=True, comment='종목 FK')
    title: Mapped[str] = mapped_column(String(300), comment='뉴스 제목')
    url: Mapped[str] = mapped_column(String(1000), unique=True, comment='뉴스 원문 URL')
    publish_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment='발행 시각(UTC)')
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0, comment='감성 점수')
    impact_scope: Mapped[str] = mapped_column(String(40), default='single_stock', comment='영향 범위')
    llm_payload: Mapped[dict] = mapped_column(JSON, default=dict, comment='LLM 부가정보')


class DisclosureParsed(Base):
    """공시 파싱 결과."""

    __tablename__ = 'disclosure_parsed'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='공시 PK')
    instrument_id: Mapped[int] = mapped_column(ForeignKey('instrument_master.id'), index=True, comment='종목 FK')
    source_disclosure_id: Mapped[str] = mapped_column(String(80), unique=True, comment='원천 공시 ID')
    title: Mapped[str] = mapped_column(String(300), comment='공시 제목')
    event_type: Mapped[str] = mapped_column(String(80), comment='공시 이벤트 유형')
    publish_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment='게시 시각(UTC)')
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, comment='영향 점수')
    llm_payload: Mapped[dict] = mapped_column(JSON, default=dict, comment='LLM 부가정보')


class MacroSnapshot(Base):
    """거시 스냅샷."""

    __tablename__ = 'macro_snapshot'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='거시 PK')
    as_of_date: Mapped[datetime] = mapped_column(Date, index=True, comment='기준일')
    observation_date: Mapped[datetime | None] = mapped_column(Date, nullable=True, comment='관측 기준일')
    release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment='공식 발표 시각(UTC)')
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment='실제 사용 가능 시각(UTC)')
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment='수집 시각(UTC)')
    revision: Mapped[str | None] = mapped_column(String(40), nullable=True, comment='빈티지/리비전')
    source_tz: Mapped[str | None] = mapped_column(String(40), nullable=True, comment='원천 시간대')
    country: Mapped[str] = mapped_column(String(10), default='KR', comment='국가 코드')
    indicator_name: Mapped[str] = mapped_column(String(100), comment='지표명')
    actual: Mapped[float | None] = mapped_column(Float, nullable=True, comment='실제값')
    consensus: Mapped[float | None] = mapped_column(Float, nullable=True, comment='비교 기준값')
    surprise_std: Mapped[float | None] = mapped_column(Float, nullable=True, comment='정규화 surprise')
    directional_interpretation: Mapped[str | None] = mapped_column(String(120), nullable=True, comment='방향 해석')
    source_meta_json: Mapped[dict] = mapped_column(JSON, default=dict, comment='원천 메타데이터')


class ReleaseCalendarEvent(Base):
    """공식 이벤트 캘린더."""

    __tablename__ = 'release_calendar_event'
    __table_args__ = (UniqueConstraint('source_system', 'event_code', name='uq_release_calendar_event_source_code'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='이벤트 PK')
    source_system: Mapped[str] = mapped_column(String(40), index=True, comment='소스 시스템')
    event_code: Mapped[str] = mapped_column(String(160), comment='원천 이벤트 코드')
    category: Mapped[str] = mapped_column(String(60), comment='이벤트 카테고리')
    title: Mapped[str] = mapped_column(String(500), comment='이벤트 제목')
    country: Mapped[str] = mapped_column(String(10), default='GLOBAL', comment='국가 코드')
    source_tz: Mapped[str | None] = mapped_column(String(40), nullable=True, comment='원천 시간대')
    scheduled_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, comment='예정 시각(UTC)')
    release_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment='발표 시각(UTC)')
    available_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment='사용 가능 시각(UTC)')
    status: Mapped[str] = mapped_column(String(20), default='scheduled', comment='상태')
    url: Mapped[str | None] = mapped_column(String(1200), nullable=True, comment='원문 URL')
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, comment='메타데이터')
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment='생성 시각(UTC)')


class SignalDecision(Base):
    """신호 평가 결과."""

    __tablename__ = 'signal_decision'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='신호 PK')
    instrument_id: Mapped[int] = mapped_column(ForeignKey('instrument_master.id'), index=True, comment='종목 FK')
    as_of_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, comment='생성 시각(UTC)')
    signal_type: Mapped[str] = mapped_column(String(40), comment='신호 유형')
    direction: Mapped[str] = mapped_column(String(20), comment='방향')
    score: Mapped[float] = mapped_column(Float, comment='점수')
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, comment='품질 점수')
    reasons_json: Mapped[dict] = mapped_column(JSON, default=dict, comment='사유 JSON')
    risk_flags_json: Mapped[dict] = mapped_column(JSON, default=dict, comment='리스크 JSON')


class AlertHistory(Base):
    """알림 발송 이력."""

    __tablename__ = 'alert_history'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='알림 PK')
    instrument_id: Mapped[int] = mapped_column(ForeignKey('instrument_master.id'), index=True, comment='종목 FK')
    signal_direction: Mapped[str] = mapped_column(String(20), comment='신호 방향')
    reason_fingerprint: Mapped[str] = mapped_column(String(120), index=True, comment='중복 방지 해시')
    channel: Mapped[str] = mapped_column(String(20), default='telegram', comment='채널')
    payload_text: Mapped[str] = mapped_column(Text, comment='발송 본문')
    sent_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment='발송 시각(UTC)')
    status: Mapped[str] = mapped_column(String(20), default='sent', comment='상태')


class WatchlistSubscription(Base):
    """저장형 워치리스트 구독."""

    __tablename__ = 'watchlist_subscription'
    __table_args__ = (UniqueConstraint('instrument_id', 'channel', name='uq_watchlist_subscription_instrument_channel'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='워치리스트 구독 PK')
    instrument_id: Mapped[int] = mapped_column(ForeignKey('instrument_master.id'), index=True, comment='종목 FK')
    channel: Mapped[str] = mapped_column(String(20), default='telegram', comment='알림 채널')
    is_active: Mapped[bool] = mapped_column(default=True, comment='활성 여부')
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True, comment='관찰 메모')
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment='생성 시각(UTC)')
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment='수정 시각(UTC)')


class ExternalDocument(Base):
    """외부 문서 아카이브."""

    __tablename__ = 'external_document'
    __table_args__ = (
        UniqueConstraint('fingerprint', name='uq_external_document_fingerprint'),
        UniqueConstraint('source_system', 'source_doc_id', name='uq_external_document_source_doc'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='문서 PK')
    source_system: Mapped[str] = mapped_column(String(40), index=True, comment='소스 시스템')
    source_id: Mapped[str] = mapped_column(String(20), index=True, comment='소스 ID')
    source_doc_id: Mapped[str] = mapped_column(String(120), comment='원천 문서 ID')
    category: Mapped[str] = mapped_column(String(80), index=True, comment='카테고리')
    title: Mapped[str] = mapped_column(String(500), comment='제목')
    url: Mapped[str] = mapped_column(String(1200), comment='원문 URL')
    publish_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment='게시 시각(UTC)')
    ticker: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True, comment='관련 종목')
    instrument_name: Mapped[str | None] = mapped_column(String(120), nullable=True, comment='관련 종목명')
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True, comment='관련 섹터')
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True, comment='이벤트 유형')
    content_text: Mapped[str] = mapped_column(Text, comment='정제 본문')
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, comment='요약 JSON')
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, comment='메타 JSON')
    local_doc_dir: Mapped[str | None] = mapped_column(String(1200), nullable=True, comment='로컬 저장 경로')
    fingerprint: Mapped[str] = mapped_column(String(64), index=True, comment='중복 해시')
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment='적재 시각(UTC)')


class ProductSnapshotCache(Base):
    """사용자 제품 스냅샷 캐시."""

    __tablename__ = 'product_snapshot_cache'
    __table_args__ = (UniqueConstraint('product_type', 'snapshot_key', name='uq_product_snapshot_cache_product_key'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='스냅샷 PK')
    product_type: Mapped[str] = mapped_column(String(60), index=True, comment='제품 유형')
    snapshot_key: Mapped[str] = mapped_column(String(120), index=True, comment='스냅샷 키')
    as_of_date: Mapped[datetime] = mapped_column(Date, index=True, comment='기준일')
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict, comment='스냅샷 데이터 JSON')
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict, comment='메타데이터 JSON')
    expires_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment='만료 시각(UTC)')
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment='생성 시각(UTC)')
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment='수정 시각(UTC)')

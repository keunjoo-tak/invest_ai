from datetime import datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Instrument(Base):
    """종목 마스터."""

    __tablename__ = "instrument_master"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="종목 마스터 PK")
    ticker: Mapped[str] = mapped_column(String(30), unique=True, index=True, comment="종목 티커/코드")
    name_kr: Mapped[str] = mapped_column(String(120), comment="종목 한글명")
    market: Mapped[str] = mapped_column(String(20), default="KR", comment="시장 구분(KR/US 등)")
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True, comment="섹터명")
    is_active: Mapped[bool] = mapped_column(default=True, comment="활성 종목 여부")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="생성 시각(UTC)")


class PriceDaily(Base):
    """일봉 시세."""

    __tablename__ = "price_daily"
    __table_args__ = (UniqueConstraint("instrument_id", "trade_date", name="uq_price_daily_instrument_trade_date"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="일봉 데이터 PK")
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument_master.id"), index=True, comment="종목 마스터 FK")
    trade_date: Mapped[datetime] = mapped_column(Date, comment="거래일자")
    open: Mapped[float] = mapped_column(Float, comment="시가")
    high: Mapped[float] = mapped_column(Float, comment="고가")
    low: Mapped[float] = mapped_column(Float, comment="저가")
    close: Mapped[float] = mapped_column(Float, comment="종가")
    volume: Mapped[int] = mapped_column(Integer, comment="거래량")
    source: Mapped[str] = mapped_column(String(30), default="KIS", comment="데이터 소스(KIS 등)")


class NewsParsed(Base):
    """뉴스 파싱 결과."""

    __tablename__ = "news_parsed"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="뉴스 데이터 PK")
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument_master.id"), index=True, comment="종목 마스터 FK")
    title: Mapped[str] = mapped_column(String(300), comment="뉴스 제목")
    url: Mapped[str] = mapped_column(String(1000), unique=True, comment="뉴스 원문 URL")
    publish_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="뉴스 발행 시각(UTC)")
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0, comment="뉴스 감성 점수")
    impact_scope: Mapped[str] = mapped_column(String(40), default="single_stock", comment="영향 범위(single_stock/sector/macro)")
    llm_payload: Mapped[dict] = mapped_column(JSON, default=dict, comment="LLM 요약/원문 발췌/부가 메타")


class DisclosureParsed(Base):
    """공시 파싱 결과."""

    __tablename__ = "disclosure_parsed"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="공시 데이터 PK")
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument_master.id"), index=True, comment="종목 마스터 FK")
    source_disclosure_id: Mapped[str] = mapped_column(String(80), unique=True, comment="소스 공시 고유 ID")
    title: Mapped[str] = mapped_column(String(300), comment="공시 제목")
    event_type: Mapped[str] = mapped_column(String(80), comment="공시 이벤트 유형")
    publish_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="공시 게시 시각(UTC)")
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, comment="공시 영향도 점수")
    llm_payload: Mapped[dict] = mapped_column(JSON, default=dict, comment="LLM 요약/원문 발췌/부가 메타")


class MacroSnapshot(Base):
    """거시 지표 스냅샷."""

    __tablename__ = "macro_snapshot"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="거시 스냅샷 PK")
    as_of_date: Mapped[datetime] = mapped_column(Date, index=True, comment="기준일")
    country: Mapped[str] = mapped_column(String(10), default="KR", comment="국가 코드")
    indicator_name: Mapped[str] = mapped_column(String(100), comment="지표명")
    actual: Mapped[float | None] = mapped_column(Float, nullable=True, comment="실제 발표값")
    consensus: Mapped[float | None] = mapped_column(Float, nullable=True, comment="컨센서스 값")
    surprise_std: Mapped[float | None] = mapped_column(Float, nullable=True, comment="서프라이즈 표준화 값")
    directional_interpretation: Mapped[str | None] = mapped_column(String(120), nullable=True, comment="방향성 해석")


class SignalDecision(Base):
    """신호 판정 결과."""

    __tablename__ = "signal_decision"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="신호 판정 PK")
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument_master.id"), index=True, comment="종목 마스터 FK")
    as_of_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, comment="신호 생성 시각(UTC)")
    signal_type: Mapped[str] = mapped_column(String(40), comment="신호 유형")
    direction: Mapped[str] = mapped_column(String(20), comment="신호 방향")
    score: Mapped[float] = mapped_column(Float, comment="신호 점수")
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, comment="품질 점수")
    reasons_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="신호 근거 JSON")
    risk_flags_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="리스크 플래그 JSON")


class AlertHistory(Base):
    """알림 발송 이력."""

    __tablename__ = "alert_history"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="알림 이력 PK")
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instrument_master.id"), index=True, comment="종목 마스터 FK")
    signal_direction: Mapped[str] = mapped_column(String(20), comment="신호 방향")
    reason_fingerprint: Mapped[str] = mapped_column(String(120), index=True, comment="중복 방지용 근거 해시")
    channel: Mapped[str] = mapped_column(String(20), default="telegram", comment="알림 채널")
    payload_text: Mapped[str] = mapped_column(Text, comment="실제 발송 메시지")
    sent_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="발송 시각(UTC)")
    status: Mapped[str] = mapped_column(String(20), default="sent", comment="발송 상태(sent/skipped/failed 등)")


class ExternalDocument(Base):
    """외부 문서 아카이브/인텔리전스 적재."""

    __tablename__ = "external_document"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_external_document_fingerprint"),
        UniqueConstraint("source_system", "source_doc_id", name="uq_external_document_source_doc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="외부 문서 PK")
    source_system: Mapped[str] = mapped_column(String(40), index=True, comment="문서 시스템(KRX_KIND/POLICY_BRIEFING/BOK_PUBLICATIONS)")
    source_id: Mapped[str] = mapped_column(String(20), index=True, comment="데이터소스 ID(S06/S28/S16 등)")
    source_doc_id: Mapped[str] = mapped_column(String(120), comment="소스 문서 고유 ID")
    category: Mapped[str] = mapped_column(String(80), index=True, comment="문서 카테고리")
    title: Mapped[str] = mapped_column(String(500), comment="문서 제목")
    url: Mapped[str] = mapped_column(String(1200), comment="원문 URL")
    publish_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="문서 게시 시각(UTC)")

    ticker: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True, comment="연결 종목 티커")
    instrument_name: Mapped[str | None] = mapped_column(String(120), nullable=True, comment="연결 종목명")
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True, comment="연결 섹터")
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="이벤트 유형")

    content_text: Mapped[str] = mapped_column(Text, comment="정제된 본문 텍스트")
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="LLM 요약 결과 JSON")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="전처리/점수/엔터티 메타 JSON")

    local_doc_dir: Mapped[str | None] = mapped_column(String(1200), nullable=True, comment="로컬 저장 폴더 경로")
    fingerprint: Mapped[str] = mapped_column(String(64), index=True, comment="중복 제거용 문서 해시")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), comment="적재 시각(UTC)")

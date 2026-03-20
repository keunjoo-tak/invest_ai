from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import ExternalDocument
from app.services.ingestion.research_repair import (
    INSUFFICIENT_RESEARCH_SUMMARY,
    ResearchDocumentRepairService,
)
from app.services.intelligence.market_pulse import MarketPulseEngine

UTC = timezone.utc


def _build_row(work_dir: Path) -> ExternalDocument:
    doc_dir = work_dir / "research_doc"
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "raw.pdf").write_bytes(b"%PDF-1.4 mock")
    (doc_dir / "content.txt").write_text("제목만 저장된 상태", encoding="utf-8")
    return ExternalDocument(
        source_system="PUBLIC_RESEARCH_REPORTS",
        source_id="S41",
        source_doc_id="repair-doc-1",
        category="research_pdf",
        title="삼성전자 업황 점검",
        url="https://example.com/research.pdf",
        publish_time_utc=datetime(2026, 3, 19, 0, 0, tzinfo=UTC),
        ticker="005930",
        instrument_name="삼성전자",
        sector="반도체",
        event_type="research_report",
        content_text="삼성전자 업황 점검",
        summary_json={"summary": INSUFFICIENT_RESEARCH_SUMMARY, "key_points": [], "risk_tags": ["정보 부족"]},
        metadata_json={
            "house_name": "삼성증권",
            "service_targets": ["market_regime", "stock_decision"],
            "access_tier": "PUBLIC_OPEN",
            "redistribution_policy": "DERIVED_ONLY",
            "layout_profile": "samsung_sec_research",
            "market_scope": "KR",
            "feature_confidence": 0.4,
            "house_quality_score": 0.86,
            "research_scores": {
                "freshness_score": 0.9,
                "house_quality_score": 0.86,
                "risk_on_off_score": 0.4,
                "policy_risk_score": 0.1,
                "geopolitical_risk_score": 0.05,
            },
        },
        local_doc_dir=str(doc_dir),
        fingerprint="fp-repair-doc-1",
    )


def test_research_document_repair_rehydrates_short_pdf_content(monkeypatch) -> None:
    work_dir = Path("test_artifacts/research_repair/case_one")
    if work_dir.exists():
        import shutil

        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    restored_text = "삼성전자 HBM 수요 회복과 AI 서버 투자 확대가 실적 개선을 이끌 수 있다는 내용입니다. "
    restored_text += "목표주가 상향과 메모리 업황 개선이 함께 언급되며 수익성 회복 가능성을 제시합니다. " * 8
    monkeypatch.setattr("app.services.ingestion.research_repair.pdf_text_extractor", lambda raw: restored_text)

    with SessionLocal() as db:
        row = _build_row(work_dir)
        db.add(row)
        db.commit()
        db.refresh(row)

        repaired = ResearchDocumentRepairService().ensure_document_ready(db, row)

        assert len(repaired.content_text) > 400
        assert repaired.summary_json["summary"] != INSUFFICIENT_RESEARCH_SUMMARY
        assert "HBM" in repaired.summary_json["summary"]
        assert repaired.metadata_json.get("repair_source") == "local_raw_document"
        assert repaired.metadata_json["research_scores"]["parser_quality_score"] > 0.35


def test_market_pulse_research_briefs_use_repaired_summary(monkeypatch) -> None:
    work_dir = Path("test_artifacts/research_repair/case_two")
    if work_dir.exists():
        import shutil

        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    restored_text = "미국 반도체 투자 확대와 메모리 가격 안정화가 국내 대표 반도체 업종에 우호적이라는 분석입니다. "
    restored_text += "단기 변동성은 남아 있지만 업황 회복 기대가 높아져 시장 체제 판단에도 참고할 수 있습니다. " * 10
    monkeypatch.setattr("app.services.ingestion.research_repair.pdf_text_extractor", lambda raw: restored_text)

    with SessionLocal() as db:
        row = _build_row(work_dir)
        row.source_doc_id = "repair-doc-2"
        row.fingerprint = "fp-repair-doc-2"
        row.summary_json = {"summary": INSUFFICIENT_RESEARCH_SUMMARY}
        row.metadata_json["service_targets"] = ["market_regime"]
        db.add(row)
        db.commit()
        db.refresh(row)

        class _ScalarResult:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                return self

            def all(self):
                return self._rows

        repaired = ResearchDocumentRepairService().ensure_document_ready(db, row)
        monkeypatch.setattr(db, "execute", lambda stmt: _ScalarResult([repaired]))

        engine_obj = MarketPulseEngine()
        monkeypatch.setattr(engine_obj.research_repair, "ensure_document_ready", lambda session, current_row: current_row)
        briefs, _ = engine_obj._research_briefs(db, date(2026, 3, 19))

        assert briefs
        assert briefs[0]["summary"] != INSUFFICIENT_RESEARCH_SUMMARY
        assert "반도체" in briefs[0]["summary"]

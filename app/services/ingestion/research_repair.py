from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ExternalDocument
from app.services.ingestion.preprocessing import (
    docx_text_extractor,
    html_cleaner,
    normalize_text_for_storage,
    pdf_text_extractor,
)
from app.services.ingestion.research_normalizer import normalize_research_document

INSUFFICIENT_RESEARCH_SUMMARY = "제공된 정보가 문서 제목과 출처에 불과하여 내용을 요약할 수 없습니다."
SKIP_SENTENCE_PATTERNS = (
    "\ubcf8 \uc790\ub8cc\ub294",
    "\ubc95\uc801 \ucc45\uc784",
    "\uc99d\ube59 \uc790\ub8cc",
    "\uc0ac\uc6a9\ub420 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4",
    "\ubb34\ub2e8 \uc804\uc7ac",
    "\ubc30\ud3ec\ub97c \uae08\ud569\ub2c8\ub2e4",
    "\ud22c\uc790 \uacb0\uacfc\uc5d0 \ub300\ud55c",
)


INSIGHT_KEYWORDS = (
    "전략",
    "전망",
    "시장",
    "수요",
    "공급",
    "업황",
    "실적",
    "이익",
    "매출",
    "가이던스",
    "목표주가",
    "밸류",
    "리스크",
    "금리",
    "환율",
    "유동성",
    "정책",
    "반도체",
    "소비",
    "투자",
)


class ResearchDocumentRepairService:
    def needs_repair(self, row: ExternalDocument) -> bool:
        text = normalize_text_for_storage(row.content_text or "")
        summary = row.summary_json if isinstance(row.summary_json, dict) else {}
        summary_text = normalize_text_for_storage(str(summary.get("summary") or ""))
        title_text = normalize_text_for_storage(str(row.title or ""))
        summary_is_title = bool(summary_text and title_text) and summary_text == title_text
        summary_is_boilerplate = any(pattern in summary_text for pattern in SKIP_SENTENCE_PATTERNS)
        return len(text) < 400 or not summary_text or summary_text == INSUFFICIENT_RESEARCH_SUMMARY or summary_is_title or summary_is_boilerplate

    def ensure_document_ready(self, db: Session, row: ExternalDocument) -> ExternalDocument:
        if not self.needs_repair(row):
            return row

        repaired_text = self._restore_text(row)
        if len(repaired_text) < 400:
            return row

        summary = self._build_summary(row.title, repaired_text)
        meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        published_at = row.publish_time_utc
        if published_at is not None and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        research_meta = normalize_research_document(
            house_name=str(meta.get("house_name") or row.source_id or row.source_system),
            source_id=str(row.source_id or row.source_system),
            access_tier=str(meta.get("access_tier") or "PUBLIC_OPEN"),
            redistribution_policy=str(meta.get("redistribution_policy") or "DERIVED_ONLY"),
            layout_profile=str(meta.get("layout_profile") or meta.get("profile_key") or "research_generic"),
            market_scope=str(meta.get("market_scope") or "GLOBAL"),
            title=row.title,
            content_text=repaired_text,
            url=row.url,
            published_at_utc=published_at,
            summary=summary,
            prediction_signal=meta.get("prediction_signal") if isinstance(meta.get("prediction_signal"), dict) else {},
            house_quality_score=float(meta.get("house_quality_score") or 0.8),
        )

        merged_meta = dict(meta)
        merged_meta.update(research_meta)
        original_targets = [str(item) for item in list(meta.get("service_targets") or []) if item]
        rebuilt_targets = [str(item) for item in list(research_meta.get("service_targets") or []) if item]
        merged_meta["service_targets"] = list(dict.fromkeys(original_targets + rebuilt_targets)) or rebuilt_targets or original_targets
        merged_meta["repair_source"] = "local_raw_document"
        merged_meta["repair_updated_at_utc"] = datetime.now(UTC).isoformat()

        row.content_text = repaired_text[:180000]
        row.summary_json = summary
        row.metadata_json = merged_meta
        row.category = str(research_meta.get("report_type") or row.category)
        row.ticker = research_meta.get("primary_ticker")
        row.instrument_name = research_meta.get("primary_company")
        row.sector = research_meta.get("primary_sector")
        row.event_type = "research_report"
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _restore_text(self, row: ExternalDocument) -> str:
        candidates: list[str] = []
        current_text = normalize_text_for_storage(row.content_text or "")
        if current_text:
            candidates.append(current_text)

        doc_dir = Path(str(row.local_doc_dir or "")).expanduser()
        if doc_dir.exists():
            content_file = doc_dir / "content.txt"
            if content_file.exists():
                candidates.append(normalize_text_for_storage(content_file.read_text(encoding="utf-8", errors="ignore")))

            for name in ("raw.pdf", "raw.docx", "raw.html", "raw.htm", "raw.bin"):
                raw_path = doc_dir / name
                if not raw_path.exists():
                    continue
                extracted = self._extract_from_raw(raw_path)
                if extracted:
                    candidates.append(extracted)

        best = max((text for text in candidates if text), key=len, default="")
        return normalize_text_for_storage(best)

    def _extract_from_raw(self, raw_path: Path) -> str:
        raw = raw_path.read_bytes()
        suffix = raw_path.suffix.lower()
        if suffix == ".pdf":
            return normalize_text_for_storage(pdf_text_extractor(raw))
        if suffix == ".docx":
            return normalize_text_for_storage(docx_text_extractor(raw))
        if suffix in {".html", ".htm"}:
            return normalize_text_for_storage(html_cleaner(raw.decode("utf-8", errors="ignore")))
        return normalize_text_for_storage(raw.decode("utf-8", errors="ignore"))

    def _build_summary(self, title: str, content_text: str) -> dict[str, Any]:
        return self._build_local_summary(title, content_text)

    def _build_local_summary(self, title: str, content_text: str) -> dict[str, Any]:
        text = normalize_text_for_storage(content_text)
        sentence_candidates = self._sentence_candidates(text)
        summary_sentences = sentence_candidates[:2]
        summary_text = " ".join(summary_sentences).strip() if summary_sentences else text[:320]
        key_points = sentence_candidates[:3]
        risk_tokens = [
            "리스크",
            "둔화",
            "부진",
            "하향",
            "변동성",
            "긴축",
            "지연",
]
        risk_tags = [token for token in risk_tokens if token in text][:3]
        if not risk_tags:
            risk_tags = ["본문 재추출 완료"]
        return {
            "source": "research_repair",
            "title": title,
            "summary": summary_text[:600],
            "key_points": key_points[:3],
            "risk_tags": risk_tags,
        }

    def _sentence_candidates(self, text: str) -> list[str]:
        normalized = text.replace("•", ". ").replace("·", ". ").replace("■", ". ")
        parts = [chunk.strip() for chunk in re.split(r"(?:\.\s+|\n+)", normalized) if chunk.strip()]
        scored: list[tuple[float, int, str]] = []
        seen: set[str] = set()
        for index, part in enumerate(parts):
            candidate = normalize_text_for_storage(part)[:220].strip()
            if len(candidate) < 24 or candidate in seen:
                continue
            if any(pattern in candidate for pattern in SKIP_SENTENCE_PATTERNS):
                continue
            seen.add(candidate)
            low = candidate.lower()
            keyword_hits = sum(1 for token in INSIGHT_KEYWORDS if token in low)
            numeric_bonus = 0.25 if re.search(r"\d", candidate) else 0.0
            score = min(len(candidate) / 180.0, 1.0) + (keyword_hits * 0.7) + numeric_bonus
            scored.append((score, index, candidate))
        if not scored:
            return []
        top_ranked = sorted(scored, key=lambda item: (-item[0], item[1]))[:6]
        ordered = sorted(top_ranked, key=lambda item: item[1])
        return [candidate for _, _, candidate in ordered]

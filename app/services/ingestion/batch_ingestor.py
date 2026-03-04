from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import ExternalDocument
from app.schemas.batch_ingestion import BatchIngestionResponse
from app.services.ingestion.preprocessing import doc_fingerprint, entity_linker, event_classifier, html_cleaner, score_engine
from app.services.ingestion.providers import SourceProviderClient
from app.services.ingestion.raw_archive import RawArchiveManager
from app.services.llm.gemini_client import GeminiClient

UTC = timezone.utc


class BatchIngestor:
    """문서형 데이터 배치 수집/처리/적재 서비스."""

    def __init__(self) -> None:
        self.providers = SourceProviderClient()
        self.archive = RawArchiveManager()
        self.gemini = GeminiClient()

    def _ensure_tables(self, db: Session) -> None:
        """배치 적재에 필요한 테이블을 보장한다."""
        bind = db.get_bind()
        Base.metadata.create_all(bind=bind, tables=[ExternalDocument.__table__])

    def _extract_links(self, base_url: str, html: str, max_items: int) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        seen: set[str] = set()
        for href, label in re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html or ""):
            url = urljoin(base_url, href.strip())
            title = html_cleaner(label)
            if not url.startswith("http"):
                continue
            if len(title) < 3:
                continue
            if url in seen:
                continue
            seen.add(url)
            links.append({"url": url, "title": title[:280]})
            if len(links) >= max_items:
                break
        return links

    def _fetch_page_doc(self, url: str) -> tuple[str, bytes, str]:
        try:
            resp = httpx.get(url, timeout=20.0, follow_redirects=True, headers={"User-Agent": "investai-batch/0.3"})
            if not resp.is_success:
                return "", b"", ".html"
            ctype = (resp.headers.get("content-type") or "").lower()
            if "application/pdf" in ctype:
                return self.providers._pdf_to_text(resp.content), resp.content, ".pdf"
            return html_cleaner(resp.text)[:120000], resp.content, ".html"
        except Exception:
            return "", b"", ".html"

    def _upsert_document(self, db: Session, payload: dict[str, Any]) -> tuple[ExternalDocument, bool]:
        stmt = select(ExternalDocument).where(
            (ExternalDocument.fingerprint == payload["fingerprint"])
            | (
                (ExternalDocument.source_system == payload["source_system"])
                & (ExternalDocument.source_doc_id == payload["source_doc_id"])
            )
        )
        row = db.execute(stmt).scalar_one_or_none()
        created = row is None
        if row is None:
            row = ExternalDocument(**payload)
            db.add(row)
        else:
            row.title = payload["title"]
            row.url = payload["url"]
            row.publish_time_utc = payload.get("publish_time_utc")
            row.category = payload["category"]
            row.ticker = payload.get("ticker")
            row.instrument_name = payload.get("instrument_name")
            row.sector = payload.get("sector")
            row.event_type = payload.get("event_type")
            row.content_text = payload["content_text"]
            row.summary_json = payload["summary_json"]
            row.metadata_json = payload["metadata_json"]
            row.local_doc_dir = payload.get("local_doc_dir")
            row.fingerprint = payload["fingerprint"]
        return row, created

    def ingest_kind_disclosures(self, db: Session, ticker_or_name: str, max_items: int = 20) -> BatchIngestionResponse:
        started = datetime.now(UTC)
        request_id = str(uuid.uuid4())
        call_dir = self.archive.create_call_dir("batch_kind", request_id)
        self._ensure_tables(db)
        profile = self.providers.resolve_instrument(ticker_or_name)
        rows = self.providers.fetch_disclosures(profile.ticker, date.today(), include_content=True)[:max_items]

        docs_input: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            title = str(row.get("title") or f"disclosure_{idx+1}")
            body = str(row.get("content_text") or "")
            saved = self.archive.save_document(
                root=call_dir,
                source="kind_disclosures",
                doc_id=str(row.get("source_disclosure_id") or f"kind_{idx+1}"),
                title=title,
                url=str(row.get("url") or ""),
                content_text=body,
                metadata={
                    "ticker": profile.ticker,
                    "instrument_name": profile.name_kr,
                    "event_type": row.get("event_type"),
                    "impact_score": row.get("impact_score"),
                    "kind_type": self._kind_disclosure_type(title),
                },
                raw_bytes=row.get("raw_content") or b"",
                raw_ext=str(row.get("raw_ext") or ".html"),
            )
            row["local_doc_dir"] = saved["doc_dir"]
            docs_input.append({"source": "KRX_KIND", "title": title, "content_text": body, "url": row.get("url", "")})

        summaries = self.gemini.summarize_documents(docs_input)
        summary_map = {str(x.get("title") or ""): x for x in summaries}

        stored = 0
        skipped = 0
        for row in rows:
            title = str(row.get("title") or "")
            summary = summary_map.get(title, {})
            kind_type = self._kind_disclosure_type(title)
            fp = doc_fingerprint("KRX_KIND", str(row.get("url") or ""), title, str(row.get("content_text") or ""))
            payload = {
                "source_system": "KRX_KIND",
                "source_id": "S06",
                "source_doc_id": str(row.get("source_disclosure_id") or fp[:20]),
                "category": f"kind_{kind_type}",
                "title": title,
                "url": str(row.get("url") or ""),
                "publish_time_utc": row.get("publish_time_utc"),
                "ticker": profile.ticker,
                "instrument_name": profile.name_kr,
                "sector": profile.sector,
                "event_type": str(row.get("event_type") or event_classifier(f'{title} {row.get("content_text","")}')),
                "content_text": str(row.get("content_text") or ""),
                "summary_json": summary if isinstance(summary, dict) else {},
                "metadata_json": {
                    "impact_score": row.get("impact_score"),
                    "kind_type": kind_type,
                    "scores": score_engine(str(row.get("content_text") or title), row.get("publish_time_utc")),
                    "entities": entity_linker(str(row.get("content_text") or title)),
                },
                "local_doc_dir": row.get("local_doc_dir"),
                "fingerprint": fp,
            }
            _, created = self._upsert_document(db, payload)
            if created:
                stored += 1
            else:
                skipped += 1
        db.commit()
        finished = datetime.now(UTC)
        self.archive.save_json(
            call_dir,
            "snapshot/batch_result.json",
            {
                "source_system": "KRX_KIND",
                "ticker": profile.ticker,
                "fetched_count": len(rows),
                "stored_count": stored,
                "skipped_count": skipped,
            },
        )
        return BatchIngestionResponse(
            source_system="KRX_KIND",
            request_id=request_id,
            started_at_utc=started,
            finished_at_utc=finished,
            fetched_count=len(rows),
            stored_count=stored,
            skipped_count=skipped,
            saved_call_dir=str(call_dir),
            message="KRX KIND(정기/수시 공시) 배치 적재 완료",
        )

    def _kind_disclosure_type(self, title: str) -> str:
        t = (title or "").lower()
        regular_keywords = ["사업보고서", "분기보고서", "반기보고서", "감사보고서", "annual report", "quarterly"]
        if any(k.lower() in t for k in regular_keywords):
            return "regular"
        return "occasional"

    def ingest_policy_briefing(self, db: Session, max_items: int = 30) -> BatchIngestionResponse:
        seeds = [
            ("policy_news", "https://www.korea.kr/news/policyNewsList.do"),
            ("cheongwadae", "https://www.korea.kr/news/presidentView.do"),
            ("cabinet", "https://www.korea.kr/news/cabinetMeetingList.do"),
            ("ministry_briefing", "https://www.korea.kr/news/briefingList.do"),
        ]
        return self._ingest_seeded_web_docs(
            db=db,
            source_system="POLICY_BRIEFING",
            source_id="S28",
            seeds=seeds,
            max_items=max_items,
            channel_name="batch_policy",
            message="정책브리핑(청와대/국무회의/부처브리핑/정책뉴스) 배치 적재 완료",
        )

    def ingest_bok_publications(self, db: Session, max_items: int = 30) -> BatchIngestionResponse:
        seeds = [
            ("bok_publications", "https://www.bok.or.kr/portal/bbs/P0000559/list.do?menuNo=200690"),
            ("bok_research", "https://www.bok.or.kr/portal/bbs/B0000245/list.do?menuNo=200761"),
            ("bok_regional", "https://www.bok.or.kr/portal/bbs/B0000202/list.do?menuNo=200690"),
            ("bok_overseas", "https://www.bok.or.kr/portal/bbs/B0000347/list.do?menuNo=200691"),
            ("bok_business_info", "https://www.bok.or.kr/portal/main/contents.do?menuNo=200001"),
        ]
        return self._ingest_seeded_web_docs(
            db=db,
            source_system="BOK_PUBLICATIONS",
            source_id="S16",
            seeds=seeds,
            max_items=max_items,
            channel_name="batch_bok",
            message="한국은행(간행물/조사연구/지역/국외/업무별정보) 배치 적재 완료",
        )

    def _ingest_seeded_web_docs(
        self,
        db: Session,
        source_system: str,
        source_id: str,
        seeds: list[tuple[str, str]],
        max_items: int,
        channel_name: str,
        message: str,
    ) -> BatchIngestionResponse:
        started = datetime.now(UTC)
        request_id = str(uuid.uuid4())
        call_dir = self.archive.create_call_dir(channel_name, request_id)
        self._ensure_tables(db)
        per_seed = max(3, max_items // max(len(seeds), 1))

        collected: list[dict[str, Any]] = []
        for category, seed_url in seeds:
            try:
                resp = httpx.get(seed_url, timeout=20.0, follow_redirects=True, headers={"User-Agent": "investai-batch/0.3"})
                if not resp.is_success:
                    continue
                links = self._extract_links(str(resp.url), resp.text, per_seed)
                for i, link in enumerate(links):
                    content_text, raw, ext = self._fetch_page_doc(link["url"])
                    if not content_text:
                        continue
                    doc_id = f"{category}_{i+1}_{uuid.uuid4().hex[:8]}"
                    saved = self.archive.save_document(
                        root=call_dir,
                        source=category,
                        doc_id=doc_id,
                        title=link["title"],
                        url=link["url"],
                        content_text=content_text,
                        metadata={"seed_url": seed_url, "category": category},
                        raw_bytes=raw,
                        raw_ext=ext,
                    )
                    collected.append(
                        {
                            "source_system": source_system,
                            "source_id": source_id,
                            "source_doc_id": doc_id,
                            "category": category,
                            "title": link["title"],
                            "url": link["url"],
                            "content_text": content_text,
                            "local_doc_dir": saved["doc_dir"],
                        }
                    )
                    if len(collected) >= max_items:
                        break
            except Exception:
                continue
            if len(collected) >= max_items:
                break

        docs_input = [
            {"source": source_system, "title": x["title"], "content_text": x["content_text"], "url": x["url"]}
            for x in collected
        ]
        summaries = self.gemini.summarize_documents(docs_input)
        summary_map = {str(x.get("title") or ""): x for x in summaries}

        stored = 0
        skipped = 0
        for item in collected:
            title = str(item["title"])
            text = str(item["content_text"])
            summary = summary_map.get(title, {})
            fp = doc_fingerprint(item["source_system"], item["url"], title, text)
            payload = {
                "source_system": item["source_system"],
                "source_id": item["source_id"],
                "source_doc_id": item["source_doc_id"],
                "category": item["category"],
                "title": title,
                "url": item["url"],
                "publish_time_utc": None,
                "ticker": None,
                "instrument_name": None,
                "sector": None,
                "event_type": event_classifier(text),
                "content_text": text,
                "summary_json": summary if isinstance(summary, dict) else {},
                "metadata_json": {"scores": score_engine(text), "entities": entity_linker(text)},
                "local_doc_dir": item["local_doc_dir"],
                "fingerprint": fp,
            }
            _, created = self._upsert_document(db, payload)
            if created:
                stored += 1
            else:
                skipped += 1

        db.commit()
        finished = datetime.now(UTC)
        self.archive.save_json(
            call_dir,
            "snapshot/batch_result.json",
            {
                "source_system": source_system,
                "fetched_count": len(collected),
                "stored_count": stored,
                "skipped_count": skipped,
                "categories": [x[0] for x in seeds],
            },
        )
        return BatchIngestionResponse(
            source_system=source_system,
            request_id=request_id,
            started_at_utc=started,
            finished_at_utc=finished,
            fetched_count=len(collected),
            stored_count=stored,
            skipped_count=skipped,
            saved_call_dir=str(call_dir),
            message=message,
        )

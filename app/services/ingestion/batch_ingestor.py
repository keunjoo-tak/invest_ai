from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import ExternalDocument, ReleaseCalendarEvent
from app.schemas.batch_ingestion import BatchIngestionResponse
from app.services.ingestion.preprocessing import (
    doc_fingerprint,
    docx_text_extractor,
    entity_linker,
    event_classifier,
    html_cleaner,
    normalize_text_for_storage,
    pdf_text_extractor,
    score_engine,
)
from app.services.ingestion.providers import SourceProviderClient
from app.services.ingestion.raw_archive import RawArchiveManager
from app.services.llm.gemini_client import GeminiClient
from app.services.intelligence.decision_products import DecisionProductService

UTC = timezone.utc


class BatchIngestor:
    """문서형 외부 데이터 배치 수집/정제/적재 서비스."""

    POLICY_PATTERNS: dict[str, str] = {
        "policy_news": r"/news/policyNewsView\.do\?newsId=\d+",
        "cheongwadae": r"/(?:news|briefing)/presidentView\.do\?newsId=\d+",
        "cabinet": r"/news/cabinetMeetingView\.do\?newsId=\d+",
        "ministry_briefing": r"/briefing/(?:pressReleaseView|briefingRoomView)\.do\?newsId=\d+",
    }

    POLICY_KEYWORDS = [
        "금리",
        "통화정책",
        "물가",
        "환율",
        "수출",
        "반도체",
        "배터리",
        "자동차",
        "조선",
        "철강",
        "바이오",
        "관세",
        "보조금",
        "규제",
        "세제",
        "예산",
        "산업",
        "AI",
        "공급망",
        "주택",
        "부동산",
    ]

    BOK_KEYWORDS = [
        "기준금리",
        "통화정책",
        "금융통화위원회",
        "환율",
        "물가",
        "성장",
        "수출",
        "가계부채",
        "금융안정",
        "반도체",
        "산업",
        "경기",
        "전망",
        "리포트",
    ]


    NAVER_SECTION_SEEDS: list[tuple[str, str, str]] = [
        ("politics", "정치", "https://news.naver.com/section/100"),
        ("economy_finance", "경제-금융", "https://news.naver.com/breakingnews/section/101/259"),
        ("economy_securities", "경제-증권", "https://news.naver.com/breakingnews/section/101/258"),
        ("economy_realestate", "경제-부동산", "https://news.naver.com/breakingnews/section/101/260"),
        ("it_science", "IT/과학", "https://news.naver.com/section/105"),
        ("world", "세계", "https://news.naver.com/section/104"),
    ]

    def __init__(self) -> None:
        self.providers = SourceProviderClient()
        self.archive = RawArchiveManager()
        self.gemini = GeminiClient()

    def _ensure_tables(self, db: Session) -> None:
        """외부 문서 적재용 테이블 존재를 보장한다."""
        bind = db.get_bind()
        Base.metadata.create_all(bind=bind, tables=[ExternalDocument.__table__])

    def _http_get(self, url: str) -> httpx.Response:
        return httpx.get(url, timeout=25.0, follow_redirects=True, headers={"User-Agent": "investai-batch/0.4"})

    def _parse_datetime(self, raw: str) -> datetime | None:
        txt = (raw or "").strip()
        if not txt:
            return None
        for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(txt, fmt).replace(tzinfo=UTC)
            except Exception:
                continue
        try:
            return parsedate_to_datetime(txt).astimezone(UTC)
        except Exception:
            return None

    def _extract_meta_content(self, html: str, key: str) -> str:
        patterns = [
            rf'<meta[^>]+property=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+name=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(key)}["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(key)}["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html or "", re.I)
            if match:
                return html_cleaner(match.group(1))
        return ""

    def _extract_content_block(self, html: str, patterns: list[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, html or "", re.I | re.S)
            if match:
                return html_cleaner(match.group(1))
        return ""


    def _extract_naver_section_links(self, section_key: str, section_label: str, base_url: str, html: str, max_items: int) -> list[dict[str, Any]]:
        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        patterns = [
            r"(?is)<a[^>]+href=[\"']([^\"']+?/mnews/article/[^\"']+)[\"'][^>]*>(.*?)</a>",
            r"(?is)<a[^>]+href=[\"']([^\"']+?/article/[^\"']+)[\"'][^>]*>(.*?)</a>",
        ]
        for pattern in patterns:
            for href, label in re.findall(pattern, html or ""):
                if "/article/comment/" in href:
                    continue
                url = urljoin(base_url, href.replace("&amp;", "&"))
                url = re.sub(r'#.*$', '', url)
                if url in seen:
                    continue
                seen.add(url)
                title = html_cleaner(label).replace("기사원문", "").strip()
                if not title:
                    continue
                links.append(
                    {
                        "url": url,
                        "title": title[:300],
                        "category": f"naver_headline_{section_key}",
                        "section_key": section_key,
                        "section_label": section_label,
                    }
                )
                if len(links) >= max_items:
                    return links
        return links

    def _extract_naver_article_page(self, url: str, section_key: str, section_label: str) -> dict[str, Any] | None:
        try:
            resp = self._http_get(url)
            html = resp.text
            title = self._extract_meta_content(html, "og:title") or self._extract_meta_content(html, "title")
            title_match = re.search(r"<h2[^>]+id=[\"']title_area[\"'][^>]*>(.*?)</h2>", html, re.I | re.S)
            if title_match:
                title = html_cleaner(title_match.group(1))
            body = self._extract_content_block(
                html,
                [
                    r"<article[^>]+id=[\"']dic_area[\"'][^>]*>(.*?)</article>",
                    r"<div[^>]+id=[\"']dic_area[\"'][^>]*>(.*?)</div>\s*</article>",
                    r"<div[^>]+class=[\"'][^\"']*_article_body_contents[^\"']*[\"'][^>]*>(.*?)</div>",
                ],
            )
            description = self._extract_meta_content(html, "description") or self._extract_meta_content(html, "og:description")
            text = normalize_text_for_storage(body or description)
            if not text:
                return None
            published_raw = self._extract_meta_content(html, "article:published_time")
            if not published_raw:
                stamp_match = re.search(r"data-date-time=[\"']([^\"']+)[\"']", html, re.I)
                if stamp_match:
                    published_raw = stamp_match.group(1)
            published = self._parse_datetime(published_raw)
            article_id_match = re.search(r'/article/(\d+)/(\d+)', url)
            source_doc_id = f"{section_key}_{article_id_match.group(1)}_{article_id_match.group(2)}" if article_id_match else f"{section_key}_{uuid.uuid4().hex[:12]}"
            return {
                "source_doc_id": source_doc_id,
                "title": (title or text[:80])[:300],
                "content_text": text[:180000],
                "publish_time_utc": published,
                "raw_bytes": resp.content,
                "raw_ext": ".html",
                "attachments": [],
                "section_key": section_key,
                "section_label": section_label,
            }
        except Exception:
            return None

    def _extract_policy_links(self, category: str, base_url: str, html: str, max_items: int) -> list[dict[str, Any]]:
        pattern = self.POLICY_PATTERNS.get(category)
        if not pattern:
            return []
        links: list[dict[str, Any]] = []
        seen: set[str] = set()
        for href, label in re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html or ""):
            if not re.search(pattern, href, re.I):
                continue
            url = urljoin(base_url, href.replace("&amp;", "&"))
            if url in seen:
                continue
            seen.add(url)
            title = html_cleaner(label)
            title = title.replace("${title}", "").strip()
            if not title:
                continue
            links.append({"url": url, "title": title[:300], "category": category})
            if len(links) >= max_items:
                break
        return links

    def _seed_to_bok_rss(self, seed_url: str) -> str:
        return seed_url.replace("/list.do", "/news.rss")

    def _extract_bok_rss_items(self, category: str, feed_url: str, max_items: int) -> list[dict[str, Any]]:
        try:
            resp = self._http_get(feed_url)
            root = ET.fromstring(resp.text)
            items = root.findall(".//item")
            out: list[dict[str, Any]] = []
            for item in items[:max_items]:
                title = html_cleaner(item.findtext("title") or "")
                link = html_cleaner(item.findtext("link") or "")
                description = html_cleaner(item.findtext("description") or "")
                pub_dt = self._parse_datetime(item.findtext("pubDate") or "")
                if not title or not link:
                    continue
                out.append(
                    {
                        "url": link,
                        "title": title[:300],
                        "description": description[:2000],
                        "publish_time_utc": pub_dt,
                        "category": category,
                    }
                )
            return out
        except Exception:
            return []

    def _download_attachment(self, url: str) -> tuple[str, bytes, str]:
        try:
            resp = self._http_get(url)
            if not resp.is_success:
                return "", b"", ".bin"
            content_type = (resp.headers.get("content-type") or "").lower()
            ext = "." + url.split(".")[-1].split("?")[0].lower() if "." in url else ".bin"
            if "pdf" in content_type or ext == ".pdf":
                text = pdf_text_extractor(resp.content)[:120000]
                if "endstream" in text.lower() and "/type" in text.lower():
                    text = ""
                return text, resp.content, ".pdf"
            if ext == ".docx":
                return docx_text_extractor(resp.content)[:120000], resp.content, ".docx"
            if "html" in content_type or ext in {".htm", ".html"}:
                return html_cleaner(resp.text)[:120000], resp.content, ".html"
            return normalize_text_for_storage(resp.content.decode("utf-8", errors="ignore"))[:120000], resp.content, ext
        except Exception:
            return "", b"", ".bin"

    def _extract_bok_attachments(self, base_url: str, html: str) -> list[dict[str, str]]:
        files: list[dict[str, str]] = []
        seen: set[str] = set()
        for href, label in re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html or ""):
            href = href.replace("&amp;", "&")
            if not re.search(r"\.(pdf|hwp|docx?)($|\?)|/fileSrc/", href, re.I):
                continue
            url = urljoin(base_url, href)
            if url in seen:
                continue
            seen.add(url)
            files.append({"url": url, "title": html_cleaner(label)[:200]})
        return files[:6]

    def _extract_policy_page(self, url: str) -> dict[str, Any] | None:
        try:
            resp = self._http_get(url)
            html = resp.text
            title = self._extract_meta_content(html, "og:title") or self._extract_meta_content(html, "title")
            title = title or html_cleaner(re.search(r"<title>(.*?)</title>", html, re.I | re.S).group(1)) if re.search(r"<title>(.*?)</title>", html, re.I | re.S) else ""
            body = self._extract_content_block(
                html,
                [
                    r'<div[^>]+class=["\'][^"\']*view_cont[^"\']*["\'][^>]*>(.*?)</div>\s*<div[^>]+class=["\'][^"\']*article_footer',
                    r'<div[^>]+class=["\'][^"\']*view_cont[^"\']*["\'][^>]*>(.*?)</div>',
                    r'<div[^>]+class=["\'][^"\']*article_txt[^"\']*["\'][^>]*>(.*?)</div>',
                ],
            )
            description = self._extract_meta_content(html, "description") or self._extract_meta_content(html, "og:description")
            text = normalize_text_for_storage(body or description)
            if not text:
                return None
            date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", html)
            return {
                "title": title[:300] if title else text[:80],
                "content_text": text[:120000],
                "publish_time_utc": self._parse_datetime(date_match.group(1)) if date_match else None,
                "raw_bytes": resp.content,
                "raw_ext": ".html",
                "attachments": [],
            }
        except Exception:
            return None

    def _extract_bok_page(self, url: str, seed_description: str = "") -> dict[str, Any] | None:
        try:
            resp = self._http_get(url)
            html = resp.text
            title_match = re.search(r'<h2[^>]+class=["\'][^"\']*subject[^"\']*["\'][^>]*>(.*?)</h2>', html, re.I | re.S)
            title = html_cleaner(title_match.group(1)) if title_match else self._extract_meta_content(html, "og:title")
            publish_match = re.search(r'<dd[^>]+class=["\'][^"\']*date[^"\']*["\'][^>]*>(.*?)</dd>', html, re.I | re.S)
            publish_time = self._parse_datetime(html_cleaner(publish_match.group(1))) if publish_match else None
            body = self._extract_content_block(
                html,
                [
                    r'<div[^>]+class=["\'][^"\']*editor-view[^"\']*["\'][^>]*>(.*?)</div>',
                    r'<div[^>]+class=["\'][^"\']*cont[^"\']*["\'][^>]*>(.*?)</div>\s*</div>\s*</div>',
                ],
            )
            meta_desc = self._extract_meta_content(html, "description") or self._extract_meta_content(html, "og:description")
            attachments = self._extract_bok_attachments(url, html)

            attachment_texts: list[str] = []
            primary_raw = resp.content
            primary_ext = ".html"
            for file in attachments[:2]:
                text, raw, ext = self._download_attachment(file["url"])
                if text:
                    attachment_texts.append(f"[첨부:{file['title']}] {text}")
                if ext in {".pdf", ".docx"} and raw:
                    primary_raw = raw
                    primary_ext = ext

            combined = normalize_text_for_storage("\n\n".join(x for x in [body, meta_desc, seed_description, *attachment_texts] if x))
            if not combined:
                return None
            return {
                "title": (title or combined[:80])[:300],
                "content_text": combined[:180000],
                "publish_time_utc": publish_time,
                "raw_bytes": primary_raw,
                "raw_ext": primary_ext,
                "attachments": attachments,
            }
        except Exception:
            return None

    def _heuristic_market_relevance(self, source_system: str, title: str, content_text: str, category: str) -> dict[str, Any]:
        text = f"{title} {content_text}".lower()
        keywords = self.BOK_KEYWORDS if source_system == "BOK_PUBLICATIONS" else self.POLICY_KEYWORDS
        english_tokens = [
            "rate", "inflation", "cpi", "ppi", "employment", "payroll", "gdp", "pce", "yield", "treasury",
            "debt", "deficit", "fiscal", "oecd", "euro", "ecb", "export", "semiconductor", "tariff", "subsidy",
        ]
        hits = [token for token in keywords if token.lower() in text]
        english_hits = [token for token in english_tokens if token in text]
        if source_system == "BOK_PUBLICATIONS":
            base = 0.35
            should_keep = bool(hits) or bool(english_hits) or any(token in text for token in ["rate", "inflation", "yield", "macro"])
        elif source_system == "NAVER_HEADLINE_NEWS":
            base = 0.4
            should_keep = True
        elif source_system in {"FRED_MACRO", "BLS_MACRO", "BEA_MACRO", "FISCALDATA_MACRO", "OECD_BRIEFING", "WORLDBANK_MACRO", "IMF_MACRO", "EUROSTAT_MACRO", "GLOBAL_MACRO_INTEL", "INTERNATIONAL_MACRO_INTEL", "BROAD_ISSUE_STREAM"}:
            base = 0.42
            should_keep = True
        else:
            base = 0.18
            should_keep = len(hits) >= 2 or len(english_hits) >= 2 or any(token in text for token in ["policy", "support", "regulation", "industry"])
        related_assets = hits[:6] + english_hits[:6]
        return {
            "should_keep": should_keep,
            "relevance_score": round(min(1.0, base + len(hits) * 0.1 + len(english_hits) * 0.08), 3),
            "impact_scope": "macro" if source_system in {"BOK_PUBLICATIONS", "FRED_MACRO", "BLS_MACRO", "BEA_MACRO", "FISCALDATA_MACRO", "OECD_BRIEFING", "GLOBAL_MACRO_INTEL"} or any(token in text for token in ["rate", "inflation", "gdp", "debt", "fiscal"]) else "sector",
            "policy_area": "monetary" if source_system == "BOK_PUBLICATIONS" or any(token in text for token in ["rate", "yield", "pce", "cpi"]) else "fiscal" if any(token in text for token in ["fiscal", "debt", "deficit"]) else "industry",
            "related_assets": related_assets[:6],
            "reason": ", ".join(related_assets[:6]) if related_assets else "heuristic relevance match",
        }

    def _apply_market_triage(self, source_system: str, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not docs:
            return []
        triage_input = [
            {
                "source": source_system,
                "title": doc["title"],
                "content_text": doc["content_text"][:6000],
                "url": doc["url"],
                "category": doc["category"],
            }
            for doc in docs
        ]
        llm_rows = self.gemini.triage_market_documents(triage_input)
        llm_map = {str(item.get("title") or ""): item for item in llm_rows}
        kept: list[dict[str, Any]] = []
        for doc in docs:
            heuristic = self._heuristic_market_relevance(source_system, doc["title"], doc["content_text"], doc["category"])
            triage = llm_map.get(doc["title"], {})
            should_keep = bool(triage.get("should_keep")) or bool(heuristic["should_keep"])
            relevance_score = max(float(triage.get("relevance_score", 0.0) or 0.0), float(heuristic["relevance_score"] or 0.0))
            if not should_keep and relevance_score < 0.45:
                continue
            force_macro_source = source_system in {"FRED_MACRO", "BLS_MACRO", "BEA_MACRO", "FISCALDATA_MACRO", "OECD_BRIEFING", "WORLDBANK_MACRO", "IMF_MACRO", "EUROSTAT_MACRO", "GLOBAL_MACRO_INTEL", "INTERNATIONAL_MACRO_INTEL", "BROAD_ISSUE_STREAM"}
            doc["triage"] = {
                "should_keep": should_keep,
                "relevance_score": round(relevance_score, 3),
                "impact_scope": heuristic["impact_scope"] if force_macro_source else triage.get("impact_scope", heuristic["impact_scope"]),
                "policy_area": heuristic["policy_area"] if force_macro_source else triage.get("policy_area", heuristic["policy_area"]),
                "related_assets": triage.get("related_assets", heuristic["related_assets"]),
                "reason": triage.get("reason", heuristic["reason"]),
            }
            kept.append(doc)
        return kept

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
            title = str(row.get("title") or f"disclosure_{idx + 1}")
            body = str(row.get("content_text") or "")
            saved = self.archive.save_document(
                root=call_dir,
                source="kind_disclosures",
                doc_id=str(row.get("source_disclosure_id") or f"kind_{idx + 1}"),
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
                "event_type": str(row.get("event_type") or event_classifier(f"{title} {row.get('content_text', '')}")),
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
            message="KRX KIND 배치 적재 완료",
        )

    def _kind_disclosure_type(self, title: str) -> str:
        t = (title or "").lower()
        regular_keywords = ["사업보고서", "분기보고서", "반기보고서", "감사보고서", "annual report", "quarterly"]
        if any(keyword.lower() in t for keyword in regular_keywords):
            return "regular"
        return "occasional"

    def ingest_policy_briefing(self, db: Session, max_items: int = 30) -> BatchIngestionResponse:
        seeds = [
            ("policy_news", "https://www.korea.kr/news/policyNewsList.do"),
            ("cheongwadae", "https://www.korea.kr/briefing/presidentList.do"),
            ("cabinet", "https://www.korea.kr/news/cabinetMeetingList.do"),
            ("ministry_briefing", "https://www.korea.kr/briefing/pressReleaseList.do"),
        ]
        return self._ingest_policy_briefing_docs(
            db=db,
            source_system="POLICY_BRIEFING",
            source_id="S28",
            seeds=seeds,
            max_items=max_items,
            channel_name="batch_policy",
            message="정책브리핑 배치 적재 완료",
        )

    def ingest_bok_publications(self, db: Session, max_items: int = 30) -> BatchIngestionResponse:
        seeds = [
            ("bok_monetary_policy", "https://www.bok.or.kr/portal/bbs/P0000559/list.do?menuNo=200690"),
            ("bok_research", "https://www.bok.or.kr/portal/bbs/B0000245/list.do?menuNo=200789"),
            ("bok_regional", "https://www.bok.or.kr/portal/bbs/B0000202/list.do?menuNo=200782"),
            ("bok_overseas", "https://www.bok.or.kr/portal/bbs/B0000347/list.do?menuNo=201106"),
            ("bok_business_info", "https://www.bok.or.kr/portal/bbs/B0000529/list.do?menuNo=201716"),
        ]
        return self._ingest_bok_docs(
            db=db,
            source_system="BOK_PUBLICATIONS",
            source_id="S16",
            seeds=seeds,
            max_items=max_items,
            channel_name="batch_bok",
            message="한국은행 자료 배치 적재 완료",
        )

    def ingest_global_macro_briefings(self, db: Session, max_items: int = 20) -> BatchIngestionResponse:
        started = datetime.now(UTC)
        request_id = str(uuid.uuid4())
        call_dir = self.archive.create_call_dir("batch_global_macro", request_id)
        self._ensure_tables(db)
        collected: list[dict[str, Any]] = []
        as_of_date = date.today()

        source_specs = [
            ("OECD_BRIEFING", "S30", "oecd_briefing", "OECD Global and Europe Policy Briefing", self.providers._fetch_macro_oecd(as_of_date), "https://www.oecd.org/newsroom/"),
            ("FRED_MACRO", "S31", "fred_macro", "FRED US Macro Snapshot", self.providers._fetch_macro_fred(as_of_date), "https://fred.stlouisfed.org/docs/api/fred/"),
            ("BLS_MACRO", "S32", "bls_macro", "BLS US Labor and Inflation Snapshot", self.providers._fetch_macro_bls(as_of_date), "https://www.bls.gov/developers/"),
            ("BEA_MACRO", "S33", "bea_macro", "BEA US Growth and Consumption Snapshot", self.providers._fetch_macro_bea(as_of_date), "https://www.bea.gov/resources/developer"),
            ("FISCALDATA_MACRO", "S34", "fiscaldata_macro", "Fiscal Data US Treasury Snapshot", self.providers._fetch_macro_fiscaldata(as_of_date), "https://fiscaldata.treasury.gov/api-documentation/"),
        ]
        for source_system, source_id, category, title, rows, url in source_specs:
            if not rows:
                continue
            doc_id = f"{category}_{as_of_date.isoformat()}"
            content_text = self._render_macro_snapshot_text(title, rows)
            raw_bytes = self._serialize_json_bytes({"title": title, "rows": rows})
            saved = self.archive.save_document(
                root=call_dir,
                source=category,
                doc_id=doc_id,
                title=title,
                url=url,
                content_text=content_text,
                metadata={"as_of_date": str(as_of_date), "row_count": len(rows), "source_system": source_system},
                raw_bytes=raw_bytes,
                raw_ext=".json",
            )
            collected.append(
                {
                    "source_system": source_system,
                    "source_id": source_id,
                    "source_doc_id": doc_id,
                    "category": category,
                    "title": title,
                    "url": url,
                    "content_text": content_text,
                    "publish_time_utc": datetime.now(UTC),
                    "local_doc_dir": saved["doc_dir"],
                    "attachments": [],
                }
            )
            if len(collected) >= max_items:
                break

        return self._finalize_batch_docs(
            db=db,
            call_dir=call_dir,
            source_system="GLOBAL_MACRO_INTEL",
            message="Global macro briefing batch completed",
            request_id=request_id,
            started=started,
            collected=collected,
        )

    def ingest_international_macro_briefings(self, db: Session, max_items: int = 20) -> BatchIngestionResponse:
        started = datetime.now(UTC)
        request_id = str(uuid.uuid4())
        call_dir = self.archive.create_call_dir("batch_international_macro", request_id)
        self._ensure_tables(db)
        collected: list[dict[str, Any]] = []
        as_of_date = date.today()

        source_specs = [
            ("WORLDBANK_MACRO", "S37", "worldbank_macro", "World Bank International Macro Snapshot", self.providers._fetch_macro_world_bank(as_of_date), "https://api.worldbank.org/"),
            ("IMF_MACRO", "S38", "imf_macro", "IMF International Macro Snapshot", self.providers._fetch_macro_imf(as_of_date), "https://www.imf.org/external/datamapper/"),
            ("EUROSTAT_MACRO", "S39", "eurostat_macro", "Eurostat Europe Macro Snapshot", self.providers._fetch_macro_eurostat(as_of_date), "https://ec.europa.eu/eurostat/api/"),
        ]
        for source_system, source_id, category, title, rows, url in source_specs:
            if not rows:
                continue
            doc_id = f"{category}_{as_of_date.isoformat()}"
            content_text = self._render_macro_snapshot_text(title, rows)
            raw_bytes = self._serialize_json_bytes({"title": title, "rows": rows})
            saved = self.archive.save_document(
                root=call_dir,
                source=category,
                doc_id=doc_id,
                title=title,
                url=url,
                content_text=content_text,
                metadata={"as_of_date": str(as_of_date), "row_count": len(rows), "source_system": source_system},
                raw_bytes=raw_bytes,
                raw_ext=".json",
            )
            collected.append(
                {
                    "source_system": source_system,
                    "source_id": source_id,
                    "source_doc_id": doc_id,
                    "category": category,
                    "title": title,
                    "url": url,
                    "content_text": content_text,
                    "publish_time_utc": datetime.now(UTC),
                    "local_doc_dir": saved["doc_dir"],
                    "attachments": [],
                }
            )
            if len(collected) >= max_items:
                break

        return self._finalize_batch_docs(
            db=db,
            call_dir=call_dir,
            source_system="INTERNATIONAL_MACRO_INTEL",
            message="International macro batch completed",
            request_id=request_id,
            started=started,
            collected=collected,
        )

    def ingest_global_event_calendars(self, db: Session, max_items: int = 80) -> BatchIngestionResponse:
        started = datetime.now(UTC)
        request_id = str(uuid.uuid4())
        call_dir = self.archive.create_call_dir("batch_global_calendar", request_id)
        events = self.providers.fetch_official_event_stream(date.today(), horizon_days=45)[:max_items]
        stored = 0
        skipped = 0
        for row in events:
            stmt = select(ReleaseCalendarEvent).where(
                (ReleaseCalendarEvent.source_system == row['source_system'])
                & (ReleaseCalendarEvent.event_code == row['event_code'])
            )
            item = db.execute(stmt).scalar_one_or_none()
            if item is None:
                item = ReleaseCalendarEvent(
                    source_system=row['source_system'],
                    event_code=row['event_code'],
                    category=row['category'],
                    title=row['title'],
                    country=row.get('country', 'GLOBAL'),
                    source_tz=row.get('source_tz'),
                    scheduled_at_utc=row['scheduled_at_utc'],
                    release_at_utc=row.get('release_at_utc'),
                    available_at_utc=row.get('available_at_utc'),
                    status=row.get('status', 'scheduled'),
                    url=row.get('url'),
                    metadata_json=row.get('metadata_json') or {},
                )
                db.add(item)
                stored += 1
            else:
                item.category = row['category']
                item.title = row['title']
                item.country = row.get('country', 'GLOBAL')
                item.source_tz = row.get('source_tz')
                item.scheduled_at_utc = row['scheduled_at_utc']
                item.release_at_utc = row.get('release_at_utc')
                item.available_at_utc = row.get('available_at_utc')
                item.status = row.get('status', 'scheduled')
                item.url = row.get('url')
                item.metadata_json = row.get('metadata_json') or {}
                skipped += 1
        db.commit()
        self.archive.save_json(call_dir, 'snapshot/calendar_events.json', {'items': events})
        return BatchIngestionResponse(source_system='OFFICIAL_EVENT_STREAM', request_id=request_id, started_at_utc=started, finished_at_utc=datetime.now(UTC), fetched_count=len(events), stored_count=stored, skipped_count=skipped, saved_call_dir=str(call_dir), message='Official event calendar batch completed')

    def ingest_global_issue_stream(self, db: Session, max_items: int = 40) -> BatchIngestionResponse:
        started = datetime.now(UTC)
        request_id = str(uuid.uuid4())
        call_dir = self.archive.create_call_dir("batch_global_issue", request_id)
        docs = self.providers.fetch_broad_issue_stream(date.today(), lookback_days=7)[:max_items]
        collected: list[dict[str, Any]] = []
        for idx, row in enumerate(docs):
            doc_id = f"broad_issue_{date.today().isoformat()}_{idx+1}"
            saved = self.archive.save_document(
                root=call_dir,
                source='broad_issue_stream',
                doc_id=doc_id,
                title=str(row.get('title') or doc_id),
                url=str(row.get('url') or ''),
                content_text=str(row.get('content_text') or row.get('title') or ''),
                metadata={'publish_time_utc': str(row.get('publish_time_utc') or ''), 'source': row.get('source')},
                raw_bytes=row.get('raw_content') or b'',
                raw_ext=str(row.get('raw_ext') or '.json'),
            )
            collected.append({'source_system':'BROAD_ISSUE_STREAM','source_id':'S36','source_doc_id':doc_id,'category':'broad_issue_stream','title':str(row.get('title') or doc_id),'url':str(row.get('url') or ''),'content_text':str(row.get('content_text') or row.get('title') or ''),'publish_time_utc':row.get('publish_time_utc'),'local_doc_dir':saved['doc_dir'],'attachments':[]})
        return self._finalize_batch_docs(db, call_dir, 'BROAD_ISSUE_STREAM', 'Broad issue stream batch completed', request_id, started, collected)
    def ingest_naver_section_headlines(self, db: Session, max_items: int = 10) -> BatchIngestionResponse:
        started = datetime.now(UTC)
        request_id = str(uuid.uuid4())
        call_dir = self.archive.create_call_dir("batch_naver_headlines", request_id)
        self._ensure_tables(db)
        per_section = max(1, min(int(max_items), 10))
        collected: list[dict[str, Any]] = []

        for section_key, section_label, seed_url in self.NAVER_SECTION_SEEDS:
            try:
                html = self._http_get(seed_url).text
                links = self._extract_naver_section_links(section_key, section_label, seed_url, html, per_section)
                for link in links:
                    page = self._extract_naver_article_page(link["url"], section_key, section_label)
                    if page is None:
                        continue
                    saved = self.archive.save_document(
                        root=call_dir,
                        source=link["category"],
                        doc_id=page["source_doc_id"],
                        title=page["title"],
                        url=link["url"],
                        content_text=page["content_text"],
                        metadata={
                            "section_key": section_key,
                            "section_label": section_label,
                            "seed_url": seed_url,
                            "publish_time_utc": str(page.get("publish_time_utc") or ""),
                        },
                        raw_bytes=page["raw_bytes"],
                        raw_ext=page["raw_ext"],
                    )
                    collected.append(
                        {
                            "source_system": "NAVER_HEADLINE_NEWS",
                            "source_id": "S40",
                            "source_doc_id": page["source_doc_id"],
                            "category": link["category"],
                            "title": page["title"],
                            "url": link["url"],
                            "content_text": page["content_text"],
                            "publish_time_utc": page.get("publish_time_utc") or datetime.now(UTC),
                            "local_doc_dir": saved["doc_dir"],
                            "attachments": [],
                            "extra_metadata": {
                                "section_key": section_key,
                                "section_label": section_label,
                                "seed_url": seed_url,
                                "collection_window_days": 5,
                            },
                        }
                    )
            except Exception:
                continue

        return self._finalize_batch_docs(
            db=db,
            call_dir=call_dir,
            source_system="NAVER_HEADLINE_NEWS",
            message="Naver headline news batch completed",
            request_id=request_id,
            started=started,
            collected=collected,
        )



    def ingest_market_regime_snapshot(self, db: Session, max_items: int = 1) -> BatchIngestionResponse:
        started = datetime.now(UTC)
        request_id = str(uuid.uuid4())
        call_dir = self.archive.create_call_dir("batch_market_regime_snapshot", request_id)
        response = DecisionProductService().refresh_market_regime_snapshot(db=db, as_of_date=date.today())
        self.archive.save_json(call_dir, "snapshot/market_regime_snapshot.json", response.model_dump(mode="json"))
        return BatchIngestionResponse(
            source_system="MARKET_REGIME_SNAPSHOT",
            request_id=request_id,
            started_at_utc=started,
            finished_at_utc=datetime.now(UTC),
            fetched_count=max_items,
            stored_count=1,
            skipped_count=0,
            saved_call_dir=str(call_dir),
            message="Market regime snapshot batch completed",
        )

    def _render_macro_snapshot_text(self, title: str, rows: list[dict[str, Any]]) -> str:
        lines = [title, ""]
        for row in rows[:20]:
            lines.append(
                " - ".join(
                    [
                        str(row.get("indicator_name") or ""),
                        f"actual={row.get('actual')}",
                        f"prior={row.get('consensus')}",
                        f"surprise_std={row.get('surprise_std')}",
                        str(row.get("directional_interpretation") or ""),
                    ]
                )
            )
            content_text = str(row.get("content_text") or "").strip()
            if content_text:
                lines.append(content_text[:500])
        return normalize_text_for_storage("\n".join(lines))[:180000]

    def _serialize_json_bytes(self, payload: dict[str, Any]) -> bytes:
        import json

        return json.dumps(payload, ensure_ascii=False, default=str, indent=2).encode("utf-8")

    def _ingest_policy_briefing_docs(
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
                html = self._http_get(seed_url).text
                links = self._extract_policy_links(category, seed_url, html, per_seed)
                for index, link in enumerate(links):
                    page = self._extract_policy_page(link["url"])
                    if page is None:
                        continue
                    doc_id = f"{category}_{index + 1}_{uuid.uuid4().hex[:8]}"
                    saved = self.archive.save_document(
                        root=call_dir,
                        source=category,
                        doc_id=doc_id,
                        title=page["title"],
                        url=link["url"],
                        content_text=page["content_text"],
                        metadata={"seed_url": seed_url, "category": category, "publish_time_utc": str(page["publish_time_utc"] or "")},
                        raw_bytes=page["raw_bytes"],
                        raw_ext=page["raw_ext"],
                    )
                    collected.append(
                        {
                            "source_system": source_system,
                            "source_id": source_id,
                            "source_doc_id": doc_id,
                            "category": category,
                            "title": page["title"],
                            "url": link["url"],
                            "content_text": page["content_text"],
                            "publish_time_utc": page["publish_time_utc"],
                            "local_doc_dir": saved["doc_dir"],
                            "attachments": page["attachments"],
                        }
                    )
                    if len(collected) >= max_items:
                        break
            except Exception:
                continue
            if len(collected) >= max_items:
                break

        return self._finalize_batch_docs(db, call_dir, source_system, message, request_id, started, collected)

    def _ingest_bok_docs(
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
            rss_url = self._seed_to_bok_rss(seed_url)
            items = self._extract_bok_rss_items(category, rss_url, per_seed)
            for index, item in enumerate(items):
                page = self._extract_bok_page(item["url"], item.get("description", ""))
                if page is None:
                    continue
                doc_id = f"{category}_{index + 1}_{uuid.uuid4().hex[:8]}"
                saved = self.archive.save_document(
                    root=call_dir,
                    source=category,
                    doc_id=doc_id,
                    title=page["title"],
                    url=item["url"],
                    content_text=page["content_text"],
                    metadata={
                        "seed_url": seed_url,
                        "rss_url": rss_url,
                        "category": category,
                        "publish_time_utc": str(page["publish_time_utc"] or item.get("publish_time_utc") or ""),
                        "attachments": page["attachments"],
                    },
                    raw_bytes=page["raw_bytes"],
                    raw_ext=page["raw_ext"],
                )
                collected.append(
                    {
                        "source_system": source_system,
                        "source_id": source_id,
                        "source_doc_id": doc_id,
                        "category": category,
                        "title": page["title"],
                        "url": item["url"],
                        "content_text": page["content_text"],
                        "publish_time_utc": page["publish_time_utc"] or item.get("publish_time_utc"),
                        "local_doc_dir": saved["doc_dir"],
                        "attachments": page["attachments"],
                    }
                )
                if len(collected) >= max_items:
                    break
            if len(collected) >= max_items:
                break

        return self._finalize_batch_docs(db, call_dir, source_system, message, request_id, started, collected)

    def _finalize_batch_docs(
        self,
        db: Session,
        call_dir: Any,
        source_system: str,
        message: str,
        request_id: str,
        started: datetime,
        collected: list[dict[str, Any]],
    ) -> BatchIngestionResponse:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in collected:
            grouped.setdefault(str(item.get("source_system") or source_system), []).append(item)
        filtered: list[dict[str, Any]] = []
        for group_source, docs in grouped.items():
            filtered.extend(self._apply_market_triage(group_source, docs))
        docs_input = [
            {"source": item.get("source_system", source_system), "title": item["title"], "content_text": item["content_text"], "url": item["url"]}
            for item in filtered
        ]
        summaries = self.gemini.summarize_documents(docs_input)
        signals = self.gemini.extract_prediction_signals(docs_input)
        summary_map = {str(x.get("title") or ""): x for x in summaries}
        signal_map = {str(x.get("title") or ""): x for x in signals}

        stored = 0
        skipped = 0
        for item in filtered:
            title = item["title"]
            text = item["content_text"]
            summary = summary_map.get(title, {})
            signal = signal_map.get(title, {})
            fp = doc_fingerprint(item["source_system"], item["url"], title, text)
            payload = {
                "source_system": item["source_system"],
                "source_id": item["source_id"],
                "source_doc_id": item["source_doc_id"],
                "category": item["category"],
                "title": title,
                "url": item["url"],
                "publish_time_utc": item.get("publish_time_utc"),
                "ticker": None,
                "instrument_name": None,
                "sector": None,
                "event_type": str(signal.get("primary_event") or event_classifier(text)),
                "content_text": text,
                "summary_json": summary if isinstance(summary, dict) else {},
                "metadata_json": {
                    "scores": score_engine(text, item.get("publish_time_utc")),
                    "entities": entity_linker(text),
                    "triage": item.get("triage", {}),
                    "prediction_signal": signal,
                    "attachments": item.get("attachments", []),
                    **(item.get("extra_metadata") or {}),
                },
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
                "selected_count": len(filtered),
                "stored_count": stored,
                "skipped_count": skipped,
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

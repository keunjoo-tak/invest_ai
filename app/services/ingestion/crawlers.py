from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.schemas.ingestion_pipeline import ParsedDocument
from app.services.ingestion.preprocessing import (
    doc_fingerprint,
    doc_versioning,
    entity_linker,
    event_classifier,
    html_cleaner,
    score_engine,
)
from app.services.ingestion.source_catalog import get_source_item
from app.services.ingestion.raw_archive import RawArchiveManager

UTC = timezone.utc


class CrawlCollector:
    """v2 데이터소스 크롤링/파싱 수집기."""

    def __init__(self) -> None:
        self.archive = RawArchiveManager()

    def fetch_preview(self, source_id: str, target_url: str | None = None, max_chars: int = 8000) -> dict[str, Any]:
        source = get_source_item(source_id)
        if source is None:
            raise ValueError(f"unknown source_id: {source_id}")

        url = (target_url or source.url).strip()
        headers = {"User-Agent": "investai-bot/0.3 (+research)"}
        resp = httpx.get(url, headers=headers, timeout=20.0, follow_redirects=True)
        ctype = resp.headers.get("content-type", "")

        text = ""
        if "text/html" in ctype or "text/plain" in ctype:
            text = html_cleaner(resp.text)
        else:
            text = resp.text
        text = text[:max_chars]
        title = text[:100] if text else source.name

        fp = doc_fingerprint(source.source_id, url, title, text)
        version = doc_versioning(fp)
        parsed = ParsedDocument(
            source_id=source.source_id,
            source_url=url,
            title=title,
            content_text=text,
            entities=entity_linker(text),
            event_type=event_classifier(text),
            scores=score_engine(text, datetime.now(UTC)),
            fingerprint=fp,
            version=version,
            created_at_utc=datetime.now(UTC),
        )
        return {
            "source_id": source.source_id,
            "fetched_url": str(resp.url),
            "http_status": resp.status_code,
            "content_type": ctype,
            "content_length": len(resp.content),
            "sample_text": text[:800],
            "parsed": parsed,
        }

    def collect_and_save(
        self,
        source_id: str,
        request_id: str,
        request_label: str = "manual_collect",
        target_url: str | None = None,
        max_chars: int = 12000,
    ) -> dict[str, Any]:
        """원문 수집 후 호출 단위 폴더에 저장한다."""
        out = self.fetch_preview(source_id=source_id, target_url=target_url, max_chars=max_chars)
        call_dir = self.archive.create_call_dir(channel=request_label, request_id=request_id)
        parsed: ParsedDocument = out["parsed"]

        saved = self.archive.save_document(
            root=call_dir,
            source=source_id.lower(),
            doc_id=f"{source_id}_{request_id}",
            title=parsed.title,
            url=out["fetched_url"],
            content_text=parsed.content_text,
            metadata={
                "http_status": out["http_status"],
                "content_type": out["content_type"],
                "content_length": out["content_length"],
                "event_type": parsed.event_type,
                "scores": parsed.scores,
                "entities": parsed.entities,
                "fingerprint": parsed.fingerprint,
                "version": parsed.version,
            },
            raw_bytes=(out["sample_text"] or "").encode("utf-8", errors="ignore"),
            raw_ext=".txt",
        )
        self.archive.save_json(
            call_dir,
            "snapshot/collect_result.json",
            {
                "request_id": request_id,
                "source_id": source_id,
                "fetched_url": out["fetched_url"],
                "http_status": out["http_status"],
                "saved": saved,
            },
        )
        out["saved_call_dir"] = str(call_dir)
        out["saved_paths"] = saved
        return out

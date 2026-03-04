from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings

UTC = timezone.utc


class RawArchiveManager:
    """원본/원문 아카이브 저장 매니저."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_dir = Path(self.settings.downloads_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_call_dir(self, channel: str, request_id: str) -> Path:
        """호출 단위 저장 폴더를 생성한다."""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        name = f"{channel}_{ts}_{request_id}"
        path = self.base_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, root: Path, rel_path: str, payload: dict[str, Any]) -> Path:
        """JSON 파일 저장."""
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def save_text(self, root: Path, rel_path: str, text: str) -> Path:
        """텍스트 파일 저장."""
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text or "", encoding="utf-8")
        return path

    def save_bytes(self, root: Path, rel_path: str, data: bytes) -> Path:
        """바이너리 파일 저장."""
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data or b"")
        return path

    def save_document(
        self,
        root: Path,
        source: str,
        doc_id: str,
        title: str,
        url: str,
        content_text: str,
        metadata: dict[str, Any],
        raw_bytes: bytes | None = None,
        raw_ext: str = ".html",
    ) -> dict[str, str]:
        """문서 단위 저장(메타/본문/원본)."""
        safe_id = self._safe(doc_id)[:40] or "doc"
        safe_title = self._safe(title)[:36] or "untitled"
        suffix = hashlib.sha1(f"{doc_id}|{title}|{url}".encode("utf-8", errors="ignore")).hexdigest()[:10]
        doc_dir = root / source / f"{safe_id}_{safe_title}_{suffix}"
        doc_dir.mkdir(parents=True, exist_ok=True)

        meta = dict(metadata)
        meta.update({"source": source, "doc_id": doc_id, "title": title, "url": url})
        meta_path = doc_dir / "metadata.json"
        text_path = doc_dir / "content.txt"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        text_path.write_text(content_text or "", encoding="utf-8")

        raw_path = ""
        if raw_bytes:
            ext = raw_ext if raw_ext.startswith(".") else f".{raw_ext}"
            raw_file = doc_dir / f"raw{ext}"
            raw_file.write_bytes(raw_bytes)
            raw_path = str(raw_file)

        return {"doc_dir": str(doc_dir), "metadata_path": str(meta_path), "content_path": str(text_path), "raw_path": raw_path}

    def _safe(self, text: str) -> str:
        s = (text or "").strip()
        s = re.sub(r"[\\/:*?\"<>|]+", "_", s)
        s = re.sub(r"\s+", "_", s)
        return s

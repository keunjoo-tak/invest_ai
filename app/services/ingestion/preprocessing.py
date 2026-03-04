from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from typing import Any

UTC = timezone.utc

_VERSION_MAP: dict[str, int] = {}


def html_cleaner(raw_html: str) -> str:
    """HTML을 평문으로 정리한다."""
    txt = raw_html or ""
    txt = re.sub(r"(?is)<script.*?>.*?</script>", " ", txt)
    txt = re.sub(r"(?is)<style.*?>.*?</style>", " ", txt)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    txt = html.unescape(txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def pdf_text_extractor(raw_bytes: bytes) -> str:
    """PDF 바이트에서 텍스트를 추출한다(경량 fallback 포함)."""
    if not raw_bytes:
        return ""
    try:
        from pypdf import PdfReader  # type: ignore
        import io

        reader = PdfReader(io.BytesIO(raw_bytes))
        pages = [p.extract_text() or "" for p in reader.pages]
        return re.sub(r"\s+", " ", " ".join(pages)).strip()
    except Exception:
        # PDF 파서가 없거나 실패하면 디코딩 가능한 텍스트만 fallback 추출
        text = raw_bytes.decode("utf-8", errors="ignore")
        return re.sub(r"\s+", " ", text).strip()


def table_extractor(raw_html: str) -> list[list[str]]:
    """HTML table을 단순 2차원 배열로 추출한다."""
    tables: list[list[str]] = []
    for table in re.findall(r"(?is)<table.*?>.*?</table>", raw_html or ""):
        rows: list[str] = []
        for tr in re.findall(r"(?is)<tr.*?>.*?</tr>", table):
            cols = re.findall(r"(?is)<t[dh].*?>(.*?)</t[dh]>", tr)
            clean_cols = [html_cleaner(x) for x in cols]
            if clean_cols:
                rows.append(" | ".join(clean_cols))
        if rows:
            tables.append(rows)
    return tables


def doc_fingerprint(source_id: str, source_url: str, title: str, content_text: str) -> str:
    """문서 fingerprint를 생성한다."""
    head = content_text[:1500] if content_text else ""
    key = f"{source_id}|{source_url}|{title}|{head}".encode("utf-8", errors="ignore")
    return hashlib.sha256(key).hexdigest()


def doc_versioning(fingerprint: str) -> int:
    """동일 fingerprint 기준 버전 번호를 반환한다."""
    v = _VERSION_MAP.get(fingerprint, 0) + 1
    _VERSION_MAP[fingerprint] = v
    return v


def entity_linker(text: str) -> list[dict[str, Any]]:
    """텍스트에서 종목 엔터티를 간단 매핑한다."""
    entities: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for token in re.findall(r"\b[0-9]{6}\b", text or ""):
        key = ("ticker", token)
        if key in seen:
            continue
        seen.add(key)
        entities.append({"type": "symbol", "ticker": token, "name_kr": "", "mention": token})

    lexicon = {
        "삼성전자": "005930",
        "sk하이닉스": "000660",
        "하이닉스": "000660",
        "네이버": "035420",
        "카카오": "035720",
        "lg화학": "051910",
        "lg에너지솔루션": "373220",
        "삼성바이오로직스": "207940",
        "셀트리온": "068270",
        "현대자동차": "005380",
        "현대차": "005380",
        "현대모비스": "012330",
    }
    low = (text or "").lower()
    for name, ticker in lexicon.items():
        if name in low:
            key = ("name", name)
            if key in seen:
                continue
            seen.add(key)
            entities.append({"type": "symbol", "ticker": ticker, "name_kr": name, "mention": name})

    return entities[:8]


def event_classifier(text: str) -> str:
    """키워드 기반 이벤트 유형 분류."""
    t = (text or "").lower()
    if any(x in t for x in ["계약", "수주", "contract"]):
        return "contract"
    if any(x in t for x in ["실적", "영업이익", "earnings", "profit"]):
        return "earnings"
    if any(x in t for x in ["증자", "cb", "bw", "rights issue"]):
        return "financing"
    if any(x in t for x in ["정책", "regulation", "지원", "금리", "cpi", "ppi"]):
        return "macro_policy"
    if any(x in t for x in ["ir", "기업설명회", "발표자료"]):
        return "ir"
    return "general"


def score_engine(text: str, published_at_utc: datetime | None = None) -> dict[str, Any]:
    """영향도/감성/신선도 점수를 생성한다."""
    t = (text or "").lower()
    sentiment = 0.0
    if any(x in t for x in ["개선", "증가", "성장", "수주", "record", "beat"]):
        sentiment += 0.3
    if any(x in t for x in ["감소", "악화", "적자", "리콜", "drop", "miss"]):
        sentiment -= 0.3
    impact = 0.1
    if any(x in t for x in ["실적", "가이던스", "대규모", "정책", "금리", "cpi", "ppi", "수출"]):
        impact += 0.25
    now = datetime.now(UTC)
    if published_at_utc is None:
        freshness = 0.5
    else:
        age_h = max((now - published_at_utc).total_seconds() / 3600, 0.0)
        freshness = max(0.0, min(1.0, 1 - (age_h / 72)))
    return {
        "sentiment_score": round(max(-1.0, min(1.0, sentiment)), 3),
        "impact_score": round(max(-1.0, min(1.0, impact)), 3),
        "freshness_score": round(freshness, 3),
    }

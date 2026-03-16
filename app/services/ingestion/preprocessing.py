from __future__ import annotations

import hashlib
import html
import io
import re
import zipfile
from datetime import datetime, timezone
from statistics import mean
from typing import Any
from xml.etree import ElementTree as ET

UTC = timezone.utc

_VERSION_MAP: dict[str, int] = {}

_POSITIVE_TOKENS = [
    "개선",
    "증가",
    "성장",
    "확대",
    "수주",
    "계약",
    "beat",
    "record",
]
_NEGATIVE_TOKENS = [
    "감소",
    "악화",
    "적자",
    "리스크",
    "취소",
    "소송",
    "drop",
    "miss",
]
_SUPPLY_TOKENS = ["공급계약", "수주", "계약", "납품", "증설", "고객사"]
_FINANCING_TOKENS = ["유상증자", "cb", "bw", "전환사채", "신주인수권부사채", "차입", "financing"]
_SHAREHOLDER_RETURN_TOKENS = ["배당", "자사주", "소각", "주주환원", "share buyback"]
_GOVERNANCE_TOKENS = ["지배구조", "esg", "감사", "사외이사", "주주총회", "governance"]
_MACRO_POSITIVE_TOKENS = ["완화", "부양", "개선", "상승 둔화", "안정"]
_MACRO_NEGATIVE_TOKENS = ["긴축", "인상", "급등", "불안", "악화", "하락"]


def html_cleaner(raw_html: str) -> str:
    """HTML 본문을 예측 파이프라인용 평문으로 정리한다."""
    txt = raw_html or ""
    txt = re.sub(r"(?is)<script.*?>.*?</script>", " ", txt)
    txt = re.sub(r"(?is)<style.*?>.*?</style>", " ", txt)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    txt = html.unescape(txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def normalize_text_for_storage(text: str) -> str:
    """DB 저장 전 텍스트를 정규화한다."""
    txt = (text or "").replace("\x00", " ")
    txt = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F]+", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def pdf_text_extractor(raw_bytes: bytes) -> str:
    """PDF 바이트에서 텍스트를 추출한다."""
    if not raw_bytes:
        return ""
    try:
        from pypdf import PdfReader  # type: ignore
        import io

        reader = PdfReader(io.BytesIO(raw_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return normalize_text_for_storage(" ".join(pages))
    except Exception:
        text = raw_bytes.decode("utf-8", errors="ignore")
        return normalize_text_for_storage(text)


def docx_text_extractor(raw_bytes: bytes) -> str:
    """DOCX 바이트에서 텍스트를 추출한다."""
    if not raw_bytes:
        return ""
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:  # type: ignore[name-defined]
            xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        texts = [node.text or "" for node in root.iter() if node.text]
        return normalize_text_for_storage(" ".join(texts))
    except Exception:
        return normalize_text_for_storage(raw_bytes.decode("utf-8", errors="ignore"))


def table_extractor(raw_html: str) -> list[list[str]]:
    """HTML table을 간단한 2차원 텍스트 배열로 변환한다."""
    tables: list[list[str]] = []
    for table in re.findall(r"(?is)<table.*?>.*?</table>", raw_html or ""):
        rows: list[str] = []
        for tr in re.findall(r"(?is)<tr.*?>.*?</tr>", table):
            cols = re.findall(r"(?is)<t[dh].*?>(.*?)</t[dh]>", tr)
            clean_cols = [html_cleaner(col) for col in cols]
            if clean_cols:
                rows.append(" | ".join(clean_cols))
        if rows:
            tables.append(rows)
    return tables


def doc_fingerprint(source_id: str, source_url: str, title: str, content_text: str) -> str:
    """문서 중복 판별을 위한 fingerprint를 만든다."""
    head = content_text[:1500] if content_text else ""
    key = f"{source_id}|{source_url}|{title}|{head}".encode("utf-8", errors="ignore")
    return hashlib.sha256(key).hexdigest()


def doc_versioning(fingerprint: str) -> int:
    """동일 fingerprint 기준 버전 번호를 증가시킨다."""
    version = _VERSION_MAP.get(fingerprint, 0) + 1
    _VERSION_MAP[fingerprint] = version
    return version


def entity_linker(text: str) -> list[dict[str, Any]]:
    """텍스트 내 주요 종목 표현을 탐지해 엔터티 후보를 만든다."""
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
        "naver": "035420",
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
    """문서 내용을 기반으로 이벤트 유형을 분류한다."""
    t = (text or "").lower()
    if any(token in t for token in ["계약", "수주", "contract"]):
        return "contract"
    if any(token in t for token in ["실적", "영업이익", "earnings", "profit"]):
        return "earnings"
    if any(token in t for token in ["증자", "cb", "bw", "rights issue", "전환사채"]):
        return "financing"
    if any(token in t for token in ["정책", "regulation", "금리", "cpi", "ppi"]):
        return "macro_policy"
    if any(token in t for token in ["ir", "기업설명회", "발표자료"]):
        return "ir"
    if any(token in t for token in ["배당", "자사주", "주주환원"]):
        return "shareholder_return"
    if any(token in t for token in ["지배구조", "esg", "감사", "governance"]):
        return "governance"
    return "general"


def score_engine(text: str, published_at_utc: datetime | None = None) -> dict[str, Any]:
    """텍스트 기반 감성, 영향도, 신선도 점수를 생성한다."""
    t = (text or "").lower()
    sentiment = 0.0
    if any(token in t for token in _POSITIVE_TOKENS):
        sentiment += 0.3
    if any(token in t for token in _NEGATIVE_TOKENS):
        sentiment -= 0.3

    impact = 0.1
    if any(token in t for token in ["실적", "가이던스", "대규모", "정책", "금리", "cpi", "ppi", "수출"]):
        impact += 0.25
    if any(token in t for token in _FINANCING_TOKENS):
        impact += 0.1

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


def _count_tokens(text: str, tokens: list[str]) -> int:
    low = (text or "").lower()
    return sum(low.count(token.lower()) for token in tokens)


def _extract_text_signal_base(row: dict[str, Any]) -> str:
    return " ".join(
        [
            str(row.get("title") or ""),
            str(row.get("content_text") or ""),
            str(row.get("doc_summary") or ""),
            str(row.get("llm_signal_text") or ""),
        ]
    ).strip()


def enrich_news_records(news: list[dict[str, Any]], llm_signals: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """뉴스 원문을 예측 모델용 구조화 변수로 변환한다."""
    llm_map = {str(item.get("title") or ""): item for item in (llm_signals or [])}
    out: list[dict[str, Any]] = []
    total_count = max(len(news), 1)
    for row in news:
        item = dict(row)
        llm_signal = llm_map.get(str(item.get("title") or ""), {})
        if llm_signal:
            item["llm_signal_text"] = " ".join(str(x) for x in llm_signal.get("key_drivers", []) if x)
        text = _extract_text_signal_base(item)
        scores = score_engine(text, item.get("publish_time_utc"))
        item["sentiment_score"] = scores["sentiment_score"]
        item["impact_score"] = max(float(item.get("impact_scope") == "market_wide") * 0.2, scores["impact_score"])
        item["freshness_score"] = scores["freshness_score"]
        item["event_type"] = llm_signal.get("primary_event") or event_classifier(text)
        item["keyword_density"] = round(
            (_count_tokens(text, _POSITIVE_TOKENS + _NEGATIVE_TOKENS + _SUPPLY_TOKENS + _FINANCING_TOKENS) / max(len(text.split()), 1)),
            4,
        )
        item["supply_signal"] = min(1.0, round(_count_tokens(text, _SUPPLY_TOKENS) / 4.0, 3))
        item["financing_risk"] = min(1.0, round(_count_tokens(text, _FINANCING_TOKENS) / 3.0, 3))
        item["governance_signal"] = min(1.0, round(_count_tokens(text, _GOVERNANCE_TOKENS) / 3.0, 3))
        item["shareholder_return_signal"] = min(1.0, round(_count_tokens(text, _SHAREHOLDER_RETURN_TOKENS) / 3.0, 3))
        item["attention_score"] = round(
            min(
                1.0,
                (
                    abs(item["sentiment_score"]) * 0.35
                    + item["freshness_score"] * 0.35
                    + min(1.0, total_count / 12) * 0.30
                ),
            ),
            3,
        )
        item["entities"] = entity_linker(text)
        item["event_flags"] = {
            "supply": item["supply_signal"] > 0,
            "financing": item["financing_risk"] > 0,
            "shareholder_return": item["shareholder_return_signal"] > 0,
            "governance": item["governance_signal"] > 0,
        }
        out.append(item)
    return out


def enrich_disclosure_records(
    disclosures: list[dict[str, Any]],
    llm_signals: list[dict[str, Any]] | None = None,
    llm_disclosure_scores: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """공시 원문을 이벤트 더미와 구조화 점수로 변환한다."""
    llm_map = {str(item.get("title") or ""): item for item in (llm_signals or [])}
    llm_score_map = {str(item.get("title") or ""): item for item in (llm_disclosure_scores or [])}
    out: list[dict[str, Any]] = []
    for row in disclosures:
        item = dict(row)
        llm_signal = llm_map.get(str(item.get("title") or ""), {})
        llm_score = llm_score_map.get(str(item.get("title") or ""), {})
        if llm_signal:
            item["llm_signal_text"] = " ".join(str(x) for x in llm_signal.get("key_drivers", []) if x)
        text = _extract_text_signal_base(item)
        scores = score_engine(text, item.get("publish_time_utc"))
        item["event_type"] = llm_signal.get("primary_event") or item.get("event_type") or event_classifier(text)
        item["impact_score"] = round(
            max(float(item.get("impact_score") or 0.0), scores["impact_score"]),
            3,
        )
        item["sentiment_score"] = scores["sentiment_score"]
        item["freshness_score"] = scores["freshness_score"]
        item["supply_signal"] = min(1.0, round(_count_tokens(text, _SUPPLY_TOKENS) / 3.0, 3))
        item["financing_risk"] = min(1.0, round(_count_tokens(text, _FINANCING_TOKENS) / 2.0, 3))
        item["shareholder_return_signal"] = min(1.0, round(_count_tokens(text, _SHAREHOLDER_RETURN_TOKENS) / 2.0, 3))
        item["governance_signal"] = min(1.0, round(_count_tokens(text, _GOVERNANCE_TOKENS) / 2.0, 3))
        item["disclosure_bullish_score"] = round(float(llm_score.get("bullish_score") or 0.0), 3)
        item["disclosure_bearish_score"] = round(float(llm_score.get("bearish_score") or 0.0), 3)
        item["disclosure_net_score"] = round(float(llm_score.get("net_score") or 0.0), 3)
        item["material_disclosure_severity"] = round(float(llm_score.get("event_severity") or 0.0), 3)
        if llm_score.get("rationale"):
            item["llm_disclosure_rationale"] = str(llm_score.get("rationale") or "")
        if llm_score.get("event_label"):
            item["event_type"] = str(llm_score.get("event_label") or item["event_type"])
        item["impact_score"] = round(
            min(
                1.0,
                max(
                    float(item.get("impact_score") or 0.0),
                    item["material_disclosure_severity"] * 0.7 + abs(item["disclosure_net_score"]) * 0.3,
                ),
            ),
            3,
        )
        item["sentiment_score"] = round(
            max(-1.0, min(1.0, float(item.get("sentiment_score") or 0.0) + item["disclosure_net_score"] * 0.7)),
            3,
        )
        item["keyword_density"] = round(
            (_count_tokens(text, _POSITIVE_TOKENS + _NEGATIVE_TOKENS + _SUPPLY_TOKENS + _FINANCING_TOKENS) / max(len(text.split()), 1)),
            4,
        )
        item["earnings_event_flag"] = item["event_type"] == "earnings"
        item["contract_event_flag"] = item["event_type"] == "contract"
        item["financing_event_flag"] = item["event_type"] == "financing" or item["financing_risk"] > 0
        item["shareholder_return_event_flag"] = item["event_type"] == "shareholder_return" or item["shareholder_return_signal"] > 0
        item["governance_event_flag"] = item["event_type"] == "governance" or item["governance_signal"] > 0
        item["entities"] = entity_linker(text)
        out.append(item)
    return out


def enrich_macro_rows(macro_rows: list[dict[str, Any]], llm_signals: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """거시 지표 행을 공통 스키마로 정규화하고 예측용 방향 점수를 추가한다."""
    llm_map = {str(item.get("title") or ""): item for item in (llm_signals or [])}
    out: list[dict[str, Any]] = []
    for row in macro_rows:
        item = dict(row)
        title = str(item.get("title") or item.get("indicator_name") or "")
        llm_signal = llm_map.get(title, {})
        text = " ".join(
            [
                title,
                str(item.get("directional_interpretation") or ""),
                str(item.get("content_text") or ""),
                " ".join(str(x) for x in llm_signal.get("key_drivers", []) if x),
            ]
        ).strip()
        sentiment = 0.0
        if any(token in text for token in _MACRO_POSITIVE_TOKENS):
            sentiment += 0.2
        if any(token in text for token in _MACRO_NEGATIVE_TOKENS):
            sentiment -= 0.2
        surprise = float(item.get("surprise_std") or 0.0)
        item["macro_signal_strength"] = round(min(1.0, abs(surprise) / 2.5), 3)
        item["macro_risk_score"] = round(max(0.0, surprise) + max(0.0, -sentiment), 3)
        item["macro_support_score"] = round(max(0.0, sentiment) + max(0.0, -surprise), 3)
        country = str(item.get("country") or "GLOBAL").upper()
        item["macro_relevance_weight"] = {
            "KR": 1.0,
            "US": 0.9,
            "EU": 0.8,
            "GLOBAL": 0.75,
        }.get(country, 0.7)
        item["available_at"] = item.get("available_at") or item.get("release_at") or item.get("as_of_date")
        item["observation_date"] = item.get("observation_date") or item.get("as_of_date")
        item["ingested_at"] = item.get("ingested_at") or datetime.now(UTC)
        item["revision"] = item.get("revision") or "initial"
        out.append(item)
    return out


def build_text_feature_snapshot(news: list[dict[str, Any]], disclosures: list[dict[str, Any]]) -> dict[str, float]:
    """뉴스/공시 구조화 결과를 공통 수치 feature snapshot으로 집계한다."""
    news_count = len(news)
    disclosure_count = len(disclosures)

    def avg(rows: list[dict[str, Any]], key: str) -> float:
        values = [float(row.get(key) or 0.0) for row in rows]
        return mean(values) if values else 0.0

    return {
        "news_count_7d": float(news_count),
        "disclosure_count_30d": float(disclosure_count),
        "text_attention_score": round(avg(news, "attention_score"), 3),
        "text_keyword_density": round(avg(news + disclosures, "keyword_density"), 4),
        "disclosure_bullish_score": round(avg(disclosures, "disclosure_bullish_score"), 3),
        "disclosure_bearish_score": round(avg(disclosures, "disclosure_bearish_score"), 3),
        "disclosure_net_score": round(avg(disclosures, "disclosure_net_score"), 3),
        "material_disclosure_severity": round(avg(disclosures, "material_disclosure_severity"), 3),
        "supply_signal_score": round(avg(news + disclosures, "supply_signal"), 3),
        "financing_risk_score": round(avg(news + disclosures, "financing_risk"), 3),
        "shareholder_return_score": round(avg(news + disclosures, "shareholder_return_signal"), 3),
        "governance_score": round(avg(news + disclosures, "governance_signal"), 3),
        "earnings_event_ratio": round(
            sum(1 for row in disclosures if row.get("earnings_event_flag")) / max(disclosure_count, 1),
            3,
        ),
        "contract_event_ratio": round(
            sum(1 for row in disclosures if row.get("contract_event_flag")) / max(disclosure_count, 1),
            3,
        ),
    }

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.services.ingestion.preprocessing import entity_linker, normalize_text_for_storage, score_engine

UTC = timezone.utc

_REPORT_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("morning_outlook", ("모닝", "morning", "개장", "장전", "morning meeting", "morning brief", "morning letter")),
    ("close_outlook", ("마감", "close", "closing", "장마감", "eod")),
    ("weekly_strategy", ("weekly", "주간", "week ahead")),
    ("monthly_strategy", ("monthly", "월간", "month ahead", "outlook")),
    ("daily_strategy", ("daily", "데일리", "today", "전략", "market strategy", "house view")),
    ("rates", ("금리", "채권", "rates", "yield", "bond")),
    ("fx", ("환율", "fx", "외환", "dollar", "usd/krw")),
    ("credit", ("credit", "크레딛", "회사채", "spread")),
    ("commodity", ("commodities", "commodity", "원자재", "oil", "copper")),
    ("policy_brief", ("정책", "regulation", "policy")),
    ("sector_report", ("산업", "sector", "industry", "업종", "semiconductor", "반도체", "배터리")),
    ("company_report", ("기업", "company", "target price", "목표주가", "투자의견", "buy", "hold", "reduce", "overweight", "neutral", "underweight")),
    ("theme_report", ("테마", "theme", "ai", "인공지능", "정책 수혜")),
    ("etf_report", ("etf", "글로벌etf", "fund flow")),
    ("real_estate", ("부동산", "housing", "real estate")),
    ("macro", ("macro", "거시", "economy", "경제", "전망", "inflation", "gdp", "house view")),
]

_SECTOR_RULES: dict[str, tuple[str, ...]] = {
    "반도체": ("반도체", "메모리", "dram", "nand", "hbm", "semiconductor", "chip"),
    "인터넷": ("internet", "platform", "광고", "커머스", "portal", "search"),
    "2차전지·화학": ("2차전지", "배터리", "battery", "chem", "cathode", "anode", "화학"),
    "바이오": ("bio", "바이오", "pharma", "cdmo", "clinical", "제약"),
    "자동차": ("자동차", "auto", "ev", "vehicle", "mobility", "완성차"),
    "금융": ("bank", "banking", "증권", "보험", "financial", "credit"),
    "부동산": ("부동산", "housing", "real estate", "mortgage"),
    "조선·산업재": ("조선", "ship", "industrial", "machinery", "방산", "defense"),
    "철강·소재": ("steel", "철강", "metals", "material", "소재"),
    "IT/과학": ("ai", "it", "science", "cloud", "software", "robot"),
}

_POSITIVE_STANCE = ("buy", "overweight", "매수", "비중확대", "상향", "선호", "우호", "개선", "확대")
_NEGATIVE_STANCE = ("reduce", "avoid", "underweight", "매도", "비중축소", "하향", "악화", "둔화", "리스크", "부정")
_CATALYST_TOKENS = ("실적", "가이던스", "수주", "계약", "출하", "증설", "launch", "approval")
_RISK_TOKENS = ("리스크", "규제", "관세", "소송", "자금조달", "유상증자", "cb", "bw", "downside", "불확실성")
_VALUATION_POSITIVE = ("밸류에이션 매력", "저평가", "undervalued", "cheap", "매력")
_VALUATION_NEGATIVE = ("고평가", "부담", "expensive", "valuation burden")
_MANAGEMENT_POSITIVE = ("execution", "집행력", "capacity", "수율 개선", "share gain", "점유율 확대")
_REGION_RULES: dict[str, tuple[str, ...]] = {
    "KR": ("korea", "kr", "국내", "한국"),
    "US": ("us", "usa", "미국", "fed", "nasdaq", "s&p"),
    "EU": ("euro", "ecb", "europe", "eu", "유럽"),
    "CN": ("china", "중국"),
    "JP": ("japan", "일본"),
}


def classify_research_report_type(title: str, content_text: str) -> str:
    """리서치 문서 제목과 본문을 기반으로 표준 report_type을 분류한다."""

    text = f"{title} {content_text}".lower()
    for report_type, tokens in _REPORT_TYPE_RULES:
        if any(token.lower() in text for token in tokens):
            return report_type
    return "macro"


def normalize_research_document(
    *,
    house_name: str,
    source_id: str,
    access_tier: str,
    redistribution_policy: str,
    layout_profile: str,
    market_scope: str,
    title: str,
    content_text: str,
    url: str,
    published_at_utc: datetime | None,
    summary: dict[str, Any] | None = None,
    prediction_signal: dict[str, Any] | None = None,
    house_quality_score: float = 0.8,
) -> dict[str, Any]:
    """리서치 문서를 서비스 투영용 메타데이터로 정규화한다."""

    text = normalize_text_for_storage(content_text or "")
    title_text = (title or "").strip()
    combined = f"{title_text}\n{text}".strip()
    report_type = classify_research_report_type(title_text, text)
    entities = entity_linker(combined)
    sector_tags = _extract_sector_tags(combined)
    named_ticker_tags = [str(item.get("ticker") or "") for item in entities if item.get("ticker") and item.get("name_kr")]
    ticker_tags = named_ticker_tags or [str(item.get("ticker") or "") for item in entities if item.get("ticker")]
    company_tags = [str(item.get("name_kr") or item.get("mention") or item.get("ticker") or "") for item in entities]
    region_tags = _extract_region_tags(combined, market_scope)
    asset_tags = _asset_tags(report_type, combined)
    recommendation = _extract_recommendation(combined)
    target_price, previous_target_price, current_price = _extract_price_fields(combined)
    price_upside_pct = ((target_price / max(current_price, 1.0)) - 1.0) * 100.0 if target_price and current_price else 0.0
    stance_value = _stance_value(combined, recommendation)
    report_scope = _report_scope(report_type, ticker_tags, sector_tags)
    service_targets = _service_targets(report_type, report_scope)
    scores = score_engine(combined, published_at_utc)
    evidence_density = min(1.0, round(len((summary or {}).get("key_points") or []) / 4.0 + min(len(text) / 8000.0, 0.65), 3))
    parser_quality = 0.85 if len(text) >= 400 else 0.55 if len(text) >= 120 else 0.35
    feature_confidence = round(min(1.0, (parser_quality * 0.45) + (house_quality_score * 0.30) + (evidence_density * 0.25)), 3)
    target_price_revision_score = round((target_price - previous_target_price) / max(previous_target_price, 1.0), 3) if target_price and previous_target_price else 0.0
    thesis_positive_score = round(min(1.0, max(0.0, 0.5 + stance_value * 0.35 + _token_hits(combined, _POSITIVE_STANCE) * 0.06)), 3)
    thesis_negative_score = round(min(1.0, max(0.0, 0.35 + _token_hits(combined, _NEGATIVE_STANCE + _RISK_TOKENS) * 0.07)), 3)
    catalyst_near_term_score = round(min(1.0, _token_hits(combined, _CATALYST_TOKENS) * 0.12 + scores["freshness_score"] * 0.25), 3)
    valuation_language_score = round(max(-1.0, min(1.0, _token_hits(combined, _VALUATION_POSITIVE) * 0.2 - _token_hits(combined, _VALUATION_NEGATIVE) * 0.2)), 3)
    management_execution_signal = round(min(1.0, _token_hits(combined, _MANAGEMENT_POSITIVE) * 0.16), 3)
    industry_tailwind_score = round(min(1.0, max(0.0, (0.5 + stance_value * 0.3) if sector_tags else 0.0)), 3)
    industry_headwind_score = round(min(1.0, max(0.0, 0.35 + (-stance_value) * 0.35 if sector_tags else 0.0)), 3)
    company_recommendation_score = round(max(-1.0, min(1.0, stance_value)), 3)
    target_price_upside_score = round(max(-1.0, min(1.0, price_upside_pct / 30.0)), 3)
    risk_on_off_score = round(max(-1.0, min(1.0, _risk_on_off(report_type, stance_value, combined))), 3)
    growth_inflation_mix_score = round(max(-1.0, min(1.0, _growth_inflation_mix(combined))), 3)
    liquidity_score = round(max(-1.0, min(1.0, _liquidity_score(combined))), 3)
    policy_risk_score = round(min(1.0, _token_hits(combined, ("정책", "regulation", "tariff", "관세", "fiscal")) * 0.18), 3)
    geopolitical_risk_score = round(min(1.0, _token_hits(combined, ("지정학", "geopolitical", "middle east", "ukraine", "war", "분쟁")) * 0.22), 3)
    rates_direction_score = round(max(-1.0, min(1.0, _rates_direction(combined))), 3)
    fx_pressure_score = round(max(-1.0, min(1.0, _fx_pressure(combined))), 3)

    summary_text = str((summary or {}).get("summary") or title_text or text[:140])
    key_bullets = [str(x) for x in ((summary or {}).get("key_points") or []) if x][:4]
    risk_bullets = [str(x) for x in ((summary or {}).get("risk_tags") or []) if x][:4] or _sentence_bullets(text, _RISK_TOKENS, 3)
    catalyst_bullets = _sentence_bullets(text, _CATALYST_TOKENS, 3)

    primary_ticker = ticker_tags[0] if report_scope == "company" and ticker_tags else None
    primary_company = company_tags[0] if report_scope == "company" and company_tags else None
    primary_sector = sector_tags[0] if sector_tags else None

    return {
        "house_name": house_name,
        "source_id": source_id,
        "access_tier": access_tier,
        "redistribution_policy": redistribution_policy,
        "layout_profile": layout_profile,
        "market_scope": market_scope,
        "report_type": report_type,
        "report_scope": report_scope,
        "service_targets": service_targets,
        "region_tags": region_tags,
        "asset_tags": asset_tags,
        "sector_tags": sector_tags,
        "ticker_tags": ticker_tags,
        "company_tags": company_tags,
        "recommendation": recommendation,
        "target_price": target_price,
        "previous_target_price": previous_target_price,
        "current_price": current_price,
        "price_upside_pct": round(price_upside_pct, 2),
        "stance": _stance_label(stance_value),
        "key_bullets": key_bullets,
        "risk_bullets": risk_bullets,
        "catalyst_bullets": catalyst_bullets,
        "parser_confidence": parser_quality,
        "entity_confidence": 0.8 if entities else 0.35,
        "feature_confidence": feature_confidence,
        "evidence_snippet": summary_text[:280],
        "research_scores": {
            "freshness_score": scores["freshness_score"],
            "house_quality_score": round(house_quality_score, 3),
            "parser_quality_score": round(parser_quality, 3),
            "evidence_density_score": evidence_density,
            "cross_house_agreement_score": 0.5,
            "risk_on_off_score": risk_on_off_score,
            "growth_inflation_mix_score": growth_inflation_mix_score,
            "liquidity_score": liquidity_score,
            "policy_risk_score": policy_risk_score,
            "geopolitical_risk_score": geopolitical_risk_score,
            "rates_direction_score": rates_direction_score,
            "fx_pressure_score": fx_pressure_score,
            "company_recommendation_score": company_recommendation_score,
            "target_price_upside_score": target_price_upside_score,
            "target_price_revision_score": target_price_revision_score,
            "earnings_revision_score": round(stance_value * 0.35, 3),
            "thesis_positive_score": thesis_positive_score,
            "thesis_negative_score": thesis_negative_score,
            "industry_tailwind_score": industry_tailwind_score,
            "industry_headwind_score": industry_headwind_score,
            "cross_house_dispersion_score": 0.5,
            "catalyst_near_term_score": catalyst_near_term_score,
            "valuation_language_score": valuation_language_score,
            "management_execution_signal": management_execution_signal,
            "actionability_score": round(min(1.0, catalyst_near_term_score * 0.5 + scores["freshness_score"] * 0.3 + parser_quality * 0.2), 3),
        },
        "prediction_signal": prediction_signal or {},
        "primary_ticker": primary_ticker,
        "primary_company": primary_company,
        "primary_sector": primary_sector,
        "title_clean": title_text,
        "published_at_utc": published_at_utc.astimezone(UTC).isoformat() if published_at_utc else None,
        "url": url,
    }


def _token_hits(text: str, tokens: tuple[str, ...]) -> int:
    low = (text or "").lower()
    return sum(low.count(token.lower()) for token in tokens)


def _extract_sector_tags(text: str) -> list[str]:
    low = (text or "").lower()
    return [name for name, tokens in _SECTOR_RULES.items() if any(token.lower() in low for token in tokens)][:4]


def _extract_region_tags(text: str, market_scope: str) -> list[str]:
    low = (text or "").lower()
    matched = [code for code, tokens in _REGION_RULES.items() if any(token.lower() in low for token in tokens)]
    if market_scope.upper() == "KR" and "KR" not in matched:
        matched.insert(0, "KR")
    if market_scope.upper() == "GLOBAL" and not matched:
        matched.append("GLOBAL")
    return matched[:4]


def _asset_tags(report_type: str, text: str) -> list[str]:
    low = (text or "").lower()
    tags: list[str] = []
    if report_type in {"rates", "credit"}:
        tags.append("채권")
    if report_type == "fx" or "환율" in low or "fx" in low:
        tags.append("환율")
    if report_type in {"daily_strategy", "weekly_strategy", "monthly_strategy", "macro"}:
        tags.append("주식시장")
    if "commodity" in low or "원자재" in low:
        tags.append("원자재")
    return tags[:4]


def _extract_recommendation(text: str) -> str:
    low = (text or "").lower()
    if any(token in low for token in ("buy", "매수", "비중확대", "overweight")):
        return "buy"
    if any(token in low for token in ("reduce", "avoid", "매도", "비중축소", "underweight")):
        return "reduce"
    return "neutral"


def _extract_price_fields(text: str) -> tuple[float | None, float | None, float | None]:
    target_price = _first_price_match(text, (r"목표주가\s*[:：]?\s*([0-9][0-9,]{3,})", r"target price\s*[:：]?\s*([0-9][0-9,]{3,})"))
    previous_target = _first_price_match(text, (r"기존\s*목표주가\s*[:：]?\s*([0-9][0-9,]{3,})", r"prior target\s*[:：]?\s*([0-9][0-9,]{3,})"))
    current_price = _first_price_match(text, (r"현재주가\s*[:：]?\s*([0-9][0-9,]{3,})", r"current price\s*[:：]?\s*([0-9][0-9,]{3,})"))
    return target_price, previous_target, current_price


def _first_price_match(text: str, patterns: tuple[str, ...]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            try:
                return float(match.group(1).replace(',', ''))
            except Exception:
                continue
    return None


def _stance_value(text: str, recommendation: str) -> float:
    low = (text or "").lower()
    value = 0.45 if recommendation == "buy" else -0.45 if recommendation == "reduce" else 0.0
    value += _token_hits(low, _POSITIVE_STANCE) * 0.08
    value -= _token_hits(low, _NEGATIVE_STANCE) * 0.08
    return max(-1.0, min(1.0, value))


def _report_scope(report_type: str, ticker_tags: list[str], sector_tags: list[str]) -> str:
    if report_type == "company_report" or ticker_tags:
        return "company"
    if report_type in {"sector_report", "theme_report", "real_estate"} or sector_tags:
        return "sector"
    return "market"


def _service_targets(report_type: str, report_scope: str) -> list[str]:
    targets = ["market_regime"] if report_scope == "market" else []
    if report_scope in {"company", "sector"}:
        targets.append("stock_decision")
    if report_type in {"morning_outlook", "close_outlook", "daily_strategy", "weekly_strategy", "company_report", "sector_report", "theme_report"}:
        targets.append("action_planner")
    return list(dict.fromkeys(targets or ["market_regime"]))


def _stance_label(value: float) -> str:
    if value >= 0.2:
        return "positive"
    if value <= -0.2:
        return "negative"
    return "neutral"


def _risk_on_off(report_type: str, stance_value: float, text: str) -> float:
    low = (text or "").lower()
    value = stance_value * 0.8
    if report_type in {"daily_strategy", "weekly_strategy", "monthly_strategy", "macro"}:
        value += _token_hits(low, ("risk on", "overweight equities", "reflation", "경기민감", "확장")) * 0.12
        value -= _token_hits(low, ("risk off", "defensive", "hedge", "방어주", "회피")) * 0.12
    return value


def _growth_inflation_mix(text: str) -> float:
    low = (text or "").lower()
    growth = _token_hits(low, ("growth", "성장", "확장", "수요 회복", "이익 개선"))
    inflation = _token_hits(low, ("inflation", "물가", "cpi", "pce", "inflation pressure"))
    return (growth * 0.10) - (inflation * 0.08)


def _liquidity_score(text: str) -> float:
    low = (text or "").lower()
    positive = _token_hits(low, ("liquidity", "완화", "cut", "인하", "유동성 지원", "risk appetite"))
    negative = _token_hits(low, ("tightening", "긴축", "drain", "유동성 축소", "higher for longer"))
    return (positive * 0.12) - (negative * 0.12)


def _rates_direction(text: str) -> float:
    low = (text or "").lower()
    cuts = _token_hits(low, ("rate cut", "인하", "yield lower", "금리 하락"))
    hikes = _token_hits(low, ("rate hike", "인상", "yield higher", "금리 상승"))
    return (cuts * 0.14) - (hikes * 0.14)


def _fx_pressure(text: str) -> float:
    low = (text or "").lower()
    positive = _token_hits(low, ("달러 약세", "won strength", "usd weaker", "fx stability"))
    negative = _token_hits(low, ("달러 강세", "won weakness", "usd stronger", "fx volatility"))
    return (negative * 0.14) - (positive * 0.10)


def _sentence_bullets(text: str, tokens: tuple[str, ...], limit: int) -> list[str]:
    cleaned = normalize_text_for_storage(text)
    if not cleaned:
        return []
    parts = re.split(r'(?<=[.!??])\s+', cleaned)
    out: list[str] = []
    for part in parts:
        low = part.lower()
        if any(token.lower() in low for token in tokens):
            out.append(part[:180])
        if len(out) >= limit:
            break
    return out

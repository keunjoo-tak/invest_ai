from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Any

from app.schemas.common import MarketFeatureSet
from app.services.ingestion.preprocessing import build_text_feature_snapshot


def _rsi14(closes: list[float]) -> float:
    """Calculate 14-day RSI."""
    if len(closes) < 15:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, 15):
        diff = closes[-i] - closes[-i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))
    avg_gain = sum(gains) / 14 if gains else 0.0
    avg_loss = sum(losses) / 14 if losses else 1e-9
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _pct_change(values: list[float], days: int) -> float:
    """Calculate percentage change over the given window."""
    if len(values) <= days or values[-days - 1] == 0:
        return 0.0
    return (values[-1] / values[-days - 1]) - 1


def _avg_true_range_pct(prices: list[dict], window: int = 14) -> float:
    """Calculate ATR ratio from OHLC rows."""
    if len(prices) < 2:
        return 0.0
    trs: list[float] = []
    rows = prices[-(window + 1) :]
    for idx in range(1, len(rows)):
        row = rows[idx]
        prev_close = float(rows[idx - 1]["close"] or 0.0)
        high = float(row["high"] or 0.0)
        low = float(row["low"] or 0.0)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    close = float(prices[-1]["close"] or 0.0)
    return (mean(trs) / close) if trs and close else 0.0


def _zscore(value: float, sample: list[float]) -> float:
    """Calculate z-score for a single value."""
    if len(sample) < 5:
        return 0.0
    avg = mean(sample)
    std = pstdev(sample)
    if std == 0:
        return 0.0
    return (value - avg) / std


def _safe_mean(rows: list[dict], key: str) -> float:
    values = [float(row.get(key) or 0.0) for row in rows]
    return mean(values) if values else 0.0


def _weighted_macro_mean(rows: list[dict[str, Any]], key: str, *, confidence_weighted: bool = False) -> float:
    if not rows:
        return 0.0
    weighted_sum = 0.0
    total_weight = 0.0
    for row in rows:
        value = float(row.get(key) or 0.0)
        weight = float(row.get("macro_relevance_weight") or 1.0)
        if confidence_weighted:
            weight *= float(row.get("surprise_confidence") or 0.0)
        weighted_sum += value * weight
        total_weight += weight
    return (weighted_sum / total_weight) if total_weight else 0.0


def _weighted_macro_abs_mean(rows: list[dict[str, Any]], key: str, *, confidence_weighted: bool = False) -> float:
    if not rows:
        return 0.0
    weighted_sum = 0.0
    total_weight = 0.0
    for row in rows:
        value = abs(float(row.get(key) or 0.0))
        weight = float(row.get("macro_relevance_weight") or 1.0)
        if confidence_weighted:
            weight *= float(row.get("surprise_confidence") or 0.0)
        weighted_sum += value * weight
        total_weight += weight
    return (weighted_sum / total_weight) if total_weight else 0.0


def _macro_consensus_coverage(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    weighted_confidence = 0.0
    total_weight = 0.0
    for row in rows:
        weight = float(row.get("macro_relevance_weight") or 1.0)
        weighted_confidence += weight * float(row.get("surprise_confidence") or 0.0)
        total_weight += weight
    return (weighted_confidence / total_weight) if total_weight else 0.0


def _financial_value(financials: dict, key: str) -> float:
    return round(float(financials.get(key) or 0.0), 4)


def _event_date(row: dict[str, Any]) -> date | None:
    value = row.get("publish_time_utc") or row.get("published_at")
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except Exception:
            return None
    return None


def _forward_return(closes: list[float], idx: int, step: int) -> float | None:
    if idx < 0 or idx >= len(closes) or idx + step >= len(closes) or closes[idx] == 0:
        return None
    return (closes[idx + step] / closes[idx]) - 1


def build_event_pattern_snapshot(
    as_of_date: date,
    prices: list[dict],
    news: list[dict],
    disclosures: list[dict],
) -> dict[str, Any]:
    rows = sorted(
        [dict(item) for item in disclosures + news if item.get("event_type")],
        key=lambda row: (_event_date(row) or as_of_date),
        reverse=True,
    )
    if not rows:
        return {
            "current_event_type": "",
            "sample_size": 0,
            "pattern_bias": 0.0,
            "pattern_confidence": 0.0,
            "avg_return_1d": 0.0,
            "avg_return_5d": 0.0,
            "volatility_caution_mode": False,
            "event_volatility_score": 0.0,
        }

    current = rows[0]
    current_type = str(current.get("event_type") or "general")
    current_date = _event_date(current) or as_of_date
    current_severity = float(current.get("material_disclosure_severity") or current.get("impact_score") or current.get("attention_score") or 0.0)
    price_dates = [row["trade_date"] for row in prices]
    closes = [float(row["close"] or 0.0) for row in prices]
    similar = [row for row in rows[1:] if str(row.get("event_type") or "") == current_type]
    pattern_1d: list[float] = []
    pattern_5d: list[float] = []
    for row in similar:
        event_date = _event_date(row)
        if event_date is None:
            continue
        try:
            trade_idx = next(idx for idx, trade_date in enumerate(price_dates) if trade_date >= event_date)
        except StopIteration:
            continue
        ret_1d = _forward_return(closes, trade_idx, 1)
        ret_5d = _forward_return(closes, trade_idx, 5)
        if ret_1d is not None:
            pattern_1d.append(ret_1d)
        if ret_5d is not None:
            pattern_5d.append(ret_5d)

    avg_1d = mean(pattern_1d) if pattern_1d else 0.0
    avg_5d = mean(pattern_5d) if pattern_5d else 0.0
    pattern_bias = (avg_1d * 0.6) + (avg_5d * 0.4)
    pattern_confidence = min(1.0, len(pattern_1d + pattern_5d) / 6.0)
    freshness = 1.0 if current_date >= as_of_date - timedelta(days=1) else 0.35
    volatility_score = min(1.0, current_severity * 0.55 + freshness * 0.25 + min(1.0, abs(pattern_bias) * 8.0) * 0.20)
    caution_mode = volatility_score >= 0.65 and current_type in {"earnings", "financing", "contract", "macro_policy", "supply_contract"}
    return {
        "current_event_type": current_type,
        "sample_size": len(pattern_1d + pattern_5d),
        "pattern_bias": round(pattern_bias, 4),
        "pattern_confidence": round(pattern_confidence, 3),
        "avg_return_1d": round(avg_1d, 4),
        "avg_return_5d": round(avg_5d, 4),
        "volatility_caution_mode": caution_mode,
        "event_volatility_score": round(volatility_score, 3),
    }


def build_features(
    as_of_date: date,
    prices: list[dict],
    news: list[dict],
    disclosures: list[dict],
    macro: list[dict],
    financials: dict | None = None,
    sector_momentum: dict[str, Any] | None = None,
    overnight_transmission: dict[str, Any] | None = None,
    event_pattern: dict[str, Any] | None = None,
) -> MarketFeatureSet:
    """Build market features from price, text, macro, and financial inputs."""
    closes = [float(row["close"]) for row in prices if float(row["close"]) > 0]
    volumes = [float(row["volume"]) for row in prices if float(row["volume"]) > 0]
    turnovers = [float(row["close"]) * float(row["volume"]) for row in prices if float(row["close"]) > 0 and float(row["volume"]) > 0]
    close = closes[-1]
    last_row = prices[-1]
    ma_20 = mean(closes[-20:]) if len(closes) >= 20 else close
    ma_60 = mean(closes[-60:]) if len(closes) >= 60 else close
    rsi_14 = _rsi14(closes)
    vol_20 = pstdev(closes[-20:]) / ma_20 if len(closes) >= 20 and ma_20 else 0.0
    rel_volume = (volumes[-1] / mean(volumes[-20:])) if len(volumes) >= 20 else 1.0
    turnover_z = _zscore(turnovers[-1], turnovers[-20:]) if turnovers else 0.0
    intraday_range = ((float(last_row["high"]) - float(last_row["low"])) / close) if close else 0.0

    text_snapshot = build_text_feature_snapshot(news, disclosures)
    news_sentiment = _safe_mean(news, "sentiment_score")
    disclosure_impact = _safe_mean(disclosures, "impact_score")
    macro_pressure = _weighted_macro_mean(macro, "macro_risk_score") or _weighted_macro_mean(macro, "surprise_std")
    macro_support = _weighted_macro_mean(macro, "macro_support_score")
    macro_global_score = macro_support - macro_pressure
    macro_surprise_index = _weighted_macro_mean(macro, "surprise_index", confidence_weighted=True)
    macro_surprise_abs_mean = _weighted_macro_abs_mean(macro, "surprise_index", confidence_weighted=True)
    macro_consensus_coverage = _macro_consensus_coverage(macro)
    financials = financials or {}
    sector_momentum = sector_momentum or {}
    overnight_transmission = overnight_transmission or {}
    overnight_active = bool(overnight_transmission.get("applied"))
    event_pattern = event_pattern or {}

    return MarketFeatureSet(
        as_of_date=as_of_date,
        close=round(close, 2),
        ma_20=round(ma_20, 2),
        ma_60=round(ma_60, 2),
        rsi_14=round(rsi_14, 2),
        volatility_20d=round(vol_20, 4),
        atr_14_pct=round(_avg_true_range_pct(prices), 4),
        return_1d=round(_pct_change(closes, 1), 4),
        return_5d=round(_pct_change(closes, 5), 4),
        return_20d=round(_pct_change(closes, 20), 4),
        gap_return_1d=round(((float(last_row["open"]) / float(prices[-2]["close"])) - 1) if len(prices) >= 2 and float(prices[-2]["close"]) else 0.0, 4),
        price_vs_ma20=round((close / ma_20) - 1 if ma_20 else 0.0, 4),
        price_vs_ma60=round((close / ma_60) - 1 if ma_60 else 0.0, 4),
        rel_volume=round(rel_volume, 3),
        turnover_value_zscore=round(turnover_z, 3),
        intraday_range_pct=round(intraday_range, 4),
        news_sentiment_7d=round(news_sentiment, 3),
        news_attention_score=round(text_snapshot["text_attention_score"], 3),
        text_keyword_density=round(text_snapshot["text_keyword_density"], 4),
        disclosure_impact_30d=round(disclosure_impact, 3),
        disclosure_bullish_score=round(text_snapshot["disclosure_bullish_score"], 3),
        disclosure_bearish_score=round(text_snapshot["disclosure_bearish_score"], 3),
        disclosure_net_score=round(text_snapshot["disclosure_net_score"], 3),
        material_disclosure_severity=round(text_snapshot["material_disclosure_severity"], 3),
        overnight_us_beta=round(float(overnight_transmission.get("transmission_beta") or 0.0), 4) if overnight_active else 0.0,
        overnight_us_correlation=round(float(overnight_transmission.get("transmission_corr") or 0.0), 4) if overnight_active else 0.0,
        overnight_us_index_return=round(float(overnight_transmission.get("latest_us_return") or 0.0), 4) if overnight_active else 0.0,
        overnight_us_signal=round(float(overnight_transmission.get("overnight_signal") or 0.0), 4) if overnight_active else 0.0,
        overnight_us_vol_spillover=round(float(overnight_transmission.get("volatility_spillover_score") or 0.0), 4) if overnight_active else 0.0,
        event_volatility_score=round(float(event_pattern.get("event_volatility_score") or 0.0), 3),
        event_pattern_bias=round(float(event_pattern.get("pattern_bias") or 0.0), 4),
        event_pattern_confidence=round(float(event_pattern.get("pattern_confidence") or 0.0), 3),
        supply_contract_score=round(text_snapshot["supply_signal_score"], 3),
        financing_risk_score=round(text_snapshot["financing_risk_score"], 3),
        shareholder_return_score=round(text_snapshot["shareholder_return_score"], 3),
        governance_score=round(text_snapshot["governance_score"], 3),
        earnings_event_ratio=round(text_snapshot["earnings_event_ratio"], 3),
        contract_event_ratio=round(text_snapshot["contract_event_ratio"], 3),
        macro_pressure_score=round(macro_pressure, 3),
        macro_support_score=round(macro_support, 3),
        macro_global_score=round(macro_global_score, 3),
        macro_surprise_index=round(macro_surprise_index, 3),
        macro_surprise_abs_mean=round(macro_surprise_abs_mean, 3),
        macro_consensus_coverage=round(macro_consensus_coverage, 3),
        sector_coupling_score=round(float(sector_momentum.get("sector_coupling_score") or 0.5), 3),
        sector_fund_flow_score=round(float(sector_momentum.get("sector_fund_flow_score") or 0.0), 3),
        sector_breadth_score=round(float(sector_momentum.get("sector_breadth_score") or 0.5), 3),
        sector_leader_relative_strength=round(float(sector_momentum.get("sector_leader_relative_strength") or 0.0), 4),
        revenue_growth_yoy=_financial_value(financials, "revenue_growth_yoy"),
        operating_margin=_financial_value(financials, "operating_margin"),
        net_margin=_financial_value(financials, "net_margin"),
        debt_ratio=_financial_value(financials, "debt_ratio"),
        current_ratio=_financial_value(financials, "current_ratio"),
        operating_cashflow_margin=_financial_value(financials, "operating_cashflow_margin"),
    )

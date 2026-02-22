from __future__ import annotations

from datetime import date
from statistics import mean, pstdev

from app.schemas.common import MarketFeatureSet


def _rsi14(closes: list[float]) -> float:
    if len(closes) < 15:
        return 50.0
    gains, losses = [], []
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


def build_features(as_of_date: date, prices: list[dict], news: list[dict], disclosures: list[dict], macro: list[dict]) -> MarketFeatureSet:
    closes = [row["close"] for row in prices if row["close"] > 0]
    volumes = [row["volume"] for row in prices if row["volume"] > 0]
    close = closes[-1]
    ma_20 = mean(closes[-20:]) if len(closes) >= 20 else close
    ma_60 = mean(closes[-60:]) if len(closes) >= 60 else close
    rsi_14 = _rsi14(closes)
    vol_20 = pstdev(closes[-20:]) / ma_20 if len(closes) >= 20 and ma_20 else 0.0
    rel_volume = (volumes[-1] / mean(volumes[-20:])) if len(volumes) >= 20 else 1.0
    news_sentiment = mean([n["sentiment_score"] for n in news]) if news else 0.0
    disclosure_impact = mean([d["impact_score"] for d in disclosures]) if disclosures else 0.0
    macro_pressure = mean([m.get("surprise_std") or 0.0 for m in macro]) if macro else 0.0
    return MarketFeatureSet(
        as_of_date=as_of_date,
        close=round(close, 2),
        ma_20=round(ma_20, 2),
        ma_60=round(ma_60, 2),
        rsi_14=round(rsi_14, 2),
        volatility_20d=round(vol_20, 4),
        rel_volume=round(rel_volume, 3),
        news_sentiment_7d=round(news_sentiment, 3),
        disclosure_impact_30d=round(disclosure_impact, 3),
        macro_pressure_score=round(macro_pressure, 3),
    )

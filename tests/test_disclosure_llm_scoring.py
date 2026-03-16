from datetime import date

from app.services.features.feature_builder import build_features
from app.services.ingestion.preprocessing import enrich_disclosure_records
from app.services.llm.gemini_client import GeminiClient
from app.services.signal.scorer import evaluate_signal


def _prices() -> list[dict]:
    rows = []
    base = 100.0
    for idx in range(40):
        close = base + idx
        rows.append({
            "trade_date": date(2026, 3, min(idx + 1, 28)),
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 100000 + idx * 1000,
        })
    return rows


def test_material_disclosure_scoring_fallback_distinguishes_positive_and_negative() -> None:
    client = GeminiClient()
    docs = [
        {"title": "Large supply contract signed", "content_text": "new long-term contract and customer order"},
        {"title": "Convertible bond issuance", "content_text": "operating fund financing through CB issuance"},
    ]

    scored = client._fallback_material_disclosure_scores(docs)

    assert scored[0]["bullish_score"] > scored[0]["bearish_score"]
    assert scored[1]["bearish_score"] > scored[1]["bullish_score"]


def test_disclosure_scoring_is_reflected_in_features_and_signal() -> None:
    disclosures = enrich_disclosure_records(
        [
            {
                "title": "Convertible bond issuance",
                "content_text": "operating fund financing through convertible bond issuance",
                "impact_score": 0.2,
                "publish_time_utc": None,
                "event_type": "general",
            }
        ],
        llm_signals=[],
        llm_disclosure_scores=[
            {
                "title": "Convertible bond issuance",
                "bullish_score": 0.1,
                "bearish_score": 0.9,
                "net_score": -0.8,
                "event_severity": 0.9,
                "event_label": "financing",
                "rationale": "dilution risk",
            }
        ],
    )
    features = build_features(date(2026, 3, 14), _prices(), [], disclosures, [], financials={}, sector_momentum={})
    signal = evaluate_signal(features)

    assert features.disclosure_bearish_score >= 0.8
    assert features.disclosure_net_score < 0
    assert "DISCLOSURE_BEARISH" in signal.risk_flags

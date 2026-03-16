from datetime import date

from app.services.features.feature_builder import build_features
from app.services.ingestion.providers import SourceProviderClient
from app.services.signal.scorer import evaluate_signal


def _price_rows() -> list[dict]:
    rows = []
    base = 100.0
    for idx in range(30):
        close = base + idx
        rows.append(
            {
                "trade_date": date(2026, 2, 1),
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000 + idx * 10,
            }
        )
    return rows


def test_build_macro_row_uses_market_oriented_surprise_index() -> None:
    client = SourceProviderClient()
    inflation_row = client._build_macro_row(
        as_of_date=date(2026, 3, 14),
        observation_date=date(2026, 3, 12),
        country="US",
        indicator_name="US_CPI_INDEX",
        actual=3.4,
        consensus=3.1,
        directional_interpretation="inflation_up_risk",
        source_meta={"provider": "BLS"},
        consensus_source="expected",
        surprise_bias="risk_up",
    )
    growth_row = client._build_macro_row(
        as_of_date=date(2026, 3, 14),
        observation_date=date(2026, 3, 12),
        country="US",
        indicator_name="US_NONFARM_PAYROLLS",
        actual=250.0,
        consensus=210.0,
        directional_interpretation="growth_support",
        source_meta={"provider": "BLS"},
        consensus_source="expected",
        surprise_bias="support_up",
    )

    assert inflation_row["surprise_raw"] == 0.3
    assert inflation_row["consensus_source"] == "expected"
    assert inflation_row["surprise_index"] < 0
    assert growth_row["surprise_index"] > 0


def test_build_features_aggregates_macro_surprise_metrics() -> None:
    features = build_features(
        as_of_date=date(2026, 3, 14),
        prices=_price_rows(),
        news=[],
        disclosures=[],
        macro=[
            {
                "macro_relevance_weight": 1.0,
                "macro_risk_score": 0.4,
                "macro_support_score": 0.0,
                "surprise_index": -0.9,
                "surprise_confidence": 1.0,
                "surprise_std": 0.9,
            },
            {
                "macro_relevance_weight": 0.9,
                "macro_risk_score": 0.0,
                "macro_support_score": 0.5,
                "surprise_index": 0.6,
                "surprise_confidence": 0.65,
                "surprise_std": 0.6,
            },
            {
                "macro_relevance_weight": 0.7,
                "macro_risk_score": 0.0,
                "macro_support_score": 0.2,
                "surprise_index": 0.0,
                "surprise_confidence": 0.0,
                "surprise_std": 0.0,
            },
        ],
        financials={},
    )

    assert features.macro_surprise_index < 0
    assert features.macro_surprise_abs_mean > 0
    assert 0 < features.macro_consensus_coverage < 1


def test_signal_scorer_flags_macro_surprise_risk() -> None:
    features = build_features(
        as_of_date=date(2026, 3, 14),
        prices=_price_rows(),
        news=[],
        disclosures=[],
        macro=[
            {
                "macro_relevance_weight": 1.0,
                "macro_risk_score": 0.8,
                "macro_support_score": 0.0,
                "surprise_index": -1.2,
                "surprise_confidence": 1.0,
                "surprise_std": 1.2,
            }
        ],
        financials={},
    )

    result = evaluate_signal(features)
    assert "MACRO_SURPRISE_RISK" in result.risk_flags

from datetime import date

from app.services.ingestion.batch_ingestor import BatchIngestor
from app.services.ingestion.providers import SourceProviderClient


def test_build_macro_row_sets_surprise_std() -> None:
    client = SourceProviderClient()
    row = client._build_macro_row(
        as_of_date=date(2026, 3, 12),
        observation_date=date(2026, 3, 1),
        country="US",
        indicator_name="US_FED_FUNDS_RATE",
        actual=4.5,
        consensus=4.25,
        directional_interpretation="rate_up_risk",
        source_meta={"provider": "FRED"},
    )
    assert row["country"] == "US"
    assert row["indicator_name"] == "US_FED_FUNDS_RATE"
    assert row["surprise_std"] > 0
    assert row["source_meta"]["provider"] == "FRED"


def test_render_macro_snapshot_text_contains_indicator_values() -> None:
    ing = BatchIngestor()
    text = ing._render_macro_snapshot_text(
        "글로벌 거시 브리핑",
        [
            {
                "indicator_name": "US_CPI_INDEX",
                "actual": 312.2,
                "consensus": 311.8,
                "surprise_std": 0.4,
                "directional_interpretation": "inflation_up_risk",
                "content_text": "미국 CPI가 전월 대비 재상승했다.",
            }
        ],
    )
    assert "US_CPI_INDEX" in text
    assert "actual=312.2" in text
    assert "inflation_up_risk" in text

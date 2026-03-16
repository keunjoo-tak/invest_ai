from app.services.ingestion.providers import SourceProviderClient


def test_extract_statement_metrics_from_dart_rows() -> None:
    client = SourceProviderClient()
    rows = [
        {"account_nm": "매출액", "thstrm_amount": "1000", "frmtrm_amount": "800"},
        {"account_nm": "영업이익", "thstrm_amount": "120", "frmtrm_amount": "90"},
        {"account_nm": "당기순이익", "thstrm_amount": "80", "frmtrm_amount": "60"},
        {"account_nm": "자산총계", "thstrm_amount": "2500", "frmtrm_amount": "2300"},
        {"account_nm": "부채총계", "thstrm_amount": "1000", "frmtrm_amount": "1100"},
        {"account_nm": "자본총계", "thstrm_amount": "1500", "frmtrm_amount": "1200"},
        {"account_nm": "유동자산", "thstrm_amount": "900", "frmtrm_amount": "850"},
        {"account_nm": "유동부채", "thstrm_amount": "500", "frmtrm_amount": "520"},
        {"account_nm": "영업활동현금흐름", "thstrm_amount": "140", "frmtrm_amount": "100"},
    ]

    metrics = client._extract_statement_metrics(rows)

    assert metrics["revenue_growth_yoy"] == 0.25
    assert metrics["operating_margin"] == 0.12
    assert metrics["net_margin"] == 0.08
    assert round(metrics["debt_ratio"], 4) == 0.6667
    assert metrics["current_ratio"] == 1.8
    assert metrics["operating_cashflow_margin"] == 0.14

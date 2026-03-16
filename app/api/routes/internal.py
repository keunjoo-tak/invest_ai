from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.ingestion import (
    CollectExternalBundleResponse,
    IngestionProbeResponse,
    InstrumentSearchCandidate,
    InstrumentSearchRequest,
    InstrumentSearchResponse,
    TickerIngestionRequest,
    XRecentSearchRequest,
)
from app.services.ingestion.providers import SourceProviderClient

router = APIRouter(prefix="/internal", tags=["internal"])
providers = SourceProviderClient()


def _now() -> datetime:
    """동작 설명은 인수인계 문서를 참고하세요."""
    return datetime.now(timezone.utc)


@router.post(
    "/jobs/recompute-features",
    summary="피처 재계산 작업 트리거(샘플)",
    description="현재는 샘플 구현으로 매크로 스냅샷 건수만 반환합니다. 이후 큐 기반 작업 트리거로 확장 예정입니다.",
)
def recompute_features() -> dict:
    """동작 설명은 인수인계 문서를 참고하세요."""
    sample = providers.fetch_macro(date.today())
    return {"status": "queued", "macro_rows": len(sample)}


@router.post(
    "/ingestion/instrument/resolve",
    response_model=IngestionProbeResponse,
    summary="종목 식별/매핑 확인",
    description="입력된 티커/종목명을 내부 종목 식별 로직으로 정규화하여 매핑 결과를 반환합니다.",
)
def resolve_instrument(req: TickerIngestionRequest) -> IngestionProbeResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    profile = providers.resolve_instrument(req.ticker_or_name)
    return IngestionProbeResponse(
        source="instrument_resolver",
        success=True,
        as_of_utc=_now(),
        item_count=1,
        details={"ticker": profile.ticker, "name_kr": profile.name_kr, "market": profile.market, "sector": profile.sector},
        sample=[{"ticker": profile.ticker, "name_kr": profile.name_kr}],
    )


@router.post(
    "/ingestion/instrument/search",
    response_model=InstrumentSearchResponse,
    summary="종목명/티커 후보 검색",
    description=(
        "자연어 종목명 또는 티커 일부를 입력하면 텍스트 유사도 기반으로 "
        "공식 종목명과 티커 후보 목록을 반환합니다."
    ),
)
def search_instrument_candidates(req: InstrumentSearchRequest) -> InstrumentSearchResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    candidates = providers.search_instruments(req.query, limit=req.limit)
    normalized_query = providers._norm_text(req.query)
    return InstrumentSearchResponse(
        query=req.query,
        normalized_query=normalized_query,
        item_count=len(candidates),
        candidates=[InstrumentSearchCandidate(**row) for row in candidates],
    )


@router.post(
    "/ingestion/price/kis/daily",
    response_model=IngestionProbeResponse,
    summary="KIS 일봉 수집 프로브",
    description="KIS OpenAPI를 통해 일봉 가격 데이터를 수집하고 샘플 응답을 반환합니다.",
)
def probe_kis_daily_price(req: TickerIngestionRequest) -> IngestionProbeResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    as_of_date = req.as_of_date or date.today()
    profile = providers.resolve_instrument(req.ticker_or_name)
    rows = providers._fetch_price_daily_kis(profile.ticker, as_of_date, req.lookback_days)
    return IngestionProbeResponse(
        source="kis_daily_price",
        success=bool(rows),
        as_of_utc=_now(),
        item_count=len(rows),
        details={"ticker": profile.ticker, "base_url_selected": providers._kis_base_url_selected},
        sample=[
            {
                "trade_date": str(x["trade_date"]),
                "open": x["open"],
                "high": x["high"],
                "low": x["low"],
                "close": x["close"],
                "volume": x["volume"],
            }
            for x in rows[: min(3, len(rows))]
        ],
    )


@router.post(
    "/ingestion/news/naver",
    response_model=IngestionProbeResponse,
    summary="NAVER 뉴스 수집 프로브",
    description="NAVER 뉴스 검색 API로 종목 관련 뉴스 목록을 조회하고 샘플 응답을 반환합니다.",
)
def probe_naver_news(req: TickerIngestionRequest) -> IngestionProbeResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    profile = providers.resolve_instrument(req.ticker_or_name)
    rows = providers._fetch_news_naver(profile.ticker, max_items=req.max_items)
    return IngestionProbeResponse(
        source="naver_news",
        success=bool(rows),
        as_of_utc=_now(),
        item_count=len(rows),
        details={"ticker": profile.ticker},
        sample=[
            {
                "title": x["title"],
                "url": x["url"],
                "publish_time_utc": x["publish_time_utc"].isoformat(),
            }
            for x in rows[: min(3, len(rows))]
        ],
    )


@router.post(
    "/ingestion/disclosures/dart/corp-code-map",
    response_model=IngestionProbeResponse,
    summary="DART 티커→corp_code 매핑 확인",
    description="OPENDART corpCode.xml 기준으로 입력 종목의 corp_code 매핑 결과를 반환합니다.",
)
def probe_dart_corp_code(req: TickerIngestionRequest) -> IngestionProbeResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    profile = providers.resolve_instrument(req.ticker_or_name)
    mapping = providers._load_dart_corp_code_map()
    corp_code = mapping.get(profile.ticker, "")
    return IngestionProbeResponse(
        source="dart_corp_code_map",
        success=bool(corp_code),
        as_of_utc=_now(),
        item_count=1 if corp_code else 0,
        details={"ticker": profile.ticker, "corp_code": corp_code, "mapping_size": len(mapping)},
        sample=[{"ticker": profile.ticker, "corp_code": corp_code}] if corp_code else [],
    )


@router.post(
    "/ingestion/disclosures/dart/list",
    response_model=IngestionProbeResponse,
    summary="DART 공시 목록 수집 프로브",
    description="OPENDART 공시 목록 API로 종목 공시를 조회하고 샘플 응답을 반환합니다.",
)
def probe_dart_disclosures(req: TickerIngestionRequest) -> IngestionProbeResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    as_of_date = req.as_of_date or date.today()
    profile = providers.resolve_instrument(req.ticker_or_name)
    rows = providers._fetch_disclosures_dart(profile.ticker, as_of_date, req.days)
    return IngestionProbeResponse(
        source="dart_disclosures",
        success=bool(rows),
        as_of_utc=_now(),
        item_count=len(rows),
        details={"ticker": profile.ticker, "days": req.days},
        sample=[
            {
                "source_disclosure_id": x["source_disclosure_id"],
                "title": x["title"],
                "publish_time_utc": x["publish_time_utc"].isoformat(),
            }
            for x in rows[: min(5, len(rows))]
        ],
    )


@router.post(
    "/ingestion/macro/snapshot",
    response_model=IngestionProbeResponse,
    summary="매크로 스냅샷 확인",
    description="현재 시점 매크로 입력 데이터(샘플 구현)를 반환합니다.",
)
def probe_macro_snapshot(req: TickerIngestionRequest) -> IngestionProbeResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    as_of_date = req.as_of_date or date.today()
    rows = providers.fetch_macro(as_of_date)
    return IngestionProbeResponse(
        source="macro_snapshot",
        success=bool(rows),
        as_of_utc=_now(),
        item_count=len(rows),
        details={"as_of_date": str(as_of_date)},
        sample=rows[: min(5, len(rows))],
    )


@router.post(
    "/ingestion/macro/bok",
    response_model=IngestionProbeResponse,
    summary="BOK ECOS 핵심지표 수집 진단",
    description="한국은행 ECOS KeyStatisticList API를 호출해 환율, 금리, 유동성 등 핵심 거시지표 수집 결과를 반환합니다.",
)
def probe_bok_macro(req: TickerIngestionRequest) -> IngestionProbeResponse:
    """BOK ECOS 기반 거시지표 수집 상태를 확인한다."""
    as_of_date = req.as_of_date or date.today()
    rows = providers._fetch_macro_bok(as_of_date)
    return IngestionProbeResponse(
        source="bok_ecos_macro",
        success=bool(rows),
        as_of_utc=_now(),
        item_count=len(rows),
        details={"as_of_date": str(as_of_date)},
        sample=rows[: min(5, len(rows))],
    )


@router.post(
    "/ingestion/macro/kosis",
    response_model=IngestionProbeResponse,
    summary="KOSIS 메타데이터 수집 진단",
    description="KOSIS OpenAPI 검색 결과를 활용해 CPI, 실업률, 산업생산, 수출 관련 최신 통계 메타데이터 수집 결과를 반환합니다.",
)
def probe_kosis_macro(req: TickerIngestionRequest) -> IngestionProbeResponse:
    """KOSIS 기반 거시 보조지표 수집 상태를 확인한다."""
    as_of_date = req.as_of_date or date.today()
    rows = providers._fetch_macro_kosis(as_of_date)
    return IngestionProbeResponse(
        source="kosis_macro_search",
        success=bool(rows),
        as_of_utc=_now(),
        item_count=len(rows),
        details={"as_of_date": str(as_of_date)},
        sample=rows[: min(5, len(rows))],
    )



@router.post(
    "/ingestion/macro/fred",
    response_model=IngestionProbeResponse,
    summary="FRED 거시지표 수집 진단",
    description="FRED API를 호출해 금리, 고용, 시장, 성장 지표를 정규화된 형태로 반환합니다.",
)
def probe_fred_macro(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers._fetch_macro_fred(as_of_date)
    return IngestionProbeResponse(source="fred_macro", success=bool(rows), as_of_utc=_now(), item_count=len(rows), details={"as_of_date": str(as_of_date)}, sample=rows[: min(5, len(rows))])


@router.post(
    "/ingestion/macro/bls",
    response_model=IngestionProbeResponse,
    summary="BLS 거시지표 수집 진단",
    description="BLS Public Data API를 호출해 CPI, 실업률, 비농업고용 지표를 정규화된 형태로 반환합니다.",
)
def probe_bls_macro(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers._fetch_macro_bls(as_of_date)
    return IngestionProbeResponse(source="bls_macro", success=bool(rows), as_of_utc=_now(), item_count=len(rows), details={"as_of_date": str(as_of_date)}, sample=rows[: min(5, len(rows))])


@router.post(
    "/ingestion/macro/bea",
    response_model=IngestionProbeResponse,
    summary="BEA 거시지표 수집 진단",
    description="BEA API를 호출해 GDP와 PCE 지표를 정규화된 형태로 반환합니다.",
)
def probe_bea_macro(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers._fetch_macro_bea(as_of_date)
    return IngestionProbeResponse(source="bea_macro", success=bool(rows), as_of_utc=_now(), item_count=len(rows), details={"as_of_date": str(as_of_date)}, sample=rows[: min(5, len(rows))])


@router.post(
    "/ingestion/macro/fiscaldata",
    response_model=IngestionProbeResponse,
    summary="Fiscal Data 수집 진단",
    description="미국 재무부 Fiscal Data API를 호출해 국가부채와 재정수지 지표를 정규화된 형태로 반환합니다.",
)
def probe_fiscaldata_macro(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers._fetch_macro_fiscaldata(as_of_date)
    return IngestionProbeResponse(source="fiscaldata_macro", success=bool(rows), as_of_utc=_now(), item_count=len(rows), details={"as_of_date": str(as_of_date)}, sample=rows[: min(5, len(rows))])


@router.post(
    "/ingestion/macro/oecd",
    response_model=IngestionProbeResponse,
    summary="OECD 거시지표 수집 진단",
    description="OECD 거시지표를 수집하고 정규화된 스냅샷 행으로 반환합니다.",
)
def probe_oecd_macro(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers._fetch_macro_oecd(as_of_date)
    return IngestionProbeResponse(source="oecd_macro", success=bool(rows), as_of_utc=_now(), item_count=len(rows), details={"as_of_date": str(as_of_date)}, sample=rows[: min(5, len(rows))])


@router.post(
    "/ingestion/macro/worldbank",
    response_model=IngestionProbeResponse,
    summary="World Bank 거시지표 수집 진단",
    description="World Bank API에서 미국, 유럽, 글로벌 거시지표를 수집합니다.",
)
def probe_worldbank_macro(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers._fetch_macro_world_bank(as_of_date)
    return IngestionProbeResponse(source="worldbank_macro", success=bool(rows), as_of_utc=_now(), item_count=len(rows), details={"as_of_date": str(as_of_date)}, sample=rows[: min(5, len(rows))])


@router.post(
    "/ingestion/macro/imf",
    response_model=IngestionProbeResponse,
    summary="IMF 거시지표 수집 진단",
    description="IMF DataMapper API에서 국제 성장률과 물가 지표를 수집합니다.",
)
def probe_imf_macro(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers._fetch_macro_imf(as_of_date)
    return IngestionProbeResponse(source="imf_macro", success=bool(rows), as_of_utc=_now(), item_count=len(rows), details={"as_of_date": str(as_of_date)}, sample=rows[: min(5, len(rows))])


@router.post(
    "/ingestion/macro/eurostat",
    response_model=IngestionProbeResponse,
    summary="Eurostat 거시지표 수집 진단",
    description="Eurostat에서 유로존 물가, 실업률, 산업생산 지표를 수집합니다.",
)
def probe_eurostat_macro(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers._fetch_macro_eurostat(as_of_date)
    return IngestionProbeResponse(source="eurostat_macro", success=bool(rows), as_of_utc=_now(), item_count=len(rows), details={"as_of_date": str(as_of_date)}, sample=rows[: min(5, len(rows))])


@router.post(
    "/ingestion/disclosures/dart/financial-statements",
    response_model=IngestionProbeResponse,
    summary="OpenDART 재무제표 수집 진단",
    description="OpenDART 단일회사 주요계정 API를 호출해 분석에 사용할 수 있는 재무 지표를 반환합니다.",
)
def probe_dart_financial_statements(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    profile = providers.resolve_instrument(req.ticker_or_name)
    row = providers.fetch_financial_statements(profile.ticker, as_of_date)
    return IngestionProbeResponse(source="dart_financial_statements", success=bool(row), as_of_utc=_now(), item_count=1 if row else 0, details={"ticker": profile.ticker, "as_of_date": str(as_of_date)}, sample=[{k: v for k, v in row.items() if k != "raw_rows"}] if row else [])


@router.post(
    "/ingestion/event-stream/official-calendar",
    response_model=IngestionProbeResponse,
    summary="공식 이벤트 캘린더 스트림 진단",
    description="Fed, ECB, Eurostat, NBS 등 공식 기관의 캘린더 항목을 수집합니다.",
)
def probe_official_event_stream(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers.fetch_official_event_stream(as_of_date, horizon_days=req.days)
    return IngestionProbeResponse(source="official_event_stream", success=bool(rows), as_of_utc=_now(), item_count=len(rows), details={"as_of_date": str(as_of_date), "horizon_days": req.days}, sample=rows[: min(5, len(rows))])


@router.post(
    "/ingestion/event-stream/broad-issue",
    response_model=IngestionProbeResponse,
    summary="광범위 이슈 스트림 진단",
    description="GDELT와 공식 기관 발표문을 수집해 광범위 이슈 스트림을 구성합니다.",
)
def probe_broad_issue_stream(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers.fetch_broad_issue_stream(as_of_date, lookback_days=req.days)
    return IngestionProbeResponse(source="broad_issue_stream", success=bool(rows), as_of_utc=_now(), item_count=len(rows), details={"as_of_date": str(as_of_date), "lookback_days": req.days}, sample=[{"title": str(x.get("title") or ""), "url": str(x.get("url") or ""), "publish_time_utc": str(x.get("publish_time_utc") or "")} for x in rows[: min(5, len(rows))]])


@router.post(
    "/ingestion/news/newsapi",
    response_model=IngestionProbeResponse,
    summary="NewsAPI 글로벌 뉴스 수집 진단",
    description="NewsAPI를 호출해 종목 관련 글로벌 뉴스 또는 거시/섹터 뉴스 수집 결과를 반환합니다.",
)
def probe_newsapi(req: TickerIngestionRequest) -> IngestionProbeResponse:
    """NewsAPI 기반 글로벌 뉴스 수집 상태를 확인한다."""
    profile = providers.resolve_instrument(req.ticker_or_name)
    rows = providers._fetch_news_newsapi(profile.ticker, max_items=req.max_items, include_content=False)
    return IngestionProbeResponse(
        source="newsapi_everything",
        success=bool(rows),
        as_of_utc=_now(),
        item_count=len(rows),
        details={"ticker": profile.ticker},
        sample=[
            {
                "title": x["title"],
                "url": x["url"],
                "publish_time_utc": x["publish_time_utc"].isoformat(),
            }
            for x in rows[: min(5, len(rows))]
        ],
    )


@router.post(
    "/ingestion/social/x/recent-search",
    response_model=IngestionProbeResponse,
    summary="X Recent Search 프로브",
    description="X API 최근 검색을 호출하고 응답/에러(크레딧 부족 등)를 진단합니다.",
)
def probe_x_recent_search(req: XRecentSearchRequest) -> IngestionProbeResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    settings = get_settings()
    token = (settings.x_bearer_token or "").strip()
    if not token:
        return IngestionProbeResponse(
            source="x_recent_search",
            success=False,
            as_of_utc=_now(),
            details={"reason": "X_BEARER_TOKEN missing"},
        )
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "query": req.query,
        "max_results": req.max_results,
        "tweet.fields": "created_at,author_id,lang,public_metrics",
    }
    try:
        resp = httpx.get("https://api.twitter.com/2/tweets/search/recent", headers=headers, params=params, timeout=20.0)
        body = resp.json() if "application/json" in resp.headers.get("content-type", "") else {"raw": resp.text[:800]}
        tweets = body.get("data", []) if isinstance(body, dict) else []
        return IngestionProbeResponse(
            source="x_recent_search",
            success=resp.is_success,
            as_of_utc=_now(),
            item_count=len(tweets),
            details={
                "http_status": resp.status_code,
                "query": req.query,
                "error_title": body.get("title") if isinstance(body, dict) else None,
                "error_detail": body.get("detail") if isinstance(body, dict) else None,
            },
            sample=tweets[: min(3, len(tweets))] if isinstance(tweets, list) else [],
        )
    except Exception as exc:
        return IngestionProbeResponse(
            source="x_recent_search",
            success=False,
            as_of_utc=_now(),
            details={"error_type": type(exc).__name__, "error": str(exc)[:300]},
        )


@router.post(
    "/ingestion/event-stream/official-calendar",
    response_model=IngestionProbeResponse,
    summary="공식 이벤트 캘린더 스트림 진단",
    description="Fed, ECB, Eurostat, NBS 등 공식 기관의 캘린더 항목을 수집합니다.",
)
def probe_official_event_stream(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers.fetch_official_event_stream(as_of_date, horizon_days=req.days)
    return IngestionProbeResponse(
        source="official_event_stream",
        success=bool(rows),
        as_of_utc=_now(),
        item_count=len(rows),
        details={"as_of_date": str(as_of_date), "horizon_days": req.days},
        sample=rows[: min(5, len(rows))],
    )


@router.post(
    "/ingestion/event-stream/broad-issue",
    response_model=IngestionProbeResponse,
    summary="광범위 이슈 스트림 진단",
    description="GDELT와 공식 기관 발표문을 수집해 광범위 이슈 스트림을 구성합니다.",
)
def probe_broad_issue_stream(req: TickerIngestionRequest) -> IngestionProbeResponse:
    as_of_date = req.as_of_date or date.today()
    rows = providers.fetch_broad_issue_stream(as_of_date, lookback_days=req.days)
    return IngestionProbeResponse(
        source="broad_issue_stream",
        success=bool(rows),
        as_of_utc=_now(),
        item_count=len(rows),
        details={"as_of_date": str(as_of_date), "lookback_days": req.days},
        sample=[
            {"title": str(x.get("title") or ""), "url": str(x.get("url") or ""), "publish_time_utc": str(x.get("publish_time_utc") or "")}
            for x in rows[: min(5, len(rows))]
        ],
    )


@router.post(
    "/ingestion/collect-external-bundle",
    response_model=CollectExternalBundleResponse,
    summary="외부 수집 번들 점검(KIS/NAVER/DART/매크로)",
    description="외부 수집 단계를 한 번에 실행하는 진단용 엔드포인트입니다.",
)
def collect_external_bundle(req: TickerIngestionRequest) -> CollectExternalBundleResponse:
    """동작 설명은 인수인계 문서를 참고하세요."""
    as_of_date = req.as_of_date or date.today()
    profile = providers.resolve_instrument(req.ticker_or_name)

    kis_rows = providers._fetch_price_daily_kis(profile.ticker, as_of_date, req.lookback_days)
    naver_rows = providers._fetch_news_naver(profile.ticker, max_items=req.max_items)
    dart_map = providers._load_dart_corp_code_map()
    dart_rows = providers._fetch_disclosures_dart(profile.ticker, as_of_date, req.days)
    macro_rows = providers.fetch_macro(as_of_date)

    return CollectExternalBundleResponse(
        ticker=profile.ticker,
        instrument_name=profile.name_kr,
        as_of_date=as_of_date,
        sources=[
            IngestionProbeResponse(
                source="kis_daily_price",
                success=bool(kis_rows),
                used_fallback=False,
                as_of_utc=_now(),
                item_count=len(kis_rows),
                details={"base_url_selected": providers._kis_base_url_selected},
                sample=[{"trade_date": str(x["trade_date"]), "close": x["close"], "volume": x["volume"]} for x in kis_rows[:3]],
            ),
            IngestionProbeResponse(
                source="naver_news",
                success=bool(naver_rows),
                used_fallback=False,
                as_of_utc=_now(),
                item_count=len(naver_rows),
                sample=[{"title": x["title"], "url": x["url"]} for x in naver_rows[:3]],
            ),
            IngestionProbeResponse(
                source="dart_corp_code_map",
                success=profile.ticker in dart_map,
                as_of_utc=_now(),
                item_count=1 if profile.ticker in dart_map else 0,
                details={"corp_code": dart_map.get(profile.ticker, ""), "mapping_size": len(dart_map)},
                sample=[{"ticker": profile.ticker, "corp_code": dart_map.get(profile.ticker, "")}] if profile.ticker in dart_map else [],
            ),
            IngestionProbeResponse(
                source="dart_disclosures",
                success=bool(dart_rows),
                as_of_utc=_now(),
                item_count=len(dart_rows),
                sample=[{"title": x["title"], "source_disclosure_id": x["source_disclosure_id"]} for x in dart_rows[:3]],
            ),
            IngestionProbeResponse(
                source="macro_snapshot",
                success=bool(macro_rows),
                as_of_utc=_now(),
                item_count=len(macro_rows),
                sample=macro_rows[:3],
            ),
        ],
    )

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceCatalogItem:
    """데이터소스 카탈로그 항목."""

    source_id: str
    name: str
    category: str
    url: str
    collection_mode: str
    parser_required: bool


SOURCE_CATALOG: list[SourceCatalogItem] = [
    SourceCatalogItem("S05", "OpenDART", "공시", "https://opendart.fss.or.kr", "api", True),
    SourceCatalogItem("S06", "KRX KIND", "공시/IR", "https://kind.krx.co.kr", "crawler", True),
    SourceCatalogItem("S08", "Naver News API", "뉴스", "https://developers.naver.com/docs/serviceapi/search/news/news.md", "api", True),
    SourceCatalogItem("S12", "X API v2", "소셜", "https://developer.x.com/en/docs/x-api", "api", True),
    SourceCatalogItem("S13", "ECOS", "거시", "https://ecos.bok.or.kr/api/", "api", False),
    SourceCatalogItem("S15", "통계청 보도자료", "거시/보도자료", "https://kostat.go.kr", "crawler", True),
    SourceCatalogItem("S16", "한국은행 보도자료", "거시/보도자료", "https://www.bok.or.kr", "crawler", True),
    SourceCatalogItem("S18", "BLS CPI Release", "글로벌거시", "https://www.bls.gov/news.release/cpi.htm", "crawler", True),
    SourceCatalogItem("S20", "BEA Schedule", "캘린더", "https://www.bea.gov/news/schedule", "crawler", True),
    SourceCatalogItem("S27", "BLS Schedule", "캘린더", "https://www.bls.gov/schedule/news_release/", "crawler", True),
    SourceCatalogItem("S28", "정책브리핑", "정책", "https://www.korea.kr/news/policyNewsList.do", "crawler", True),
    SourceCatalogItem("S29", "기업 IR 사이트", "기업문서", "https://example.com/ir-registry", "crawler", True),
]


def get_source_item(source_id: str) -> SourceCatalogItem | None:
    """ID로 카탈로그를 조회한다."""
    key = (source_id or "").strip().upper()
    for item in SOURCE_CATALOG:
        if item.source_id == key:
            return item
    return None

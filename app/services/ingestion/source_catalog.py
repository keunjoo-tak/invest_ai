from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceCatalogItem:
    """Source catalog item."""

    source_id: str
    name: str
    category: str
    url: str
    collection_mode: str
    parser_required: bool


SOURCE_CATALOG: list[SourceCatalogItem] = [
    SourceCatalogItem("S05", "OpenDART", "Disclosure and Financials", "https://opendart.fss.or.kr", "api", True),
    SourceCatalogItem("S06", "KRX KIND", "Disclosure and IR", "https://kind.krx.co.kr", "crawler", True),
    SourceCatalogItem("S08", "Naver News API", "News", "https://developers.naver.com/docs/serviceapi/search/news/news.md", "api", True),
    SourceCatalogItem("S09", "NewsAPI", "Global News", "https://newsapi.org/docs", "api", True),
    SourceCatalogItem("S12", "X API v2", "Social", "https://developer.x.com/en/docs/x-api", "api", True),
    SourceCatalogItem("S13", "BOK ECOS", "Domestic Macro", "https://ecos.bok.or.kr/api/", "api", False),
    SourceCatalogItem("S14", "KOSIS OpenAPI", "Domestic Macro and Stats", "https://kosis.kr/openapi/", "api", False),
    SourceCatalogItem("S16", "BOK Publications", "Domestic Macro Documents", "https://www.bok.or.kr", "crawler", True),
    SourceCatalogItem("S18", "BLS API", "US Macro", "https://www.bls.gov/developers/", "api", False),
    SourceCatalogItem("S20", "BEA API", "US Macro", "https://www.bea.gov/resources/developer", "api", False),
    SourceCatalogItem("S28", "Policy Briefing", "Policy", "https://www.korea.kr/news/policyNewsList.do", "crawler", True),
    SourceCatalogItem("S30", "OECD", "International Macro", "https://www.oecd.org/newsroom/", "api", True),
    SourceCatalogItem("S31", "FRED API", "US Rates and Markets", "https://fred.stlouisfed.org/docs/api/fred/", "api", False),
    SourceCatalogItem("S34", "Fiscal Data API", "US Fiscal", "https://fiscaldata.treasury.gov/api-documentation/", "api", False),
    SourceCatalogItem("S35", "Official Event Calendar", "Global Events", "https://www.federalreserve.gov/", "crawler", True),
    SourceCatalogItem("S36", "Broad Issue Stream", "Global Issues", "https://api.gdeltproject.org/", "api", True),
    SourceCatalogItem("S37", "World Bank API", "International Macro", "https://api.worldbank.org/", "api", False),
    SourceCatalogItem("S38", "IMF DataMapper API", "International Macro", "https://www.imf.org/external/datamapper/", "api", False),
    SourceCatalogItem("S39", "Eurostat API", "Europe Macro", "https://ec.europa.eu/eurostat/api/", "api", False),
    SourceCatalogItem("S40", "Naver News Section Headlines", "Domestic Headline News", "https://news.naver.com", "crawler", True),
    SourceCatalogItem("S41", "Samsung Securities Research", "Domestic Broker Research", "https://www.samsungpop.com/sscommon/jsp/search/research/research_pop.jsp", "crawler", True),
    SourceCatalogItem("S42", "KB Financial Research", "Domestic Bank Research", "https://www.kbfg.com/kbresearch/report/reportList.do", "crawler", True),
    SourceCatalogItem("S43", "Hana Institute of Finance", "Domestic Bank Research", "https://www.hanaif.re.kr/boardList.do?menuId=&tabMenuId=MN2100", "crawler", True),
    SourceCatalogItem("S44", "Woori Financial Research Institute", "Domestic Bank Research", "https://www.wfri.re.kr/ko/mo/research_report/research_report.php", "crawler", True),
    SourceCatalogItem("S45", "UBS CIO Insights", "Global Public Research", "https://www.ubs.com/global/en/wealthmanagement/insights.html", "crawler", True),
    SourceCatalogItem("S46", "BlackRock BII Outlook", "Global Public Research", "https://www.blackrock.com/us/individual/insights/blackrock-investment-institute/outlook", "crawler", True),
    SourceCatalogItem("S47", "PIMCO Insights", "Global Public Research", "https://www.pimco.com/us/en/insights", "crawler", True),
]


def get_source_item(source_id: str) -> SourceCatalogItem | None:
    """Return a catalog item by ID."""
    key = (source_id or "").strip().upper()
    for item in SOURCE_CATALOG:
        if item.source_id == key:
            return item
    return None

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchSourceProfile:
    """공개/권한형 리서치 문서 수집 프로파일."""

    profile_key: str
    source_id: str
    house_name: str
    entry_url: str
    group: str
    market_scope: str
    adapter_type: str
    access_tier: str
    redistribution_policy: str
    house_quality_score: float
    enabled: bool = True
    note: str = ""


PUBLIC_RESEARCH_PROFILES: list[ResearchSourceProfile] = [
    ResearchSourceProfile(
        profile_key="samsung_sec_research",
        source_id="S41",
        house_name="삼성증권",
        entry_url="https://www.samsungpop.com/sscommon/jsp/search/research/research_pop.jsp",
        group="domestic_broker",
        market_scope="KR",
        adapter_type="html_list_pdf",
        access_tier="PUBLIC_OPEN",
        redistribution_policy="DERIVED_ONLY",
        house_quality_score=0.86,
    ),
    ResearchSourceProfile(
        profile_key="kb_financial_research",
        source_id="S42",
        house_name="KB경영연구소",
        entry_url="https://www.kbfg.com/kbresearch/report/reportList.do",
        group="domestic_bank",
        market_scope="KR",
        adapter_type="html_article",
        access_tier="PUBLIC_OPEN",
        redistribution_policy="DERIVED_ONLY",
        house_quality_score=0.8,
    ),
    ResearchSourceProfile(
        profile_key="hana_if",
        source_id="S43",
        house_name="하나금융연구소",
        entry_url="https://www.hanaif.re.kr/boardList.do?menuId=&tabMenuId=MN2100",
        group="domestic_bank",
        market_scope="KR",
        adapter_type="html_list_pdf",
        access_tier="PUBLIC_OPEN",
        redistribution_policy="DERIVED_ONLY",
        house_quality_score=0.8,
        enabled=False,
        note="현재 개발 환경에서는 공개 다운로드 핸드셰이크가 불안정해 프로파일만 유지한다.",
    ),
    ResearchSourceProfile(
        profile_key="woori_fri",
        source_id="S44",
        house_name="우리금융경영연구소",
        entry_url="https://www.wfri.re.kr/ko/mo/research_report/research_report.php",
        group="domestic_bank",
        market_scope="KR",
        adapter_type="html_article",
        access_tier="PUBLIC_OPEN",
        redistribution_policy="DERIVED_ONLY",
        house_quality_score=0.78,
    ),
    ResearchSourceProfile(
        profile_key="ubs_cio",
        source_id="S45",
        house_name="UBS CIO",
        entry_url="https://www.ubs.com/global/en/wealthmanagement/insights.html",
        group="global_public",
        market_scope="GLOBAL",
        adapter_type="html_article",
        access_tier="PUBLIC_OPEN",
        redistribution_policy="DERIVED_ONLY",
        house_quality_score=0.87,
    ),
    ResearchSourceProfile(
        profile_key="blackrock_bii",
        source_id="S46",
        house_name="BlackRock BII",
        entry_url="https://www.blackrock.com/us/individual/insights/blackrock-investment-institute/outlook",
        group="global_public",
        market_scope="GLOBAL",
        adapter_type="html_list_pdf",
        access_tier="PUBLIC_OPEN",
        redistribution_policy="DERIVED_ONLY",
        house_quality_score=0.88,
    ),
    ResearchSourceProfile(
        profile_key="pimco_outlook",
        source_id="S47",
        house_name="PIMCO",
        entry_url="https://www.pimco.com/us/en/insights",
        group="global_public",
        market_scope="GLOBAL",
        adapter_type="html_article",
        access_tier="PUBLIC_OPEN",
        redistribution_policy="DERIVED_ONLY",
        house_quality_score=0.86,
    ),
    ResearchSourceProfile(
        profile_key="miraeasset_sec_research",
        source_id="S48",
        house_name="미래에셋증권",
        entry_url="https://securities.miraeasset.com/bbs/maildownload/notice/list.do",
        group="domestic_broker",
        market_scope="KR",
        adapter_type="html_list_pdf",
        access_tier="PUBLIC_OPEN",
        redistribution_policy="DERIVED_ONLY",
        house_quality_score=0.84,
        enabled=False,
        note="카테고리별 공개 구조는 있으나 현재 구현에서는 안정적인 링크 파서 검증 전이다.",
    ),
    ResearchSourceProfile(
        profile_key="nh_sec_research",
        source_id="S49",
        house_name="NH투자증권",
        entry_url="https://www.nhisresearch.com/",
        group="domestic_broker",
        market_scope="KR",
        adapter_type="html_list_pdf",
        access_tier="PUBLIC_OPEN",
        redistribution_policy="DERIVED_ONLY",
        house_quality_score=0.84,
        enabled=False,
        note="현재 개발 환경에서 연결 재설정이 반복돼 공개 프로파일만 유지한다.",
    ),
    ResearchSourceProfile(
        profile_key="goldman_sachs_research_public",
        source_id="S50",
        house_name="Goldman Sachs Research",
        entry_url="https://www.goldmansachs.com/insights",
        group="global_public",
        market_scope="GLOBAL",
        adapter_type="html_article",
        access_tier="PUBLIC_OPEN",
        redistribution_policy="DERIVED_ONLY",
        house_quality_score=0.89,
        enabled=False,
        note="현재 구현에서는 공개 리서치 인덱스 파서 검증 전이다.",
    ),
]


def get_research_profiles(group: str = "all", only_enabled: bool = True) -> list[ResearchSourceProfile]:
    """현재 구현에 맞는 리서치 수집 프로파일 목록을 반환한다."""

    key = (group or "all").strip().lower()
    aliases = {
        "domestic": {"domestic_broker", "domestic_bank"},
        "all": {"domestic_broker", "domestic_bank", "global_public"},
        "broker": {"domestic_broker"},
        "bank": {"domestic_bank"},
        "global": {"global_public"},
    }
    allowed = aliases.get(key, {key})
    rows = [item for item in PUBLIC_RESEARCH_PROFILES if item.group in allowed]
    if only_enabled:
        rows = [item for item in rows if item.enabled]
    return rows

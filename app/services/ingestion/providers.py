from __future__ import annotations

import copy
import html
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, pstdev
from difflib import SequenceMatcher
from threading import Lock
from typing import Any
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings


UTC = timezone.utc


@dataclass(slots=True)
class InstrumentProfile:
    """Normalized instrument identity."""

    ticker: str
    name_kr: str
    market: str = "KR"
    sector: str | None = None


class SourceProviderClient:
    """Source integration client."""

    _dart_instrument_catalog_cache: list[dict[str, str]] | None = None
    _dart_cache_loaded_at: datetime | None = None
    _dart_cache_lock: Lock = Lock()
    _kis_token_cache: dict[str, tuple[datetime, str]] = {}
    _response_cache: dict[str, tuple[datetime, Any]] = {}
    _response_cache_lock: Lock = Lock()
    _sector_universe_cache: dict[str, dict[str, Any]] | None = None
    _sector_universe_loaded_at: datetime | None = None
    _sector_cache_lock: Lock = Lock()

    def __init__(self) -> None:
        self.settings = get_settings()
        self._kis_base_url_selected = ""

    def resolve_instrument(self, ticker_or_name: str) -> InstrumentProfile:
        q = (ticker_or_name or "").strip()
        if not q:
            raise ValueError("ticker_or_name is required")

        if re.fullmatch(r"\d{6}", q):
            row = self._find_catalog_by_ticker(q)
            if row:
                return InstrumentProfile(ticker=row["ticker"], name_kr=row["name_kr"], market=row.get("market", "KR"), sector=self._sector_for_ticker(row["ticker"]))
            return InstrumentProfile(ticker=q, name_kr=q, market="KR", sector=self._sector_for_ticker(q))

        alias = self._alias_map().get(self._norm_text(q))
        if alias:
            return alias

        candidates = self.search_instruments(q, limit=1)
        if candidates:
            c = candidates[0]
            return InstrumentProfile(ticker=c["ticker"], name_kr=c["name_kr"], market=c.get("market", "KR"), sector=self._sector_for_ticker(c["ticker"]))

        return InstrumentProfile(ticker=q, name_kr=q, market="KR", sector=self._sector_for_ticker(q))

    def _cache_get(self, key: str) -> Any | None:
        now = datetime.now(UTC)
        with self._response_cache_lock:
            item = self._response_cache.get(key)
            if item is None:
                return None
            expires_at, payload = item
            if expires_at <= now:
                self._response_cache.pop(key, None)
                return None
            return copy.deepcopy(payload)

    def _cache_set(self, key: str, payload: Any, ttl_seconds: int | None = None) -> Any:
        expires_at = datetime.now(UTC) + timedelta(seconds=max(1, ttl_seconds or self.settings.connector_cache_ttl_seconds))
        copied = copy.deepcopy(payload)
        with self._response_cache_lock:
            self._response_cache[key] = (expires_at, copied)
        return copy.deepcopy(copied)

    def search_instruments(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        limit = max(1, min(limit, 50))

        catalog = self._load_dart_instrument_catalog()
        qn = self._norm_text(q)
        is_ticker = bool(re.fullmatch(r"\d{1,6}", q))
        qz = q.zfill(6) if is_ticker else q

        scored: list[dict[str, Any]] = []
        for item in catalog:
            ticker = item["ticker"]
            name = item["name_kr"]
            name_norm = item.get("name_norm") or self._norm_text(name)
            match_type = "fuzzy"
            if qz == ticker:
                score = 1.0
                match_type = "ticker_exact"
            elif qn == name_norm:
                score = 0.995
                match_type = "name_exact"
            elif qn and qn in name_norm:
                score = 0.90 + min(len(qn) / max(len(name_norm), 1), 0.09)
                match_type = "name_contains"
            else:
                score = self._similarity(qn, name_norm)
            if score < 0.25:
                continue
            scored.append(
                {
                    "ticker": ticker,
                    "name_kr": name,
                    "market": item.get("market", "KR"),
                    "corp_code": item.get("corp_code", ""),
                    "score": round(float(score), 4),
                    "match_type": match_type,
                }
            )

        alias_rows = self._search_alias_candidates(q)
        merged = {row["ticker"]: row for row in scored}
        for row in alias_rows:
            cur = merged.get(row["ticker"])
            if cur is None or row["score"] > cur["score"]:
                merged[row["ticker"]] = row

        out = list(merged.values())
        out.sort(key=lambda x: (-x["score"], x["ticker"]))
        return out[:limit]

    def fetch_price_daily(self, ticker: str, as_of_date: date, lookback_days: int) -> list[dict[str, Any]]:
        cache_key = f'price:{ticker}:{as_of_date.isoformat()}:{lookback_days}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        rows = self._fetch_price_daily_kis(ticker, as_of_date, lookback_days)
        payload = rows or self._fallback_price_daily(ticker, as_of_date, lookback_days)
        return self._cache_set(cache_key, payload)

    def fetch_news(self, ticker: str, as_of_date: date, include_content: bool = False) -> list[dict[str, Any]]:
        cache_key = f'news:{ticker}:{as_of_date.isoformat()}:{int(include_content)}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        profile = self.resolve_instrument(ticker)
        rows = self._fetch_news_naver(ticker, max_items=20, include_content=include_content)
        rows.extend(self._fetch_news_newsapi(ticker, max_items=12, include_content=include_content))
        dedup: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row.get("url") or row.get("title") or "")
            if not key:
                continue
            cur = dedup.get(key)
            if cur is None or row.get("publish_time_utc", datetime.min.replace(tzinfo=UTC)) > cur.get("publish_time_utc", datetime.min.replace(tzinfo=UTC)):
                dedup[key] = row
        merged = list(dedup.values())
        filtered = self._filter_relevant_instrument_news(profile, merged)
        filtered.sort(
            key=lambda x: (
                float(x.get('stock_relevance_score') or 0.0),
                x.get("publish_time_utc") or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        if filtered:
            payload = filtered
        elif merged:
            payload = []
        else:
            payload = self._fallback_news(ticker, as_of_date)
        return self._cache_set(cache_key, payload)

    def _instrument_reference_terms(self, profile: InstrumentProfile) -> list[str]:
        terms: set[str] = set()
        for candidate in [profile.ticker, profile.name_kr, self._instrument_english_name(profile.ticker, profile.name_kr)]:
            norm = self._norm_text(str(candidate or ''))
            if norm and (norm.isdigit() or len(norm) >= 2):
                terms.add(norm)
        for alias_key, alias_profile in self._alias_map().items():
            if alias_profile.ticker != profile.ticker:
                continue
            norm = self._norm_text(alias_key)
            if norm and (norm.isdigit() or len(norm) >= 2):
                terms.add(norm)
        return sorted(terms, key=len, reverse=True)

    def _score_instrument_news_relevance(self, profile: InstrumentProfile, title: str, content_text: str) -> dict[str, Any]:
        title_norm = self._norm_text(title)
        body_norm = self._norm_text(content_text)
        terms = self._instrument_reference_terms(profile)
        exact_name = self._norm_text(profile.name_kr)
        mention_in_title = any(term and term in title_norm for term in terms)
        mention_in_body = any(term and term in body_norm for term in terms)
        exact_title = bool(exact_name and exact_name in title_norm)
        exact_body = bool(exact_name and exact_name in body_norm)

        raw_text = f"{title} {content_text}".lower()
        impact_tokens = [
            '\uc2e4\uc801', '\uc601\uc5c5\uc774\uc775', '\ub9e4\ucd9c', '\uac00\uc774\ub358\uc2a4', '\uacf5\uc2dc', '\uc218\uc8fc', '\uacf5\uae09\uacc4\uc57d', '\uacc4\uc57d', '\uc99d\uc124', '\uc2e0\uc81c\ud488',
            '\uc810\uc720\uc728', '\uc678\uad6d\uc778', '\uae30\uad00', '\ubaa9\ud45c\uc8fc\uac00', '\ud22c\uc790\uc758\uacac', '\ubc38\ub958\uc5d0\uc774\uc158', '\uc18c\uc1a1', '\ub9ac\ucf5c', '\uc0dd\uc0b0', '\ucd9c\ud558',
            'earnings', 'guidance', 'contract', 'order', 'target price', 'rating', 'valuation', 'shipment', 'production',
        ]
        generic_tokens = [
            '\ucf54\uc2a4\ud53c', '\ucf54\uc2a4\ub2e5', '\uc99d\uc2dc', '\uad6d\ub0b4\uc99d\uc2dc', 'market', 'stock market', 'fed', 'fomc', 'inflation', 'cpi',
            '\uc911\ub3d9', '\uc804\uc7c1', 'iraq', 'iran', 'tariff', '\uad00\uc138', '\uc6d0\ub2ec\ub7ec', '\ud658\uc728',
        ]
        impact_hits = sum(1 for token in impact_tokens if token in raw_text)
        generic_hits = sum(1 for token in generic_tokens if token in raw_text)

        score = 0.0
        if exact_title:
            score += 0.82
        elif mention_in_title:
            score += 0.62
        if exact_body:
            score += 0.24
        elif mention_in_body:
            score += 0.14
        score += min(0.24, impact_hits * 0.06)
        if generic_hits and impact_hits == 0 and not exact_title:
            score -= min(0.22, generic_hits * 0.05)

        is_relevant = bool((mention_in_title or mention_in_body) and score >= 0.62)
        reason = 'exact_title_match' if exact_title else 'title_or_body_match'
        if impact_hits:
            reason += '_with_price_impact_context'
        return {
            'is_relevant': is_relevant,
            'score': round(max(0.0, min(1.0, score)), 3),
            'reason': reason,
            'impact_hits': impact_hits,
        }

    def _filter_relevant_instrument_news(self, profile: InstrumentProfile, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for row in rows:
            relevance = self._score_instrument_news_relevance(
                profile,
                str(row.get('title') or ''),
                str(row.get('content_text') or ''),
            )
            item = dict(row)
            item['stock_relevance_score'] = relevance['score']
            item['stock_relevance_reason'] = relevance['reason']
            if relevance['is_relevant']:
                filtered.append(item)
        return filtered

    def fetch_disclosures(self, ticker: str, as_of_date: date, include_content: bool = False) -> list[dict[str, Any]]:
        cache_key = f'disclosures:{ticker}:{as_of_date.isoformat()}:{int(include_content)}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        rows = self._fetch_disclosures_dart(ticker, as_of_date, days=30, include_content=include_content)
        payload = rows or self._fallback_disclosures(ticker, as_of_date)
        return self._cache_set(cache_key, payload)

    def fetch_financial_statements(self, ticker: str, as_of_date: date) -> dict[str, Any]:
        """Fetch and parse OpenDART single-account financial statements into analysis-ready metrics."""
        cache_key = f'financials:{ticker}:{as_of_date.isoformat()}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        payload = self._fetch_financial_statements_dart(ticker, as_of_date)
        return self._cache_set(cache_key, payload, ttl_seconds=max(self.settings.connector_cache_ttl_seconds, 900))


    def fetch_sector_momentum(self, ticker: str, as_of_date: date, lookback_days: int = 90) -> dict[str, Any]:
        profile = self.resolve_instrument(ticker)
        sector = profile.sector or self._sector_for_ticker(profile.ticker)
        if not sector or sector == "기타":
            return self._default_sector_momentum(profile.ticker, sector)
        definition = self._sector_definitions().get(sector)
        if not definition:
            return self._default_sector_momentum(profile.ticker, sector)

        leader_ticker = str(definition.get('leader') or profile.ticker)
        leader_name = str(definition.get('leader_name') or self.resolve_instrument(leader_ticker).name_kr)
        sampled_members = self._sector_analysis_members(sector, profile.ticker, max_members=12)

        try:
            stock_prices = self.fetch_price_daily(profile.ticker, as_of_date, max(lookback_days, 60))
        except Exception:
            stock_prices = self._fallback_price_daily(profile.ticker, as_of_date, max(lookback_days, 60))
        try:
            leader_prices = self.fetch_price_daily(leader_ticker, as_of_date, max(lookback_days, 60))
        except Exception:
            leader_prices = self._fallback_price_daily(leader_ticker, as_of_date, max(lookback_days, 60))
        stock_ret20 = self._recent_return(stock_prices, 20)
        leader_ret20 = self._recent_return(leader_prices, 20)
        coupling = self._return_correlation(stock_prices, leader_prices, 20)
        relative_strength = stock_ret20 - leader_ret20

        member_rets: list[float] = []
        member_rel_volumes: list[float] = []
        member_turnover_z: list[float] = []
        peer_rows: list[dict[str, Any]] = []
        for member in sampled_members:
            try:
                prices = self.fetch_price_daily(member, as_of_date, max(lookback_days, 60))
            except Exception:
                continue
            if len(prices) < 21:
                continue
            ret20 = self._recent_return(prices, 20)
            rel_volume = self._relative_volume(prices, 20)
            turnover_z = self._turnover_zscore(prices, 20)
            member_rets.append(ret20)
            member_rel_volumes.append(rel_volume)
            member_turnover_z.append(turnover_z)
            peer_rows.append(
                {
                    "ticker": member,
                    "name": str(definition.get("member_names", {}).get(member, member)),
                    "role": "leader" if member == leader_ticker else ("target" if member == profile.ticker else "peer"),
                    "return_20d": round(ret20, 4),
                    "rel_volume": round(rel_volume, 3),
                    "turnover_zscore": round(turnover_z, 3),
                }
            )

        breadth = (sum(1 for value in member_rets if value > 0) / len(member_rets)) if member_rets else 0.0
        avg_ret20 = mean(member_rets) if member_rets else 0.0
        avg_rel_volume = mean(member_rel_volumes) if member_rel_volumes else 1.0
        avg_turnover_z = mean(member_turnover_z) if member_turnover_z else 0.0
        fund_flow_score = self._clamp01(
            0.35 * breadth
            + 0.30 * max(0.0, avg_rel_volume - 1.0)
            + 0.20 * max(0.0, avg_turnover_z / 2.0)
            + 0.15 * max(0.0, avg_ret20 * 5.0)
        )

        return {
            'sector': sector,
            'leader_ticker': leader_ticker,
            'leader_name': leader_name,
            'member_count': len(definition.get('members') or []),
            'sampled_member_count': len(sampled_members),
            'sector_coupling_score': round(coupling, 3),
            'sector_fund_flow_score': round(fund_flow_score, 3),
            'sector_breadth_score': round(breadth, 3),
            'sector_leader_relative_strength': round(relative_strength, 4),
            'sector_average_return_20d': round(avg_ret20, 4),
            'sector_average_rel_volume': round(avg_rel_volume, 3),
            'sector_average_turnover_z': round(avg_turnover_z, 3),
            'peer_rows': peer_rows,
        }

    def _sector_keyword_map(self) -> dict[str, list[str]]:
        return {
            "반도체": ["반도체", "삼성전자", "하이닉스", "semicon", "semiconductor", "memory", "skhynix", "samsungelectronics"],
            "인터넷": ["naver", "카카오", "internet", "portal", "search", "platform"],
            "2차전지·화학": ["배터리", "에너지솔루션", "화학", "cathode", "anode", "chem", "solution"],
            "바이오": ["바이오", "셀트리온", "제약", "pharm", "pharma", "bio", "therapeutics", "medicine"],
            "자동차": ["자동차", "모비스", "motor", "mobis", "kia", "기아"],
            "증권": ["증권", "investment", "securities", "capital"],
            "보험": ["보험", "insurance", "life", "fire"],
            "은행": ["은행", "financialgroup", "bank", "금융지주"],
            "조선": ["조선", "shipbuilding", "marine", "heavyindustries"],
            "철강": ["철강", "steel", "metal"],
            "건설": ["건설", "engineering", "construction", "e&c"],
            "기계·장비": ["기계", "machinery", "equipment", "industrial", "robot"],
            "방산": ["방산", "aerospace", "defense", "한화에어로", "lig"],
            "화장품·생활소비재": ["화장품", "cosmetic", "beauty", "household", "amore", "생활건강"],
            "유통": ["마트", "retail", "shopping", "departmentstore", "백화점", "유통"],
            "게임·엔터": ["game", "games", "entertainment", "music", "studio", "엔터", "게임"],
            "통신": ["telecom", "communication", "통신", "wireless"],
            "전력·에너지": ["energy", "power", "electric", "gas", "발전", "전기"],
            "식음료": ["food", "beverage", "brewery", "식품", "제과"],
            "디스플레이·전자부품": ["display", "camera", "module", "electronics", "electronic", "component", "pcb", "optics"],
            "운송·물류": ["shipping", "logistics", "air", "airline", "transport", "해운", "물류", "항공"],
            "헬스케어서비스": ["hospital", "diagnostic", "healthcare", "medical", "clinic", "care"],
        }

    def _sector_leader_overrides(self) -> dict[str, str]:
        return {
            "반도체": "005930",
            "인터넷": "035420",
            "2차전지·화학": "373220",
            "바이오": "207940",
            "자동차": "005380",
            "증권": "005940",
            "은행": "105560",
            "보험": "005830",
            "조선": "009540",
            "철강": "005490",
            "건설": "000720",
            "방산": "012450",
            "통신": "017670",
            "전력·에너지": "015760",
            "화장품·생활소비재": "090430",
            "게임·엔터": "259960",
            "유통": "139480",
        }

    def _classify_sector_name(self, name_kr: str) -> str:
        normalized = self._norm_text(name_kr)
        if normalized in {"삼성전자", "samsungelectronics"}:
            return "반도체"
        if normalized in {"sk하이닉스", "skhynix", "하이닉스"}:
            return "반도체"
        best_sector = "기타"
        best_score = 0
        for sector, keywords in self._sector_keyword_map().items():
            score = 0
            for keyword in keywords:
                token = self._norm_text(keyword)
                if not token:
                    continue
                if token in normalized:
                    score += 2 if normalized.startswith(token) else 1
            if score > best_score:
                best_sector = sector
                best_score = score
        return best_sector

    def _sector_definitions(self) -> dict[str, dict[str, Any]]:
        now = datetime.now(UTC)
        with self._sector_cache_lock:
            cached = self._sector_universe_cache
            loaded_at = self._sector_universe_loaded_at
            if cached is not None and loaded_at is not None and (now - loaded_at) < timedelta(hours=12):
                return cached

            sectors: dict[str, dict[str, Any]] = {}
            for row in self._load_dart_instrument_catalog():
                ticker = str(row.get('ticker') or '')
                name_kr = str(row.get('name_kr') or ticker)
                if not ticker:
                    continue
                sector = self._classify_sector_name(name_kr)
                bucket = sectors.setdefault(sector, {'leader': '', 'leader_name': '', 'members': [], 'member_names': {}})
                if ticker not in bucket['members']:
                    bucket['members'].append(ticker)
                bucket['member_names'][ticker] = name_kr

            overrides = self._sector_leader_overrides()
            catalog_map = {str(row.get('ticker') or ''): str(row.get('name_kr') or row.get('ticker') or '') for row in self._load_dart_instrument_catalog()}
            for sector, bucket in sectors.items():
                bucket['members'] = sorted(set(bucket.get('members') or []))
                override = overrides.get(sector, '')
                if override and override in catalog_map and override not in bucket['members']:
                    bucket['members'].insert(0, override)
                    bucket.setdefault('member_names', {})[override] = catalog_map[override]
                leader = override if override in bucket['members'] else (bucket['members'][0] if bucket['members'] else '')
                bucket['leader'] = leader
                bucket['leader_name'] = str(bucket.get('member_names', {}).get(leader, leader))

            self._sector_universe_cache = sectors
            self._sector_universe_loaded_at = now
            return sectors

    def _sector_for_ticker(self, ticker: str) -> str | None:
        for sector, definition in self._sector_definitions().items():
            if ticker in set(definition.get('members') or []):
                return sector
        return None

    def _sector_analysis_members(self, sector: str, target_ticker: str, max_members: int = 12) -> list[str]:
        definition = self._sector_definitions().get(sector) or {}
        members = list(definition.get('members') or [])
        leader = str(definition.get('leader') or '')
        selected: list[str] = []
        for candidate in [leader, target_ticker, *members]:
            if candidate and candidate not in selected:
                selected.append(candidate)
            if len(selected) >= max_members:
                break
        return selected or [target_ticker]

    def _default_sector_momentum(self, ticker: str, sector: str | None) -> dict[str, Any]:
        return {
            'sector': sector,
            'leader_ticker': ticker,
            'leader_name': ticker,
            'member_count': 1,
            'sampled_member_count': 1,
            'sector_coupling_score': 0.5,
            'sector_fund_flow_score': 0.0,
            'sector_breadth_score': 0.5,
            'sector_leader_relative_strength': 0.0,
            'sector_average_return_20d': 0.0,
            'sector_average_rel_volume': 1.0,
            'sector_average_turnover_z': 0.0,
            'peer_rows': [],
        }

    def _recent_return(self, prices: list[dict[str, Any]], days: int) -> float:
        closes = [float(row.get('close') or 0.0) for row in prices if float(row.get('close') or 0.0) > 0]
        if len(closes) <= days or closes[-days - 1] == 0:
            return 0.0
        return (closes[-1] / closes[-days - 1]) - 1

    def _relative_volume(self, prices: list[dict[str, Any]], window: int = 20) -> float:
        volumes = [float(row.get('volume') or 0.0) for row in prices if float(row.get('volume') or 0.0) > 0]
        if len(volumes) < window:
            return 1.0
        baseline = mean(volumes[-window:]) or 1.0
        return volumes[-1] / baseline if baseline else 1.0

    def _turnover_zscore(self, prices: list[dict[str, Any]], window: int = 20) -> float:
        turnovers = [float(row.get('close') or 0.0) * float(row.get('volume') or 0.0) for row in prices if float(row.get('close') or 0.0) > 0 and float(row.get('volume') or 0.0) > 0]
        if len(turnovers) < window:
            return 0.0
        sample = turnovers[-window:]
        avg = mean(sample)
        std = pstdev(sample)
        if std == 0:
            return 0.0
        return (sample[-1] - avg) / std

    def _return_correlation(self, left_prices: list[dict[str, Any]], right_prices: list[dict[str, Any]], window: int = 20) -> float:
        left = [float(row.get('close') or 0.0) for row in left_prices if float(row.get('close') or 0.0) > 0]
        right = [float(row.get('close') or 0.0) for row in right_prices if float(row.get('close') or 0.0) > 0]
        length = min(len(left), len(right), window + 1)
        if length < 6:
            return 0.5
        left_returns = [(left[idx] / left[idx - 1]) - 1 for idx in range(len(left) - length + 1, len(left))]
        right_returns = [(right[idx] / right[idx - 1]) - 1 for idx in range(len(right) - length + 1, len(right))]
        if len(left_returns) != len(right_returns) or len(left_returns) < 5:
            return 0.5
        left_avg = mean(left_returns)
        right_avg = mean(right_returns)
        left_std = pstdev(left_returns)
        right_std = pstdev(right_returns)
        if left_std == 0 or right_std == 0:
            return 0.5
        cov = sum((lx - left_avg) * (rx - right_avg) for lx, rx in zip(left_returns, right_returns)) / len(left_returns)
        corr = cov / (left_std * right_std)
        return self._clamp01((corr + 1.0) / 2.0)

    def _clamp01(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _default_overnight_transmission(self, ticker: str) -> dict[str, Any]:
        return {
            'ticker': ticker,
            'applied': False,
            'market_window': 'regular',
            'reference_index': 'SP500',
            'reference_label': 'S&P 500',
            'transmission_beta': 0.0,
            'transmission_corr': 0.0,
            'latest_us_return': 0.0,
            'overnight_signal': 0.0,
            'volatility_spillover_score': 0.0,
            'sample_size': 0,
            'latest_us_trade_date': '',
        }

    def _is_korea_premarket(self, as_of_date: date) -> bool:
        now_kst = datetime.now(ZoneInfo('Asia/Seoul'))
        if as_of_date != now_kst.date():
            return False
        if now_kst.weekday() >= 5:
            return False
        return now_kst.hour < 9

    def _has_confirmed_us_previous_close(self, as_of_date: date, latest_us_trade_date: str) -> bool:
        if not latest_us_trade_date:
            return False
        try:
            latest_trade = date.fromisoformat(latest_us_trade_date)
        except ValueError:
            return False
        if latest_trade >= as_of_date:
            return False
        return (as_of_date - latest_trade).days <= 4

    def _select_us_overnight_index(self, sector: str | None) -> tuple[str, str]:
        sector_name = str(sector or '')
        nasdaq_sectors = {
            '\ubc18\ub3c4\uccb4', '\uc778\ud130\ub137', '\uac8c\uc784\u00b7\uc5d4\ud130', '\ub514\uc2a4\ud50c\ub808\uc774\u00b7\uc804\uc790\ubd80\ud488',
            '\ubc14\uc774\uc624', '\ud5ec\uc2a4\ucf00\uc5b4\uc11c\ube44\uc2a4', '\ud1b5\uc2e0'
        }
        dow_sectors = {
            '\uc99d\uad8c', '\ubcf4\ud5d8', '\uc740\ud589', '\uc870\uc120', '\ucca0\uac15', '\uac74\uc124', '\uae30\uacc4\u00b7\uc7a5\ube44', '\ubc29\uc0b0', '\uc6b4\uc1a1\u00b7\ubb3c\ub958'
        }
        sp500_sectors = {
            '2\ucc28\uc804\uc9c0\u00b7\ud654\ud559', '\uc790\ub3d9\ucc28', '\ud654\uc7a5\ud488\u00b7\uc0dd\ud65c\uc18c\ube44\uc7ac', '\uc720\ud1b5', '\uc804\ub825\u00b7\uc5d0\ub108\uc9c0', '\uc2dd\uc74c\ub8cc'
        }
        if sector_name in nasdaq_sectors:
            return ('NASDAQCOM', 'NASDAQ Composite')
        if sector_name in dow_sectors:
            return ('DJIA', 'Dow Jones Industrial Average')
        if sector_name in sp500_sectors:
            return ('SP500', 'S&P 500')
        return ('SP500', 'S&P 500')

    def _fetch_fred_series_history(self, series_id: str, as_of_date: date, lookback_days: int = 180) -> list[tuple[date, float]]:
        key = (self.settings.fred_api_key or '').strip()
        if not key:
            return []
        try:
            resp = httpx.get(
                'https://api.stlouisfed.org/fred/series/observations',
                params={
                    'series_id': series_id,
                    'api_key': key,
                    'file_type': 'json',
                    'sort_order': 'asc',
                    'limit': max(60, lookback_days + 40),
                },
                timeout=20.0,
            )
            if not resp.is_success:
                return []
            body = resp.json()
            observations = body.get('observations', []) if isinstance(body, dict) else []
            out: list[tuple[date, float]] = []
            for item in observations:
                raw_date = str(item.get('date') or '')
                if raw_date in {'', '.'}:
                    continue
                value = self._to_float(item.get('value'))
                if value <= 0:
                    continue
                try:
                    obs_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
                except Exception:
                    continue
                if obs_date <= as_of_date:
                    out.append((obs_date, value))
            return out[-max(40, lookback_days + 5):]
        except Exception:
            return []

    def _beta_and_corr(self, left: list[float], right: list[float]) -> tuple[float, float]:
        if len(left) != len(right) or len(left) < 6:
            return (0.0, 0.0)
        left_avg = mean(left)
        right_avg = mean(right)
        right_var = sum((value - right_avg) ** 2 for value in right) / len(right)
        if right_var == 0:
            return (0.0, 0.0)
        cov = sum((lx - left_avg) * (rx - right_avg) for lx, rx in zip(left, right)) / len(left)
        left_std = pstdev(left)
        right_std = pstdev(right)
        corr = cov / (left_std * right_std) if left_std and right_std else 0.0
        beta = cov / right_var
        return (round(beta, 4), round(corr, 4))

    def fetch_us_overnight_transmission(self, ticker: str, as_of_date: date, lookback_days: int = 180) -> dict[str, Any]:
        cache_key = f'overnight:{ticker}:{as_of_date.isoformat()}:{lookback_days}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        profile = self.resolve_instrument(ticker)
        reference_index, reference_label = self._select_us_overnight_index(profile.sector)
        us_series = self._fetch_fred_series_history(reference_index, as_of_date, lookback_days)
        if len(us_series) < 12:
            payload = self._default_overnight_transmission(profile.ticker)
            payload.update({'reference_index': reference_index, 'reference_label': reference_label})
            return self._cache_set(cache_key, payload)
        try:
            kr_prices = self.fetch_price_daily(profile.ticker, as_of_date, max(lookback_days, 120))
        except Exception:
            kr_prices = self._fallback_price_daily(profile.ticker, as_of_date, max(lookback_days, 120))
        if len(kr_prices) < 12:
            payload = self._default_overnight_transmission(profile.ticker)
            payload.update({'reference_index': reference_index, 'reference_label': reference_label})
            return self._cache_set(cache_key, payload)

        pairs_us: list[float] = []
        pairs_kr_gap: list[float] = []
        latest_us_return = 0.0
        latest_us_trade_date = ''
        for idx in range(1, len(kr_prices)):
            trade_date = kr_prices[idx]['trade_date']
            eligible = [i for i, (obs_date, _) in enumerate(us_series) if obs_date < trade_date]
            if not eligible:
                continue
            latest_idx = eligible[-1]
            if latest_idx < 1:
                continue
            us_prev_close = us_series[latest_idx - 1][1]
            us_close = us_series[latest_idx][1]
            if us_prev_close <= 0:
                continue
            us_ret = (us_close / us_prev_close) - 1
            prev_close = float(kr_prices[idx - 1].get('close') or 0.0)
            open_price = float(kr_prices[idx].get('open') or 0.0)
            if prev_close <= 0 or open_price <= 0:
                continue
            kr_gap = (open_price / prev_close) - 1
            pairs_us.append(us_ret)
            pairs_kr_gap.append(kr_gap)
            if trade_date == as_of_date or trade_date <= as_of_date:
                latest_us_return = us_ret
                latest_us_trade_date = us_series[latest_idx][0].isoformat()

        beta, corr = self._beta_and_corr(pairs_kr_gap, pairs_us)
        us_tail = pairs_us[-10:] if len(pairs_us) >= 3 else pairs_us
        us_vol = pstdev(us_tail) if len(us_tail) >= 2 else 0.0
        premarket_ready = self._is_korea_premarket(as_of_date)
        confirmed_us_close = self._has_confirmed_us_previous_close(as_of_date, latest_us_trade_date)
        applied = premarket_ready and confirmed_us_close
        overnight_signal = beta * latest_us_return if applied else 0.0
        payload = {
            'ticker': profile.ticker,
            'applied': applied,
            'market_window': 'premarket' if applied else 'regular',
            'premarket_ready': premarket_ready,
            'confirmed_us_close': confirmed_us_close,
            'reference_index': reference_index,
            'reference_label': reference_label,
            'transmission_beta': beta,
            'transmission_corr': corr,
            'latest_us_return': round(latest_us_return, 4),
            'overnight_signal': round(overnight_signal, 4),
            'volatility_spillover_score': round(self._clamp01(abs(beta) * us_vol * 100), 4),
            'sample_size': len(pairs_us),
            'latest_us_trade_date': latest_us_trade_date,
        }
        return self._cache_set(cache_key, payload)

    def fetch_macro(self, as_of_date: date) -> list[dict[str, Any]]:
        cache_key = f'macro:{as_of_date.isoformat()}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        rows: list[dict[str, Any]] = []
        rows.extend(self._fetch_macro_bok(as_of_date))
        rows.extend(self._fetch_macro_kosis(as_of_date))
        rows.extend(self._fetch_macro_fred(as_of_date))
        rows.extend(self._fetch_macro_bls(as_of_date))
        rows.extend(self._fetch_macro_bea(as_of_date))
        rows.extend(self._fetch_macro_fiscaldata(as_of_date))
        rows.extend(self._fetch_macro_oecd(as_of_date))
        rows.extend(self._fetch_macro_world_bank(as_of_date))
        rows.extend(self._fetch_macro_imf(as_of_date))
        rows.extend(self._fetch_macro_eurostat(as_of_date))
        rows.extend(self._fetch_macro_newsapi(as_of_date))
        rows.extend(self._fetch_macro_event_risk(as_of_date))
        payload = self._finalize_macro_rows(rows or self._fallback_macro(as_of_date))
        return self._cache_set(cache_key, payload, ttl_seconds=max(self.settings.connector_cache_ttl_seconds, 300))


    def _consensus_confidence(self, consensus_source: str) -> float:
        source = (consensus_source or '').strip().lower()
        mapping = {
            'expected': 1.0,
            'previous': 0.65,
            'derived': 0.45,
            'metadata': 0.15,
            'count': 0.15,
            'sentiment': 0.15,
            'level_proxy': 0.0,
            'none': 0.0,
        }
        return mapping.get(source, 0.0)

    def _infer_surprise_bias(self, directional_interpretation: str) -> str | None:
        code = (directional_interpretation or '').strip().lower()
        if code in {'rate_up_risk', 'yield_up_risk', 'inflation_up_risk', 'risk_aversion', 'labor_softening', 'fiscal_pressure', 'credit_spread_widening', 'event_risk_building', 'risk_off', 'global_rate_pressure', 'mild_risk_off'}:
            return 'risk_up'
        if code in {'growth_support', 'easing_support', 'risk_on', 'credit_spread_narrowing', 'metadata_fresh'}:
            return 'support_up'
        if code in {'growth_softening', 'metadata_stale'}:
            return 'support_down'
        return None

    def _to_market_surprise_index(self, normalized_delta: float, delta: float, bias: str | None) -> float:
        score = abs(float(normalized_delta or 0.0))
        if score == 0:
            return 0.0
        direction = 1.0 if delta >= 0 else -1.0
        code = (bias or '').strip().lower()
        if code == 'risk_up':
            return round(-score if direction > 0 else score, 3)
        if code == 'support_up':
            return round(score if direction > 0 else -score, 3)
        if code == 'support_down':
            return round(-score if direction > 0 else score, 3)
        return round(normalized_delta if delta >= 0 else -score, 3)

    def _infer_consensus_source(self, row: dict[str, Any], source_meta: dict[str, Any]) -> str:
        if row.get('consensus_source'):
            return str(row['consensus_source'])
        provider = str(source_meta.get('provider') or '').upper()
        if provider in {'FRED', 'BLS', 'BEA', 'FISCALDATA', 'OECD', 'WORLDBANK', 'IMF', 'EUROSTAT'}:
            return 'previous'
        if provider in {'BOK', 'KOSIS'}:
            return 'level_proxy'
        indicator_name = str(row.get('indicator_name') or '').upper()
        if indicator_name in {'UPCOMING_OFFICIAL_EVENT_RISK', 'BROAD_ISSUE_STREAM_TONE'}:
            return 'count' if indicator_name == 'UPCOMING_OFFICIAL_EVENT_RISK' else 'sentiment'
        return 'previous' if row.get('consensus') not in {None, ''} else 'none'

    def _finalize_macro_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            source_meta = dict(item.get('source_meta') or item.get('source_meta_json') or {})
            actual = float(item.get('actual') or 0.0)
            consensus = float(item.get('consensus') or 0.0)
            delta = round(actual - consensus, 4)
            consensus_source = self._infer_consensus_source(item, source_meta)
            confidence = self._consensus_confidence(consensus_source)
            normalized = float(item.get('surprise_std') or self._normalize_macro_delta(str(item.get('indicator_name') or ''), delta) or 0.0)
            bias = str(source_meta.get('surprise_bias') or self._infer_surprise_bias(str(item.get('directional_interpretation') or '')) or '')
            usable = confidence > 0
            item['consensus_source'] = consensus_source
            item['surprise_raw'] = delta
            item['surprise_std'] = round(normalized, 3)
            item['surprise_index'] = self._to_market_surprise_index(normalized, delta, bias) if usable else 0.0
            item['surprise_confidence'] = round(confidence, 3)
            source_meta['consensus_source'] = consensus_source
            source_meta['surprise_bias'] = bias
            source_meta['surprise_raw'] = delta
            source_meta['surprise_usable'] = usable
            source_meta['surprise_confidence'] = round(confidence, 3)
            item['source_meta'] = source_meta
            out.append(item)
        return out

    def _fallback_macro(self, as_of_date: date) -> list[dict[str, Any]]:
        base_dt = datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC)
        return [
            {
                "as_of_date": as_of_date,
                "observation_date": as_of_date,
                "release_at": base_dt,
                "available_at": base_dt,
                "ingested_at": datetime.now(UTC),
                "revision": "initial",
                "country": "KR",
                "indicator_name": "KRWUSD_DAILY_CHANGE",
                "actual": 0.2,
                "consensus": 0.1,
                "surprise_std": 0.1,
                "directional_interpretation": "mild_risk_off",
            },
            {
                "as_of_date": as_of_date,
                "observation_date": as_of_date,
                "release_at": base_dt,
                "available_at": base_dt,
                "ingested_at": datetime.now(UTC),
                "revision": "initial",
                "country": "KR",
                "indicator_name": "KOSPI_VOL_PROXY",
                "actual": 0.0,
                "consensus": 0.0,
                "surprise_std": 0.0,
                "directional_interpretation": "neutral",
            },
            {
                "as_of_date": as_of_date,
                "observation_date": as_of_date,
                "release_at": base_dt,
                "available_at": base_dt,
                "ingested_at": datetime.now(UTC),
                "revision": "initial",
                "country": "KR",
                "indicator_name": "KR_3Y_AA_SPREAD",
                "actual": 0.72,
                "consensus": 0.68,
                "surprise_std": 0.18,
                "directional_interpretation": "credit_spread_widening",
            },
            {
                "as_of_date": as_of_date,
                "observation_date": as_of_date,
                "release_at": base_dt,
                "available_at": base_dt,
                "ingested_at": datetime.now(UTC),
                "revision": "initial",
                "country": "US",
                "indicator_name": "US10Y_MOVE",
                "actual": 0.05,
                "consensus": 0.02,
                "surprise_std": 0.12,
                "directional_interpretation": "global_rate_pressure",
            },
            {
                "as_of_date": as_of_date,
                "observation_date": as_of_date,
                "release_at": base_dt,
                "available_at": base_dt,
                "ingested_at": datetime.now(UTC),
                "revision": "initial",
                "country": "GLOBAL",
                "indicator_name": "GLOBAL_RISK_SENTIMENT",
                "actual": -0.1,
                "consensus": 0.0,
                "surprise_std": 0.08,
                "directional_interpretation": "risk_off",
            },
        ]

    def _fetch_macro_bok(self, as_of_date: date) -> list[dict[str, Any]]:
        key = (self.settings.bok_api_key or "").strip()
        if not key:
            return []
        try:
            resp = httpx.get(
                f"https://ecos.bok.or.kr/api/KeyStatisticList/{key}/json/kr/1/200",
                timeout=20.0,
            )
            if not resp.is_success:
                return []
            body = resp.json().get("KeyStatisticList", {})
            rows = body.get("row", []) if isinstance(body, dict) else []
            if not isinstance(rows, list):
                return []

            aliases = {
                "원/달러 환율(종가)": ("KRWUSD_CLOSE", "fx_level"),
                "코스피지수": ("KOSPI_INDEX", "equity_index"),
                "코스닥지수": ("KOSDAQ_INDEX", "equity_index"),
                "국고채(3년)": ("KR_TBOND_3Y", "rate_level"),
                "회사채(3년, AA-)": ("KR_CORP_AA_3Y", "credit_level"),
                "CD(91일)": ("KR_CD_91D", "rate_level"),
                "기준금리": ("KR_BASE_RATE", "policy_rate"),
                "M2(광의통화, 평잔)": ("KR_M2", "liquidity"),
                "수출금액지수": ("KR_EXPORT_VALUE_INDEX", "trade"),
            }

            mapped: list[dict[str, Any]] = []
            latest_values: dict[str, float] = {}
            latest_cycles: dict[str, str] = {}
            for item in rows:
                name = str(item.get("KEYSTAT_NAME") or "").strip()
                if name not in aliases:
                    continue
                value = self._to_float(item.get("DATA_VALUE"))
                indicator_name, interpretation = aliases[name]
                cycle = str(item.get("CYCLE") or "")
                latest_values[indicator_name] = value
                latest_cycles[indicator_name] = cycle
                mapped.append(
                    {
                        "as_of_date": as_of_date,
                        "observation_date": self._parse_cycle_to_date(cycle) or as_of_date,
                        "release_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
                        "available_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
                        "ingested_at": datetime.now(UTC),
                        "revision": "initial",
                        "country": "KR",
                        "indicator_name": indicator_name,
                        "actual": value,
                        "consensus": 0.0,
                        "surprise_std": self._normalize_macro_level(indicator_name, value),
                        "directional_interpretation": interpretation,
                        "source_meta": {"provider": "BOK", "cycle": cycle, "class_name": item.get("CLASS_NAME"), "unit": item.get("UNIT_NAME")},
                        "consensus_source": "level_proxy",
                        "surprise_confidence": 0.0,
                        "surprise_index": 0.0,
                        "surprise_raw": round(value, 4),
                    }
                )

            if "KR_CORP_AA_3Y" in latest_values and "KR_TBOND_3Y" in latest_values:
                spread = latest_values["KR_CORP_AA_3Y"] - latest_values["KR_TBOND_3Y"]
                mapped.append(
                    {
                        "as_of_date": as_of_date,
                        "observation_date": self._parse_cycle_to_date(latest_cycles.get("KR_CORP_AA_3Y", "")) or as_of_date,
                        "release_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
                        "available_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
                        "ingested_at": datetime.now(UTC),
                        "revision": "derived",
                        "country": "KR",
                        "indicator_name": "KR_3Y_AA_SPREAD",
                        "actual": round(spread, 4),
                        "consensus": 0.0,
                        "surprise_std": round(spread / 2.0, 3),
                        "directional_interpretation": "credit_spread_widening" if spread > 0 else "credit_spread_narrowing",
                        "source_meta": {"provider": "BOK", "derived_from": ["KR_CORP_AA_3Y", "KR_TBOND_3Y"]},
                        "consensus_source": "derived",
                        "surprise_confidence": 0.45,
                        "surprise_index": round(-abs(spread / 2.0), 3) if spread > 0 else round(abs(spread / 2.0), 3),
                        "surprise_raw": round(spread, 4),
                    }
                )
            return mapped
        except Exception:
            return []

    def _fetch_macro_kosis(self, as_of_date: date) -> list[dict[str, Any]]:
        key = (self.settings.kosis_api_key or "").strip()
        if not key:
            return []
        query_map = {
            "소비자물가": "KR_CPI_SEARCH",
            "실업률": "KR_UNEMPLOYMENT_SEARCH",
            "산업생산지수": "KR_INDUSTRIAL_PRODUCTION_SEARCH",
            "수출": "KR_EXPORT_SEARCH",
        }
        out: list[dict[str, Any]] = []
        for query, indicator_name in query_map.items():
            try:
                resp = httpx.get(
                    "https://kosis.kr/openapi/statisticsSearch.do",
                    params={
                        "method": "getList",
                        "apiKey": key,
                        "format": "json",
                        "jsonVD": "Y",
                        "searchNm": query,
                        "resultCount": 5,
                        "startCount": 1,
                        "content": "json",
                    },
                    timeout=20.0,
                )
                if not resp.is_success:
                    continue
                rows = resp.json()
                if not isinstance(rows, list) or not rows:
                    continue
                top = rows[0]
                end_prd = str(top.get("END_PRD_DE") or "")
                freshness_days = self._days_since_period(end_prd, as_of_date)
                out.append(
                    {
                        "as_of_date": as_of_date,
                        "observation_date": self._parse_cycle_to_date(end_prd) or as_of_date,
                        "release_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
                        "available_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
                        "ingested_at": datetime.now(UTC),
                        "revision": "search_metadata",
                        "country": "KR",
                        "indicator_name": indicator_name,
                        "actual": max(0.0, 1 - min(freshness_days / 120.0, 1.0)),
                        "consensus": 0.0,
                        "surprise_std": max(0.0, min(freshness_days / 30.0, 3.0)),
                        "directional_interpretation": "metadata_fresh" if freshness_days <= 31 else "metadata_stale",
                        "content_text": " ".join(
                            [
                                str(top.get("TBL_NM") or ""),
                                str(top.get("STAT_NM") or ""),
                                str(top.get("CONTENTS") or "")[:1200],
                            ]
                        ).strip(),
                        "source_meta": {
                            "provider": "KOSIS",
                            "org_id": top.get("ORG_ID"),
                            "tbl_id": top.get("TBL_ID"),
                            "link_url": top.get("LINK_URL"),
                            "end_prd_de": end_prd,
                            "query": query,
                        },
                        "consensus_source": "metadata",
                        "surprise_confidence": 0.15,
                        "surprise_index": round(-max(0.0, min(freshness_days / 30.0, 3.0)), 3) if freshness_days > 31 else round(max(0.0, 1 - min(freshness_days / 31.0, 1.0)), 3),
                        "surprise_raw": round(max(0.0, 1 - min(freshness_days / 120.0, 1.0)), 4),
                    }
                )
            except Exception:
                continue
        return out


    def _fetch_macro_fred(self, as_of_date: date) -> list[dict[str, Any]]:
        key = (self.settings.fred_api_key or "").strip()
        if not key:
            return []
        series_map = {
            "FEDFUNDS": ("US_FED_FUNDS_RATE", "policy_rate", "rate_up_risk"),
            "DGS10": ("US_10Y_TREASURY", "rate_level", "yield_up_risk"),
            "UNRATE": ("US_UNEMPLOYMENT_RATE", "labor", "labor_softening"),
            "VIXCLS": ("US_VIX", "risk", "risk_aversion"),
            "INDPRO": ("US_INDUSTRIAL_PRODUCTION", "growth", "growth_momentum"),
        }
        out: list[dict[str, Any]] = []
        for series_id, meta in series_map.items():
            try:
                resp = httpx.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 24,
                    },
                    timeout=20.0,
                )
                if not resp.is_success:
                    continue
                body = resp.json()
                observations = body.get("observations", []) if isinstance(body, dict) else []
                parsed: list[tuple[date, float]] = []
                for item in observations:
                    value = self._to_float(item.get("value"))
                    raw_date = str(item.get("date") or "")
                    if raw_date in {"", "."}:
                        continue
                    try:
                        obs_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                    except Exception:
                        continue
                    parsed.append((obs_date, value))
                if not parsed:
                    continue
                parsed.sort(key=lambda x: x[0])
                latest_date, latest_value = parsed[-1]
                prev_value = parsed[-2][1] if len(parsed) >= 2 else latest_value
                indicator_name, interpretation, bias = meta
                out.append(
                    self._build_macro_row(
                        as_of_date=as_of_date,
                        observation_date=latest_date,
                        country="US",
                        indicator_name=indicator_name,
                        actual=latest_value,
                        consensus=prev_value,
                        directional_interpretation=self._macro_delta_interpretation(indicator_name, latest_value - prev_value, bias),
                        source_meta={"provider": "FRED", "series_id": series_id},
                        consensus_source='previous',
                        surprise_bias=bias,
                    )
                )
            except Exception:
                continue
        return out

    def _fetch_macro_bls(self, as_of_date: date) -> list[dict[str, Any]]:
        key = (self.settings.bls_api_key or "").strip()
        if not key:
            return []
        series_map = {
            "CUUR0000SA0": ("US_CPI_INDEX", "inflation", "inflation_up_risk"),
            "LNS14000000": ("US_UNEMPLOYMENT_RATE_BLS", "labor", "labor_softening"),
            "CES0000000001": ("US_NONFARM_PAYROLLS", "employment", "growth_support"),
        }
        try:
            resp = httpx.post(
                "https://api.bls.gov/publicAPI/v2/timeseries/data/",
                json={
                    "seriesid": list(series_map.keys()),
                    "registrationkey": key,
                    "startyear": str(max(as_of_date.year - 2, 2000)),
                    "endyear": str(as_of_date.year),
                },
                timeout=25.0,
            )
            if not resp.is_success:
                return []
            body = resp.json().get("Results", {}).get("series", [])
            out: list[dict[str, Any]] = []
            for series in body:
                series_id = str(series.get("seriesID") or "")
                if series_id not in series_map:
                    continue
                values: list[tuple[date, float]] = []
                for item in series.get("data", []):
                    period = str(item.get("period") or "")
                    year = str(item.get("year") or "")
                    if not year or not period.startswith("M") or period == "M13":
                        continue
                    try:
                        obs_date = date(int(year), int(period[1:]), 1)
                    except Exception:
                        continue
                    values.append((obs_date, self._to_float(item.get("value"))))
                if not values:
                    continue
                values.sort(key=lambda x: x[0])
                latest_date, latest_value = values[-1]
                prev_value = values[-2][1] if len(values) >= 2 else latest_value
                indicator_name, interpretation, bias = series_map[series_id]
                out.append(
                    self._build_macro_row(
                        as_of_date=as_of_date,
                        observation_date=latest_date,
                        country="US",
                        indicator_name=indicator_name,
                        actual=latest_value,
                        consensus=prev_value,
                        directional_interpretation=self._macro_delta_interpretation(indicator_name, latest_value - prev_value, bias),
                        source_meta={"provider": "BLS", "series_id": series_id},
                        consensus_source='previous',
                        surprise_bias=bias,
                    )
                )
            return out
        except Exception:
            return []

    def _fetch_macro_bea(self, as_of_date: date) -> list[dict[str, Any]]:
        key = (self.settings.bea_api_key or "").strip()
        if not key:
            return []
        query_specs = [
            {
                "indicator_name": "US_REAL_GDP_QOQ",
                "table_names": ["T10101"],
                "line_keywords": ["Gross domestic product"],
                "interpretation": "growth_momentum",
                "bias": "growth_support",
            },
            {
                "indicator_name": "US_PCE_PRICE_INDEX",
                "table_names": ["T10107"],
                "line_keywords": ["Personal consumption expenditures"],
                "interpretation": "inflation",
                "bias": "inflation_up_risk",
            },
        ]
        out: list[dict[str, Any]] = []
        for spec in query_specs:
            data_rows = self._query_bea_table(key, spec["table_names"], spec["line_keywords"])
            if len(data_rows) < 1:
                continue
            data_rows.sort(key=lambda x: x[0])
            latest_date, latest_value = data_rows[-1]
            prev_value = data_rows[-2][1] if len(data_rows) >= 2 else latest_value
            out.append(
                self._build_macro_row(
                    as_of_date=as_of_date,
                    observation_date=latest_date,
                    country="US",
                    indicator_name=spec["indicator_name"],
                    actual=latest_value,
                    consensus=prev_value,
                    directional_interpretation=self._macro_delta_interpretation(spec["indicator_name"], latest_value - prev_value, spec["bias"]),
                    source_meta={"provider": "BEA", "table_candidates": spec["table_names"]},
                    consensus_source='previous',
                    surprise_bias=spec["bias"],
                )
            )
        return out

    def _fetch_macro_fiscaldata(self, as_of_date: date) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            debt_resp = httpx.get(
                "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny",
                params={"sort": "-record_date", "page[size]": 3},
                timeout=20.0,
            )
            if debt_resp.is_success:
                data = debt_resp.json().get("data", [])
                parsed: list[tuple[date, float]] = []
                for item in data:
                    raw_date = str(item.get("record_date") or "")
                    if not raw_date:
                        continue
                    try:
                        obs_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                    except Exception:
                        continue
                    parsed.append((obs_date, self._to_float(item.get("tot_pub_debt_out_amt"))))
                parsed.sort(key=lambda x: x[0])
                if parsed:
                    latest_date, latest_value = parsed[-1]
                    prev_value = parsed[-2][1] if len(parsed) >= 2 else latest_value
                    out.append(
                        self._build_macro_row(
                            as_of_date=as_of_date,
                            observation_date=latest_date,
                            country="US",
                            indicator_name="US_TOTAL_PUBLIC_DEBT",
                            actual=latest_value,
                            consensus=prev_value,
                            directional_interpretation=self._macro_delta_interpretation("US_TOTAL_PUBLIC_DEBT", latest_value - prev_value, "fiscal_pressure"),
                            source_meta={"provider": "FiscalData", "endpoint": "debt_to_penny"},
                            consensus_source='previous',
                            surprise_bias='fiscal_pressure',
                        )
                    )
        except Exception:
            pass
        try:
            mts_resp = httpx.get(
                "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_1",
                params={"sort": "-record_date", "page[size]": 3},
                timeout=20.0,
            )
            if mts_resp.is_success:
                data = mts_resp.json().get("data", [])
                parsed: list[tuple[date, float]] = []
                for item in data:
                    raw_date = str(item.get("record_date") or "")
                    if not raw_date:
                        continue
                    try:
                        obs_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                    except Exception:
                        continue
                    parsed.append((obs_date, self._to_float(item.get("current_month_deficit_surplus_amt"))))
                parsed.sort(key=lambda x: x[0])
                if parsed:
                    latest_date, latest_value = parsed[-1]
                    prev_value = parsed[-2][1] if len(parsed) >= 2 else latest_value
                    out.append(
                        self._build_macro_row(
                            as_of_date=as_of_date,
                            observation_date=latest_date,
                            country="US",
                            indicator_name="US_FISCAL_BALANCE",
                            actual=latest_value,
                            consensus=prev_value,
                            directional_interpretation=self._macro_delta_interpretation("US_FISCAL_BALANCE", latest_value - prev_value, "fiscal_pressure"),
                            source_meta={"provider": "FiscalData", "endpoint": "mts_table_1"},
                            consensus_source='previous',
                            surprise_bias='fiscal_pressure',
                        )
                    )
        except Exception:
            pass
        return out

    def _fetch_macro_oecd(self, as_of_date: date) -> list[dict[str, Any]]:
        series_specs = [
            ("US", "USA.Q.N.CPI.IX._T.N._Z", "OECD_US_CPI", "inflation_up_risk"),
            ("EU", "EA20.Q.N.CPI.IX._T.N._Z", "OECD_EU_CPI", "inflation_up_risk"),
        ]
        out: list[dict[str, Any]] = []
        for country, key, indicator_name, bias in series_specs:
            values = self._fetch_oecd_series_values(key)
            if not values:
                continue
            values.sort(key=lambda x: x[0])
            latest_date, latest_value = values[-1]
            prev_value = values[-2][1] if len(values) >= 2 else latest_value
            out.append(
                self._build_macro_row(
                    as_of_date=as_of_date,
                    observation_date=latest_date,
                    country=country,
                    indicator_name=indicator_name,
                    actual=latest_value,
                    consensus=prev_value,
                    directional_interpretation=self._macro_delta_interpretation(indicator_name, latest_value - prev_value, bias),
                    source_meta={"provider": "OECD", "series_key": key},
                    consensus_source='previous',
                    surprise_bias=bias,
                )
            )
        return out

    def _fetch_oecd_series_values(self, series_key: str) -> list[tuple[date, float]]:
        try:
            resp = httpx.get(
                f"https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/{series_key}/",
                params={"lastNObservations": 4},
                timeout=25.0,
                follow_redirects=True,
            )
            if not resp.is_success or "xml" not in (resp.headers.get("content-type") or "").lower():
                return []
            root = ET.fromstring(resp.text)
            ns = {"generic": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic"}
            out: list[tuple[date, float]] = []
            for series in root.findall(".//generic:Series", ns):
                for obs in series.findall("./generic:Obs", ns):
                    dim = obs.find("./generic:ObsDimension", ns)
                    val = obs.find("./generic:ObsValue", ns)
                    if dim is None or val is None:
                        continue
                    obs_date = self._parse_oecd_period(dim.attrib.get("value", ""))
                    if obs_date is None:
                        continue
                    out.append((obs_date, self._to_float(val.attrib.get("value"))))
            return out
        except Exception:
            return []

    def _parse_oecd_period(self, raw: str) -> date | None:
        txt = (raw or "").strip()
        if not txt:
            return None
        match = re.fullmatch(r"(\d{4})-Q([1-4])", txt)
        if match:
            return date(int(match.group(1)), int(match.group(2)) * 3, 1)
        match = re.fullmatch(r"(\d{4})-(\d{2})", txt)
        if match:
            return date(int(match.group(1)), int(match.group(2)), 1)
        return None

    def fetch_oecd_briefings(self, max_items: int = 12) -> list[dict[str, Any]]:
        rows = self._fetch_macro_oecd(date.today())[: max(1, min(max_items, 12))]
        docs: list[dict[str, Any]] = []
        for row in rows:
            docs.append(
                {
                    "title": f"OECD {row.get('indicator_name')} snapshot",
                    "url": "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/",
                    "publish_time_utc": row.get("available_at") or datetime.now(UTC),
                    "content_text": str(row.get("content_text") or ""),
                    "raw_content": b"",
                    "raw_ext": ".xml",
                }
            )
        return docs

    def _fetch_oecd_feed_candidate(self, url: str, max_items: int, auth: tuple[str, str] | None = None) -> list[dict[str, Any]]:
        return []

    def _query_bea_table(self, key: str, table_names: list[str], line_keywords: list[str]) -> list[tuple[date, float]]:
        for table_name in table_names:
            try:
                resp = httpx.get(
                    "https://apps.bea.gov/api/data",
                    params={
                        "UserID": key,
                        "method": "GetData",
                        "datasetname": "NIPA",
                        "TableName": table_name,
                        "Frequency": "Q",
                        "Year": f"{max(date.today().year - 1, 2000)},{date.today().year}",
                        "ResultFormat": "json",
                    },
                    timeout=25.0,
                )
                if not resp.is_success:
                    continue
                data = resp.json().get("BEAAPI", {}).get("Results", {}).get("Data", [])
                parsed: list[tuple[date, float]] = []
                for item in data:
                    line_desc = str(item.get("LineDescription") or "")
                    if not any(keyword.lower() in line_desc.lower() for keyword in line_keywords):
                        continue
                    period = str(item.get("TimePeriod") or "")
                    obs_date = self._parse_bea_period(period)
                    if obs_date is None:
                        continue
                    parsed.append((obs_date, self._to_float(item.get("DataValue"))))
                if parsed:
                    return parsed
            except Exception:
                continue
        return []

    def _parse_bea_period(self, raw: str) -> date | None:
        txt = (raw or "").strip()
        if not txt:
            return None
        match = re.fullmatch(r"(\d{4})Q([1-4])", txt)
        if match:
            return date(int(match.group(1)), int(match.group(2)) * 3, 1)
        try:
            return datetime.strptime(txt, "%Y").date()
        except Exception:
            return None

    def _build_macro_row(
        self,
        as_of_date: date,
        observation_date: date,
        country: str,
        indicator_name: str,
        actual: float,
        consensus: float,
        directional_interpretation: str,
        source_meta: dict[str, Any] | None = None,
        *,
        consensus_source: str = 'previous',
        surprise_bias: str | None = None,
    ) -> dict[str, Any]:
        delta = actual - consensus
        surprise_std = self._normalize_macro_delta(indicator_name, delta)
        expected_label = 'expected' if consensus_source == 'expected' else 'prior'
        meta = dict(source_meta or {})
        if surprise_bias:
            meta['surprise_bias'] = surprise_bias
        meta['consensus_source'] = consensus_source
        meta['surprise_raw'] = round(delta, 4)
        meta['surprise_usable'] = self._consensus_confidence(consensus_source) > 0
        meta['surprise_confidence'] = round(self._consensus_confidence(consensus_source), 3)
        return {
            "as_of_date": as_of_date,
            "observation_date": observation_date,
            "release_at": datetime.combine(observation_date, datetime.min.time(), tzinfo=UTC),
            "available_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
            "ingested_at": datetime.now(UTC),
            "revision": "initial",
            "country": country,
            "indicator_name": indicator_name,
            "actual": round(actual, 4),
            "consensus": round(consensus, 4),
            "surprise_raw": round(delta, 4),
            "surprise_std": surprise_std,
            "surprise_index": self._to_market_surprise_index(surprise_std, delta, surprise_bias),
            "surprise_confidence": round(self._consensus_confidence(consensus_source), 3),
            "consensus_source": consensus_source,
            "directional_interpretation": directional_interpretation,
            "content_text": f"{indicator_name} actual={actual} {expected_label}={consensus} delta={round(delta, 4)}",
            "source_meta": meta,
        }

    def _macro_delta_interpretation(self, indicator_name: str, delta: float, bias: str) -> str:
        if abs(delta) < 1e-9:
            return "neutral"
        positive = delta > 0
        risk_bias = bias in {"rate_up_risk", "yield_up_risk", "inflation_up_risk", "risk_aversion", "labor_softening", "fiscal_pressure"}
        support_bias = bias in {"growth_support"}
        if risk_bias:
            return bias if positive else "easing_support"
        if support_bias:
            return "growth_support" if positive else "growth_softening"
        return f"{indicator_name.lower()}_{'up' if positive else 'down'}"

    def fetch_official_event_stream(self, as_of_date: date, horizon_days: int = 30) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        rows.extend(self._fetch_fed_calendar(as_of_date, horizon_days))
        rows.extend(self._fetch_ecb_calendar(as_of_date, horizon_days))
        rows.extend(self._fetch_eurostat_calendar(as_of_date, horizon_days))
        rows.extend(self._fetch_nbs_calendar(as_of_date, horizon_days))
        rows.extend(self._fetch_bls_schedule(as_of_date, horizon_days))
        rows.extend(self._fetch_bea_schedule(as_of_date, horizon_days))
        if not rows:
            rows.extend(self._fallback_official_event_stream(as_of_date))
        rows.sort(key=lambda x: x.get("scheduled_at_utc") or datetime.max.replace(tzinfo=UTC))
        dedup: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row.get("event_code") or row.get("title") or "")
            if key:
                dedup[key] = row
        return list(dedup.values())

    def fetch_broad_issue_stream(self, as_of_date: date, lookback_days: int = 7) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        rows.extend(self._fetch_issue_gdelt(as_of_date, lookback_days))
        rows.extend(self._fetch_issue_ecb_rss(as_of_date, lookback_days))
        rows.extend(self._fetch_issue_fed_press(as_of_date, lookback_days))
        rows.sort(key=lambda x: x.get("publish_time_utc") or datetime.min.replace(tzinfo=UTC), reverse=True)
        dedup: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row.get("url") or row.get("title") or "")
            if key and key not in dedup:
                dedup[key] = row
        return list(dedup.values())

    def _fetch_macro_event_risk(self, as_of_date: date) -> list[dict[str, Any]]:
        official = self.fetch_official_event_stream(as_of_date, horizon_days=14)
        broad = self.fetch_broad_issue_stream(as_of_date, lookback_days=7)
        out: list[dict[str, Any]] = []
        upcoming = [x for x in official if x.get("scheduled_at_utc") and x["scheduled_at_utc"].date() >= as_of_date and x["scheduled_at_utc"].date() <= (as_of_date + timedelta(days=7))]
        if upcoming:
            out.append(
                self._build_macro_row(
                    as_of_date=as_of_date,
                    observation_date=as_of_date,
                    country="GLOBAL",
                    indicator_name="UPCOMING_OFFICIAL_EVENT_RISK",
                    actual=float(len(upcoming)),
                    consensus=0.0,
                    directional_interpretation="event_risk_building",
                    source_meta={"provider": "official_event_stream", "event_count": len(upcoming), "event_titles": [str(x.get("title") or "") for x in upcoming[:5]]},
                    consensus_source='count',
                    surprise_bias='risk_up',
                )
            )
        if broad:
            sentiments = [self._naive_sentiment(" ".join([str(x.get("title") or ""), str(x.get("content_text") or "")[:500]])) for x in broad[:20]]
            avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0
            out.append(
                {
                    "as_of_date": as_of_date,
                    "observation_date": as_of_date,
                    "release_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
                    "available_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
                    "ingested_at": datetime.now(UTC),
                    "revision": "initial",
                    "source_tz": "UTC",
                    "country": "GLOBAL",
                    "indicator_name": "BROAD_ISSUE_STREAM_TONE",
                    "actual": round(avg_sentiment, 4),
                    "consensus": 0.0,
                    "surprise_std": round(abs(avg_sentiment), 3),
                    "directional_interpretation": "risk_on" if avg_sentiment > 0 else "risk_off" if avg_sentiment < 0 else "neutral",
                    "content_text": " ".join(str(x.get("title") or "") for x in broad[:5]),
                    "source_meta": {"provider": "broad_issue_stream", "issue_count": len(broad)},
                }
            )
        return out

    def _fetch_fed_calendar(self, as_of_date: date, horizon_days: int) -> list[dict[str, Any]]:
        try:
            resp = httpx.get('https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm', timeout=20.0, follow_redirects=True)
            if not resp.is_success:
                return []
            html = resp.text
            rows: list[dict[str, Any]] = []
            year = as_of_date.year
            for match in re.finditer(r'([A-Z][a-z]+)\s+(\d{1,2})(?:-(\d{1,2}))?,\s*(\d{4}).{0,80}?FOMC', html, re.I | re.S):
                month_name, day1, day2, year_s = match.groups()
                try:
                    dt = datetime.strptime(f'{month_name} {day1} {year_s} 14:00', '%B %d %Y %H:%M').replace(tzinfo=UTC)
                except Exception:
                    continue
                if dt.date() < as_of_date - timedelta(days=3) or dt.date() > as_of_date + timedelta(days=horizon_days):
                    continue
                event_code = f'FED_FOMC_{dt.date().isoformat()}'
                rows.append({
                    'source_system': 'FED_CALENDAR',
                    'event_code': event_code,
                    'category': 'policy_meeting',
                    'title': f'FOMC Meeting {dt.date().isoformat()}',
                    'country': 'US',
                    'source_tz': 'ET',
                    'scheduled_at_utc': dt,
                    'release_at_utc': dt,
                    'available_at_utc': dt,
                    'status': 'scheduled',
                    'url': 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',
                    'metadata_json': {'source_year': year, 'meeting_range_day2': day2 or ''},
                })
            return rows
        except Exception:
            return []

    def _fetch_ecb_calendar(self, as_of_date: date, horizon_days: int) -> list[dict[str, Any]]:
        try:
            resp = httpx.get('https://www.ecb.europa.eu/press/calendars/govc/html/index.en.html', timeout=20.0, follow_redirects=True)
            if not resp.is_success:
                return []
            html = resp.text
            rows: list[dict[str, Any]] = []
            for match in re.finditer(r'(\d{1,2}\s+[A-Z][a-z]+\s+\d{4}).{0,120}?(Governing Council|monetary policy meeting)', html, re.I | re.S):
                raw_date, label = match.groups()
                try:
                    dt = datetime.strptime(raw_date + ' 12:15', '%d %B %Y %H:%M').replace(tzinfo=UTC)
                except Exception:
                    continue
                if dt.date() < as_of_date - timedelta(days=3) or dt.date() > as_of_date + timedelta(days=horizon_days):
                    continue
                rows.append({
                    'source_system': 'ECB_CALENDAR',
                    'event_code': f'ECB_GC_{dt.date().isoformat()}',
                    'category': 'policy_meeting',
                    'title': f'ECB {label.strip()} {dt.date().isoformat()}',
                    'country': 'EU',
                    'source_tz': 'CET/CEST',
                    'scheduled_at_utc': dt,
                    'release_at_utc': dt,
                    'available_at_utc': dt,
                    'status': 'scheduled',
                    'url': 'https://www.ecb.europa.eu/press/calendars/govc/html/index.en.html',
                    'metadata_json': {},
                })
            return rows
        except Exception:
            return []

    def _fetch_eurostat_calendar(self, as_of_date: date, horizon_days: int) -> list[dict[str, Any]]:
        urls = [
            'https://ec.europa.eu/eurostat/web/main/news/release-calendar',
            'https://ec.europa.eu/eurostat/cache/release-calendar/release-calendar.ics',
        ]
        rows: list[dict[str, Any]] = []
        for url in urls:
            try:
                resp = httpx.get(url, timeout=20.0, follow_redirects=True)
                if not resp.is_success:
                    continue
                text = resp.text
                if 'BEGIN:VEVENT' in text:
                    for block in text.split('BEGIN:VEVENT')[1:]:
                        dt_match = re.search(r'DTSTART(?:;VALUE=DATE)?:(\d{8})', block)
                        sum_match = re.search(r'SUMMARY:(.+)', block)
                        if not dt_match or not sum_match:
                            continue
                        dt = datetime.strptime(dt_match.group(1) + ' 10:00', '%Y%m%d %H:%M').replace(tzinfo=UTC)
                        if dt.date() < as_of_date - timedelta(days=3) or dt.date() > as_of_date + timedelta(days=horizon_days):
                            continue
                        title = sum_match.group(1).strip()
                        rows.append({'source_system':'EUROSTAT_CALENDAR','event_code':f'EUROSTAT_{dt.date().isoformat()}_{len(rows)+1}','category':'statistics_release','title':title[:500],'country':'EU','source_tz':'CET/CEST','scheduled_at_utc':dt,'release_at_utc':dt,'available_at_utc':dt,'status':'scheduled','url':url,'metadata_json':{}})
                    if rows:
                        return rows
                for match in re.finditer(r'(\d{1,2}\s+[A-Z][a-z]+\s+\d{4}).{0,160}?release', text, re.I | re.S):
                    raw_date = match.group(1)
                    dt = datetime.strptime(raw_date + ' 10:00', '%d %B %Y %H:%M').replace(tzinfo=UTC)
                    if dt.date() < as_of_date - timedelta(days=3) or dt.date() > as_of_date + timedelta(days=horizon_days):
                        continue
                    rows.append({'source_system':'EUROSTAT_CALENDAR','event_code':f'EUROSTAT_{dt.date().isoformat()}_{len(rows)+1}','category':'statistics_release','title':'Eurostat Scheduled Release','country':'EU','source_tz':'CET/CEST','scheduled_at_utc':dt,'release_at_utc':dt,'available_at_utc':dt,'status':'scheduled','url':url,'metadata_json':{}})
                if rows:
                    return rows
            except Exception:
                continue
        return rows

    def _fetch_nbs_calendar(self, as_of_date: date, horizon_days: int) -> list[dict[str, Any]]:
        candidates = ['https://www.stats.gov.cn/english/PressRelease/', 'https://www.stats.gov.cn/english/']
        rows: list[dict[str, Any]] = []
        for url in candidates:
            try:
                resp = httpx.get(url, timeout=20.0, follow_redirects=True)
                if not resp.is_success:
                    continue
                for match in re.finditer(r'(\d{4}-\d{2}-\d{2}).{0,200}?(CPI|PPI|industrial production|retail sales|PMI)', resp.text, re.I | re.S):
                    raw_date, label = match.groups()
                    dt = datetime.strptime(raw_date + ' 01:00', '%Y-%m-%d %H:%M').replace(tzinfo=UTC)
                    if dt.date() < as_of_date - timedelta(days=3) or dt.date() > as_of_date + timedelta(days=horizon_days):
                        continue
                    rows.append({'source_system':'NBS_CALENDAR','event_code':f'NBS_{label}_{dt.date().isoformat()}','category':'statistics_release','title':f'NBS {label} release {dt.date().isoformat()}','country':'CN','source_tz':'CST','scheduled_at_utc':dt,'release_at_utc':dt,'available_at_utc':dt,'status':'scheduled','url':url,'metadata_json':{}})
                if rows:
                    return rows
            except Exception:
                continue
        return rows

    def _fetch_bls_schedule(self, as_of_date: date, horizon_days: int) -> list[dict[str, Any]]:
        try:
            resp = httpx.get('https://www.bls.gov/schedule/news_release/', timeout=20.0, follow_redirects=True)
            if not resp.is_success:
                return []
            rows: list[dict[str, Any]] = []
            for match in re.finditer(r'(\w+\s+\d{1,2},\s+\d{4}).{0,180}?(CPI|Employment Situation|Producer Price Index|Consumer Price Index)', resp.text, re.I | re.S):
                raw_date, label = match.groups()
                try:
                    dt = datetime.strptime(raw_date + ' 13:30', '%B %d, %Y %H:%M').replace(tzinfo=UTC)
                except Exception:
                    continue
                if dt.date() < as_of_date - timedelta(days=3) or dt.date() > as_of_date + timedelta(days=horizon_days):
                    continue
                rows.append({'source_system':'BLS_CALENDAR','event_code':f'BLS_{label}_{dt.date().isoformat()}','category':'statistics_release','title':f'BLS {label} {dt.date().isoformat()}','country':'US','source_tz':'ET','scheduled_at_utc':dt,'release_at_utc':dt,'available_at_utc':dt,'status':'scheduled','url':'https://www.bls.gov/schedule/news_release/','metadata_json':{}})
            return rows
        except Exception:
            return []

    def _fetch_bea_schedule(self, as_of_date: date, horizon_days: int) -> list[dict[str, Any]]:
        try:
            resp = httpx.get('https://www.bea.gov/news/schedule', timeout=20.0, follow_redirects=True)
            if not resp.is_success:
                return []
            rows: list[dict[str, Any]] = []
            for match in re.finditer(r'(\w+\s+\d{1,2},\s+\d{4}).{0,180}?(GDP|Personal Income and Outlays|Gross Domestic Product)', resp.text, re.I | re.S):
                raw_date, label = match.groups()
                try:
                    dt = datetime.strptime(raw_date + ' 13:30', '%B %d, %Y %H:%M').replace(tzinfo=UTC)
                except Exception:
                    continue
                if dt.date() < as_of_date - timedelta(days=3) or dt.date() > as_of_date + timedelta(days=horizon_days):
                    continue
                rows.append({'source_system':'BEA_CALENDAR','event_code':f'BEA_{label}_{dt.date().isoformat()}','category':'statistics_release','title':f'BEA {label} {dt.date().isoformat()}','country':'US','source_tz':'ET','scheduled_at_utc':dt,'release_at_utc':dt,'available_at_utc':dt,'status':'scheduled','url':'https://www.bea.gov/news/schedule','metadata_json':{}})
            return rows
        except Exception:
            return []

    def _fallback_official_event_stream(self, as_of_date: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        macro_sources = [
            ('BLS_RELEASE', 'statistics_release', self._fetch_macro_bls(as_of_date)),
            ('BEA_RELEASE', 'statistics_release', self._fetch_macro_bea(as_of_date)),
            ('FRED_RELEASE', 'market_release', self._fetch_macro_fred(as_of_date)),
        ]
        for source_system, category, items in macro_sources:
            for item in items[:5]:
                release_at = item.get('release_at') or datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC)
                indicator_name = str(item.get('indicator_name') or '')
                rows.append({
                    'source_system': source_system,
                    'event_code': f"{source_system}_{indicator_name}_{release_at.date().isoformat()}",
                    'category': category,
                    'title': f"{indicator_name} release {release_at.date().isoformat()}",
                    'country': str(item.get('country') or 'GLOBAL'),
                    'source_tz': str(item.get('source_tz') or 'UTC'),
                    'scheduled_at_utc': release_at,
                    'release_at_utc': release_at,
                    'available_at_utc': item.get('available_at') or release_at,
                    'status': 'released',
                    'url': '',
                    'metadata_json': {'fallback': True, 'indicator_name': indicator_name},
                })
        return rows

    def _fetch_issue_gdelt(self, as_of_date: date, lookback_days: int) -> list[dict[str, Any]]:
        try:
            resp = httpx.get(
                'https://api.gdeltproject.org/api/v2/doc/doc',
                params={
                    'query': '(Fed OR ECB OR Eurostat OR OECD OR "World Bank" OR inflation OR tariff OR semiconductor) sourcecountry:US OR sourcecountry:GB',
                    'mode': 'ArtList',
                    'maxrecords': 20,
                    'format': 'json',
                    'sort': 'datedesc',
                    'startdatetime': (datetime.combine(as_of_date - timedelta(days=lookback_days), datetime.min.time())).strftime('%Y%m%d%H%M%S'),
                    'enddatetime': (datetime.combine(as_of_date + timedelta(days=1), datetime.min.time())).strftime('%Y%m%d%H%M%S'),
                },
                timeout=25.0,
            )
            if not resp.is_success:
                return []
            body = resp.json()
            rows = []
            for item in body.get('articles', [])[:20]:
                title = str(item.get('title') or '').strip()
                url = str(item.get('url') or '').strip()
                if not title or not url:
                    continue
                rows.append({'source':'GDELT','title':title,'url':url,'publish_time_utc':self._parse_iso_datetime(str(item.get('seendate') or '')) or datetime.now(UTC),'content_text':str(item.get('domain') or ''),'raw_content':b'','raw_ext':'.json'})
            return rows
        except Exception:
            return []

    def _fetch_issue_ecb_rss(self, as_of_date: date, lookback_days: int) -> list[dict[str, Any]]:
        urls = ['https://www.ecb.europa.eu/rss/press.html', 'https://www.ecb.europa.eu/rss/press-release.html']
        for url in urls:
            try:
                resp = httpx.get(url, timeout=20.0, follow_redirects=True)
                if not resp.is_success:
                    continue
                root = ET.fromstring(resp.text)
                out = []
                for item in root.findall('.//item')[:20]:
                    title = self._strip_html(item.findtext('title') or '')
                    link = self._strip_html(item.findtext('link') or '')
                    pub = self._parse_naver_pubdate(item.findtext('pubDate') or '') or self._parse_iso_datetime(item.findtext('pubDate') or '')
                    if not title or not link or not pub:
                        continue
                    if pub.date() < as_of_date - timedelta(days=lookback_days):
                        continue
                    out.append({'source':'ECB_RSS','title':title,'url':link,'publish_time_utc':pub,'content_text':self._strip_html(item.findtext('description') or ''),'raw_content':b'','raw_ext':'.xml'})
                if out:
                    return out
            except Exception:
                continue
        return []

    def _fetch_issue_fed_press(self, as_of_date: date, lookback_days: int) -> list[dict[str, Any]]:
        try:
            resp = httpx.get('https://www.federalreserve.gov/newsevents/pressreleases.htm', timeout=20.0, follow_redirects=True)
            if not resp.is_success:
                return []
            rows = []
            for href, label in re.findall(r"(?is)<a[^>]+href=['\"']([^'\"']+)['\"'][^>]*>(.*?)</a>", resp.text):
                title = self._strip_html(label)
                if '/newsevents/pressreleases/' not in href or not title or re.fullmatch(r'20\d{2}(?:\s+FOMC)?', title):
                    continue
                url = href if href.startswith('http') else f'https://www.federalreserve.gov{href}'
                rows.append({'source':'FED_PRESS','title':title[:300],'url':url,'publish_time_utc':datetime.now(UTC),'content_text':title,'raw_content':b'','raw_ext':'.html'})
                if len(rows) >= 10:
                    break
            return rows
        except Exception:
            return []

    def _fetch_macro_world_bank(self, as_of_date: date) -> list[dict[str, Any]]:
        specs = [
            ("US", "USA", "NY.GDP.MKTP.KD.ZG", "WB_US_REAL_GDP_GROWTH", "growth_support"),
            ("EU", "EMU", "FP.CPI.TOTL.ZG", "WB_EU_INFLATION", "inflation_up_risk"),
            ("GLOBAL", "WLD", "NY.GDP.MKTP.KD.ZG", "WB_GLOBAL_GDP_GROWTH", "growth_support"),
        ]
        out: list[dict[str, Any]] = []
        for country, country_code, indicator_code, indicator_name, bias in specs:
            values = self._fetch_world_bank_indicator(country_code, indicator_code)
            if not values:
                continue
            values.sort(key=lambda x: x[0])
            latest_date, latest_value = values[-1]
            prev_value = values[-2][1] if len(values) >= 2 else latest_value
            out.append(
                self._build_macro_row(
                    as_of_date=as_of_date,
                    observation_date=latest_date,
                    country=country,
                    indicator_name=indicator_name,
                    actual=latest_value,
                    consensus=prev_value,
                    directional_interpretation=self._macro_delta_interpretation(indicator_name, latest_value - prev_value, bias),
                    source_meta={"provider": "WorldBank", "country_code": country_code, "indicator_code": indicator_code},
                    consensus_source='previous',
                    surprise_bias=bias,
                )
            )
        return out

    def _fetch_world_bank_indicator(self, country_code: str, indicator_code: str) -> list[tuple[date, float]]:
        try:
            resp = httpx.get(
                f"https://api.worldbank.org/v2/country/{country_code}/indicator/{indicator_code}",
                params={"format": "json", "per_page": 6},
                timeout=25.0,
                follow_redirects=True,
            )
            if not resp.is_success:
                return []
            body = resp.json()
            if not isinstance(body, list) or len(body) < 2 or not isinstance(body[1], list):
                return []
            out: list[tuple[date, float]] = []
            for item in body[1]:
                raw_year = str(item.get("date") or "")
                value = item.get("value")
                if value in {None, "", "."} or not raw_year.isdigit():
                    continue
                out.append((date(int(raw_year), 12, 31), self._to_float(value)))
            return out
        except Exception:
            return []

    def _fetch_macro_imf(self, as_of_date: date) -> list[dict[str, Any]]:
        specs = [
            ("US", "USA", "NGDP_RPCH", "IMF_US_REAL_GDP_GROWTH", "growth_support"),
            ("EU", "EUQ", "PCPIPCH", "IMF_EU_INFLATION", "inflation_up_risk"),
        ]
        out: list[dict[str, Any]] = []
        for country, area_code, parameter, indicator_name, bias in specs:
            values = self._fetch_imf_indicator(parameter, area_code)
            if not values:
                continue
            values.sort(key=lambda x: x[0])
            latest_date, latest_value = values[-1]
            prev_value = values[-2][1] if len(values) >= 2 else latest_value
            out.append(
                self._build_macro_row(
                    as_of_date=as_of_date,
                    observation_date=latest_date,
                    country=country,
                    indicator_name=indicator_name,
                    actual=latest_value,
                    consensus=prev_value,
                    directional_interpretation=self._macro_delta_interpretation(indicator_name, latest_value - prev_value, bias),
                    source_meta={"provider": "IMF", "parameter": parameter, "area_code": area_code},
                    consensus_source='previous',
                    surprise_bias=bias,
                )
            )
        return out

    def _fetch_imf_indicator(self, parameter: str, area_code: str) -> list[tuple[date, float]]:
        try:
            resp = httpx.get(
                f"https://www.imf.org/external/datamapper/api/v1/{parameter}/{area_code}",
                timeout=25.0,
                follow_redirects=True,
            )
            if not resp.is_success:
                return []
            body = resp.json()
            values_root = body.get("values", {}) if isinstance(body, dict) else {}
            parameter_values = values_root.get(parameter, {}) if isinstance(values_root, dict) else {}
            area_values = parameter_values.get(area_code, {}) if isinstance(parameter_values, dict) else {}
            out: list[tuple[date, float]] = []
            for raw_period, raw_value in area_values.items():
                obs_date = self._parse_imf_period(str(raw_period))
                if obs_date is None or raw_value in {None, "", "."}:
                    continue
                out.append((obs_date, self._to_float(raw_value)))
            return out
        except Exception:
            return []

    def _parse_imf_period(self, raw: str) -> date | None:
        txt = (raw or "").strip()
        if not txt:
            return None
        if re.fullmatch(r"\d{4}", txt):
            return date(int(txt), 12, 31)
        match = re.fullmatch(r"(\d{4})Q([1-4])", txt)
        if match:
            return date(int(match.group(1)), int(match.group(2)) * 3, 1)
        match = re.fullmatch(r"(\d{4})-(\d{2})", txt)
        if match:
            return date(int(match.group(1)), int(match.group(2)), 1)
        return None

    def _fetch_macro_eurostat(self, as_of_date: date) -> list[dict[str, Any]]:
        specs = [
            (
                "EU",
                "EUROSTAT_EA20_UNEMPLOYMENT",
                "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m",
                {"geo": "EA20", "unit": "PC_ACT", "sex": "T", "age": "TOTAL", "s_adj": "SA", "freq": "M", "lang": "en"},
                "labor_softening",
            ),
            (
                "EU",
                "EUROSTAT_EA20_HICP",
                "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr",
                {"geo": "EA20", "coicop": "CP00", "freq": "M", "unit": "RCH_A", "lang": "en"},
                "inflation_up_risk",
            ),
            (
                "EU",
                "EUROSTAT_EU_IND_PRODUCTION",
                "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_inpr_m",
                {"geo": "EA20", "nace_r2": "B-D", "s_adj": "SCA", "unit": "I15", "freq": "M", "lang": "en"},
                "growth_support",
            ),
        ]
        out: list[dict[str, Any]] = []
        for country, indicator_name, url, params, bias in specs:
            values = self._fetch_eurostat_series(url, params)
            if not values:
                continue
            values.sort(key=lambda x: x[0])
            latest_date, latest_value = values[-1]
            prev_value = values[-2][1] if len(values) >= 2 else latest_value
            out.append(
                self._build_macro_row(
                    as_of_date=as_of_date,
                    observation_date=latest_date,
                    country=country,
                    indicator_name=indicator_name,
                    actual=latest_value,
                    consensus=prev_value,
                    directional_interpretation=self._macro_delta_interpretation(indicator_name, latest_value - prev_value, bias),
                    source_meta={"provider": "Eurostat", "url": url, "params": params},
                    consensus_source='previous',
                    surprise_bias=bias,
                )
            )
        return out

    def _fetch_eurostat_series(self, url: str, params: dict[str, Any]) -> list[tuple[date, float]]:
        try:
            resp = httpx.get(url, params=params, timeout=25.0, follow_redirects=True)
            if not resp.is_success:
                return []
            body = resp.json()
            value_map = body.get("value", {}) if isinstance(body, dict) else {}
            if not isinstance(value_map, dict):
                return []
            time_index = body.get("dimension", {}).get("time", {}).get("category", {}).get("index", {})
            if not isinstance(time_index, dict):
                return []
            reverse_index = {int(idx): label for label, idx in time_index.items()}
            out: list[tuple[date, float]] = []
            for key, raw_value in value_map.items():
                try:
                    label = reverse_index.get(int(key), str(key))
                except Exception:
                    label = str(key)
                obs_date = self._parse_eurostat_period(str(label))
                if obs_date is None:
                    continue
                out.append((obs_date, self._to_float(raw_value)))
            return out
        except Exception:
            return []

    def _parse_eurostat_period(self, raw: str) -> date | None:
        txt = (raw or "").strip()
        match = re.search(r"(\d{4})-(\d{2})", txt)
        if match:
            return date(int(match.group(1)), int(match.group(2)), 1)
        match = re.search(r"(\d{4})M(\d{2})", txt)
        if match:
            return date(int(match.group(1)), int(match.group(2)), 1)
        match = re.search(r"(\d{4})", txt)
        if match:
            return date(int(match.group(1)), 12, 31)
        return None

    def _fetch_macro_newsapi(self, as_of_date: date) -> list[dict[str, Any]]:
        key = (self.settings.news_api_key or "").strip()
        if not key:
            return []
        topics = [
            ("inflation OR CPI OR 금리", "GLOBAL_INFLATION_NEWS"),
            ("semiconductor OR 반도체", "SECTOR_SEMICONDUCTOR_NEWS"),
            ("Korea stock market OR KOSPI OR KOSDAQ", "KR_MARKET_NEWS"),
        ]
        out: list[dict[str, Any]] = []
        for query, indicator_name in topics:
            try:
                resp = httpx.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": 10,
                        "from": (as_of_date - timedelta(days=7)).isoformat(),
                        "to": as_of_date.isoformat(),
                        "apiKey": key,
                    },
                    timeout=20.0,
                )
                if not resp.is_success:
                    continue
                body = resp.json()
                articles = body.get("articles", []) if isinstance(body, dict) else []
                if not isinstance(articles, list) or not articles:
                    continue
                scored = []
                for article in articles[:10]:
                    text = " ".join(
                        [
                            str(article.get("title") or ""),
                            str(article.get("description") or ""),
                            str(article.get("content") or ""),
                        ]
                    )
                    sentiment = self._naive_sentiment(text)
                    scored.append(sentiment)
                avg_sentiment = sum(scored) / len(scored) if scored else 0.0
                out.append(
                    {
                        "as_of_date": as_of_date,
                        "observation_date": as_of_date,
                        "release_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
                        "available_at": datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC),
                        "ingested_at": datetime.now(UTC),
                        "revision": "initial",
                        "country": "GLOBAL",
                        "indicator_name": indicator_name,
                        "actual": round(avg_sentiment, 4),
                        "consensus": 0.0,
                        "surprise_std": round(abs(avg_sentiment), 3),
                        "directional_interpretation": "risk_on" if avg_sentiment > 0 else "risk_off" if avg_sentiment < 0 else "neutral",
                        "content_text": " ".join(str(a.get("title") or "") for a in articles[:5]),
                        "source_meta": {"query": query, "article_count": len(articles)},
                    }
                )
            except Exception:
                continue
        return out

    def _fetch_news_newsapi(self, ticker: str, max_items: int = 12, include_content: bool = False) -> list[dict[str, Any]]:
        key = (self.settings.news_api_key or "").strip()
        if not key:
            return []
        instrument = self.resolve_instrument(ticker)
        query_terms = [instrument.name_kr, self._instrument_english_name(instrument.ticker, instrument.name_kr)]
        query_terms = [x for x in query_terms if x]
        query = " OR ".join(f'"{term}"' for term in dict.fromkeys(query_terms))
        if not query:
            return []
        try:
            resp = httpx.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "sortBy": "publishedAt",
                    "pageSize": max(1, min(int(max_items), 30)),
                    "apiKey": key,
                },
                timeout=20.0,
            )
            if not resp.is_success:
                return []
            body = resp.json()
            articles = body.get("articles", []) if isinstance(body, dict) else []
            rows: list[dict[str, Any]] = []
            for idx, item in enumerate(articles):
                title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                if not title or not url:
                    continue
                content_text = " ".join([str(item.get("description") or ""), str(item.get("content") or "")]).strip()
                raw_content = b""
                raw_ext = ".json"
                if include_content and idx < 5 and url:
                    fetched_text, fetched_bytes, fetched_ext = self._fetch_web_document(url)
                    if fetched_text:
                        content_text = fetched_text
                        raw_content = fetched_bytes
                        raw_ext = fetched_ext
                rows.append(
                    {
                        "title": title,
                        "url": url,
                        "publish_time_utc": self._parse_iso_datetime(str(item.get("publishedAt") or "")) or datetime.now(UTC),
                        "sentiment_score": self._naive_sentiment(f"{title} {content_text[:1000]}"),
                        "impact_scope": "market_wide",
                        "content_text": content_text,
                        "raw_content": raw_content,
                        "raw_ext": raw_ext,
                        "source": "newsapi",
                    }
                )
            return rows
        except Exception:
            return []

    def _fetch_price_daily_kis(self, ticker: str, as_of_date: date, lookback_days: int) -> list[dict[str, Any]]:
        app_key = (self.settings.kis_app_key or "").strip()
        app_secret = (self.settings.kis_app_secret or "").strip()
        if not app_key or not app_secret:
            return []

        access_token = ""
        selected = ""
        for base in self._kis_base_candidates():
            tok = self._issue_kis_access_token(base, app_key, app_secret)
            if tok:
                access_token = tok
                selected = base
                break
        if not access_token:
            self._kis_base_url_selected = ""
            return []

        self._kis_base_url_selected = selected
        try:
            resp = httpx.get(
                f"{selected}/uapi/domestic-stock/v1/quotations/inquire-daily-price",
                headers={
                    "authorization": f"Bearer {access_token}",
                    "appkey": app_key,
                    "appsecret": app_secret,
                    "tr_id": "FHKST01010400",
                },
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_input_iscd": ticker,
                    "fid_org_adj_prc": "1",
                    "fid_period_div_code": "D",
                },
                timeout=15.0,
            )
            if not resp.is_success:
                return []
            out = resp.json().get("output2") or resp.json().get("output") or []
            cutoff = as_of_date - timedelta(days=max(lookback_days, 1) + 10)
            rows: list[dict[str, Any]] = []
            for item in out:
                raw = str(item.get("stck_bsop_date") or "").strip()
                if len(raw) != 8:
                    continue
                d = datetime.strptime(raw, "%Y%m%d").date()
                if d > as_of_date or d < cutoff:
                    continue
                rows.append(
                    {
                        "trade_date": d,
                        "open": self._to_float(item.get("stck_oprc")),
                        "high": self._to_float(item.get("stck_hgpr")),
                        "low": self._to_float(item.get("stck_lwpr")),
                        "close": self._to_float(item.get("stck_clpr")),
                        "volume": int(self._to_float(item.get("acml_vol"))),
                    }
                )
            rows.sort(key=lambda x: x["trade_date"])
            return rows[-lookback_days:] if lookback_days > 0 and len(rows) > lookback_days else rows
        except Exception:
            return []

    def _issue_kis_access_token(self, base_url: str, app_key: str, app_secret: str) -> str:
        now = datetime.now(UTC)
        cache_key = f'{base_url}|{app_key}'
        with self._response_cache_lock:
            token_item = self._kis_token_cache.get(cache_key)
            if token_item is not None and token_item[0] > now and token_item[1]:
                return token_item[1]
        try:
            resp = httpx.post(
                f"{base_url}/oauth2/tokenP",
                json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
                timeout=15.0,
            )
            if not resp.is_success:
                return ""
            token = str(resp.json().get("access_token") or "")
            if token:
                expires_at = now + timedelta(seconds=max(60, self.settings.kis_token_ttl_seconds))
                with self._response_cache_lock:
                    self._kis_token_cache[cache_key] = (expires_at, token)
            return token
        except Exception:
            return ""

    def _kis_base_candidates(self) -> list[str]:
        custom = (self.settings.kis_base_url or "").strip()
        prod = (self.settings.kis_prod_base_url or "").strip()
        mock = (self.settings.kis_mock_base_url or "").strip()
        out: list[str] = []
        for x in [custom, prod, mock]:
            if x and x not in out:
                out.append(x)
        return out

    def _fetch_news_naver(self, ticker: str, max_items: int = 20, include_content: bool = False) -> list[dict[str, Any]]:
        cid = (self.settings.naver_client_id or "").strip()
        sec = (self.settings.naver_client_secret or "").strip()
        if not cid or not sec:
            return []
        instrument = self.resolve_instrument(ticker)
        query = instrument.name_kr if instrument.name_kr and instrument.name_kr != ticker else ticker
        try:
            resp = httpx.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec},
                params={"query": query, "display": max(1, min(int(max_items), 100)), "sort": "date"},
                timeout=15.0,
            )
            if not resp.is_success:
                return []
            rows: list[dict[str, Any]] = []
            for i, item in enumerate(resp.json().get("items", [])):
                title = self._strip_html(str(item.get("title") or "")).strip()
                url = str(item.get("originallink") or item.get("link") or "").strip()
                if not title or not url:
                    continue
                content_text = ""
                raw_content = b""
                raw_ext = ".html"
                if include_content and i < 8:
                    content_text, raw_content, raw_ext = self._fetch_web_document(url)
                rows.append(
                    {
                        "title": title,
                        "url": url,
                        "publish_time_utc": self._parse_naver_pubdate(str(item.get("pubDate") or "")) or datetime.now(UTC) - timedelta(hours=i),
                        "sentiment_score": self._naive_sentiment(f"{title} {content_text[:800]}"),
                        "impact_scope": "single_stock",
                        "content_text": content_text,
                        "raw_content": raw_content,
                        "raw_ext": raw_ext,
                    }
                )
            return rows
        except Exception:
            return []

    def _fetch_disclosures_dart(self, ticker: str, as_of_date: date, days: int = 30, include_content: bool = False) -> list[dict[str, Any]]:
        key = (self.settings.dart_api_key or "").strip()
        if not key:
            return []
        corp_code = self._load_dart_corp_code_map().get(ticker)
        if not corp_code:
            return []
        try:
            resp = httpx.get(
                "https://opendart.fss.or.kr/api/list.json",
                params={
                    "crtfc_key": key,
                    "corp_code": corp_code,
                    "bgn_de": (as_of_date - timedelta(days=max(days, 1))).strftime("%Y%m%d"),
                    "end_de": as_of_date.strftime("%Y%m%d"),
                    "page_count": 100,
                },
                timeout=20.0,
            )
            if not resp.is_success:
                return []
            body = resp.json()
            if str(body.get("status")) not in {"000", "013"}:
                return []
            rows: list[dict[str, Any]] = []
            for item in body.get("list", []):
                stock_code = str(item.get("stock_code") or "").strip()
                if stock_code and stock_code != ticker:
                    continue
                rid = str(item.get("rcept_no") or "").strip()
                title = str(item.get("report_nm") or "").strip()
                if not rid or not title:
                    continue
                doc_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rid}"
                content_text = ""
                raw_content = b""
                raw_ext = ".html"
                if include_content and len(rows) < 8:
                    content_text, raw_content, raw_ext = self._fetch_web_document(doc_url)
                rows.append(
                    {
                        "source_disclosure_id": rid,
                        "title": title,
                        "event_type": self._classify_disclosure(title),
                        "publish_time_utc": self._parse_yyyymmdd(str(item.get("rcept_dt") or "")) or datetime.now(UTC),
                        "impact_score": self._estimate_disclosure_impact(f"{title} {content_text[:800]}"),
                        "url": doc_url,
                        "content_text": content_text,
                        "raw_content": raw_content,
                        "raw_ext": raw_ext,
                    }
                )
            rows.sort(key=lambda x: x["publish_time_utc"], reverse=True)
            return rows
        except Exception:
            return []

    def _fetch_financial_statements_dart(self, ticker: str, as_of_date: date) -> dict[str, Any]:
        key = (self.settings.dart_api_key or "").strip()
        if not key:
            return {}
        corp_code = self._load_dart_corp_code_map().get(ticker)
        if not corp_code:
            return {}

        report_meta = self._choose_latest_dart_report(ticker, as_of_date)
        if not report_meta:
            return {}

        bsns_year = report_meta["bsns_year"]
        reprt_code = report_meta["reprt_code"]
        report_nm = report_meta["report_nm"]
        rcept_no = report_meta["rcept_no"]

        for fs_div in ["CFS", "OFS"]:
            try:
                resp = httpx.get(
                    "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
                    params={
                        "crtfc_key": key,
                        "corp_code": corp_code,
                        "bsns_year": bsns_year,
                        "reprt_code": reprt_code,
                        "fs_div": fs_div,
                    },
                    timeout=25.0,
                )
                if not resp.is_success:
                    continue
                body = resp.json()
                if str(body.get("status")) != "000":
                    continue
                rows = body.get("list", [])
                if not isinstance(rows, list) or not rows:
                    continue
                metrics = self._extract_statement_metrics(rows)
                if not metrics:
                    continue
                metrics.update(
                    {
                        "ticker": ticker,
                        "corp_code": corp_code,
                        "report_nm": report_nm,
                        "rcept_no": rcept_no,
                        "bsns_year": bsns_year,
                        "reprt_code": reprt_code,
                        "fs_div": fs_div,
                        "summary_text": self._summarize_financial_statement(metrics),
                        "raw_rows": rows,
                    }
                )
                return metrics
            except Exception:
                continue
        return {}

    def _choose_latest_dart_report(self, ticker: str, as_of_date: date) -> dict[str, str] | None:
        report_keyword = "보고서"
        rows = self._fetch_disclosures_dart(ticker, as_of_date, days=500, include_content=False)
        for row in rows:
            title = str(row.get("title") or "")
            rcept_no = str(row.get("source_disclosure_id") or "")
            if not rcept_no or report_keyword not in title:
                continue
            month_match = re.search(r"\((\d{4})\.(\d{2})\)", title)
            if not month_match:
                continue
            year = month_match.group(1)
            month = month_match.group(2)
            reprt_code = {"03": "11013", "06": "11012", "09": "11014", "12": "11011"}.get(month)
            if not reprt_code:
                continue
            return {"bsns_year": year, "reprt_code": reprt_code, "report_nm": title, "rcept_no": rcept_no}
        return None

    def _extract_statement_metrics(self, rows: list[dict[str, Any]]) -> dict[str, float]:
        revenue_patterns = ["매출액", "영업수익", "revenue", "sales"]
        operating_income_patterns = ["영업이익", "operatingincome", "operatingprofit"]
        net_income_patterns = ["당기순이익", "연결당기순이익", "분기순이익", "netincome", "profitloss"]
        assets_patterns = ["자산총계", "totalassets"]
        liabilities_patterns = ["부채총계", "totalliabilities"]
        equity_patterns = ["자본총계", "totalequity", "equity"]
        current_assets_patterns = ["유동자산", "currentassets"]
        current_liabilities_patterns = ["유동부채", "currentliabilities"]
        operating_cf_patterns = ["영업활동현금흐름", "영업활동으로인한현금흐름", "cashflowsfromusedinoperatingactivities"]

        def amount(patterns: list[str]) -> tuple[float, float]:
            for row in rows:
                account = self._norm_text(str(row.get("account_nm") or row.get("account_id") or ""))
                if any(pattern in account for pattern in patterns):
                    current = self._to_float(row.get("thstrm_amount") or row.get("thstrm_add_amount"))
                    previous = self._to_float(row.get("frmtrm_amount") or row.get("frmtrm_q_amount"))
                    return current, previous
            return 0.0, 0.0

        revenue, revenue_prev = amount(revenue_patterns)
        op_income, _ = amount(operating_income_patterns)
        net_income, _ = amount(net_income_patterns)
        assets, _ = amount(assets_patterns)
        liabilities, _ = amount(liabilities_patterns)
        equity, _ = amount(equity_patterns)
        current_assets, _ = amount(current_assets_patterns)
        current_liabilities, _ = amount(current_liabilities_patterns)
        operating_cf, _ = amount(operating_cf_patterns)

        revenue_growth = ((revenue / revenue_prev) - 1.0) if revenue and revenue_prev else 0.0
        operating_margin = (op_income / revenue) if revenue else 0.0
        net_margin = (net_income / revenue) if revenue else 0.0
        debt_ratio = (liabilities / equity) if equity else 0.0
        current_ratio = (current_assets / current_liabilities) if current_liabilities else 0.0
        ocf_margin = (operating_cf / revenue) if revenue else 0.0

        return {
            "revenue": revenue,
            "revenue_prev": revenue_prev,
            "operating_income": op_income,
            "net_income": net_income,
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
            "operating_cashflow": operating_cf,
            "revenue_growth_yoy": round(revenue_growth, 4),
            "operating_margin": round(operating_margin, 4),
            "net_margin": round(net_margin, 4),
            "debt_ratio": round(debt_ratio, 4),
            "current_ratio": round(current_ratio, 4),
            "operating_cashflow_margin": round(ocf_margin, 4),
        }

    def _summarize_financial_statement(self, metrics: dict[str, Any]) -> str:
        return (
            f"Financial snapshot: revenue_growth_yoy={round(float(metrics.get('revenue_growth_yoy') or 0.0) * 100, 2)}%, "
            f"operating_margin={round(float(metrics.get('operating_margin') or 0.0) * 100, 2)}%, "
            f"net_margin={round(float(metrics.get('net_margin') or 0.0) * 100, 2)}%, "
            f"debt_ratio={round(float(metrics.get('debt_ratio') or 0.0) * 100, 2)}%, "
            f"current_ratio={round(float(metrics.get('current_ratio') or 0.0) * 100, 2)}%, "
            f"operating_cashflow_margin={round(float(metrics.get('operating_cashflow_margin') or 0.0) * 100, 2)}%."
        )

    def _load_dart_corp_code_map(self) -> dict[str, str]:
        return {row["ticker"]: row["corp_code"] for row in self._load_dart_instrument_catalog() if row.get("corp_code")}

    def _load_dart_instrument_catalog(self) -> list[dict[str, str]]:
        now = datetime.now(UTC)
        with self._dart_cache_lock:
            if (
                self._dart_instrument_catalog_cache is not None
                and self._dart_cache_loaded_at is not None
                and (now - self._dart_cache_loaded_at) < timedelta(hours=12)
            ):
                return self._dart_instrument_catalog_cache

            api_key = (self.settings.dart_api_key or "").strip()
            if not api_key:
                return self._dart_instrument_catalog_cache or self._fallback_catalog()

            try:
                resp = httpx.get("https://opendart.fss.or.kr/api/corpCode.xml", params={"crtfc_key": api_key}, timeout=30.0)
                if not resp.is_success:
                    return self._dart_instrument_catalog_cache or self._fallback_catalog()
                root = ET.fromstring(self._extract_corp_code_xml_bytes(resp.content))
                catalog: list[dict[str, str]] = []
                for row in root.findall("./list"):
                    stock = (row.findtext("stock_code") or "").strip()
                    if not stock or len(stock) != 6:
                        continue
                    name = (row.findtext("corp_name") or "").strip() or stock
                    catalog.append(
                        {
                            "ticker": stock,
                            "name_kr": name,
                            "name_norm": self._norm_text(name),
                            "corp_code": (row.findtext("corp_code") or "").strip(),
                            "market": "KR",
                        }
                    )
                if not catalog:
                    return self._dart_instrument_catalog_cache or self._fallback_catalog()
                merged = {x["ticker"]: x for x in catalog}
                for row in self._fallback_catalog():
                    merged.setdefault(row["ticker"], row)
                out = sorted(merged.values(), key=lambda x: x["ticker"])
                self._dart_instrument_catalog_cache = out
                self._dart_cache_loaded_at = now
                return out
            except Exception:
                return self._dart_instrument_catalog_cache or self._fallback_catalog()

    def _extract_corp_code_xml_bytes(self, content: bytes) -> bytes:
        if content[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".xml"):
                        return zf.read(name)
            raise ValueError("No XML file found in corpCode zip")
        return content

    def _fallback_price_daily(self, ticker: str, as_of_date: date, lookback_days: int) -> list[dict[str, Any]]:
        days = max(lookback_days, 60)
        start = as_of_date - timedelta(days=days + 40)
        rows: list[dict[str, Any]] = []
        price = 70000.0 if ticker == "005930" else 100000.0
        volume_base = 1_500_000 if ticker == "005930" else 300_000
        for i in range((as_of_date - start).days + 1):
            d = start + timedelta(days=i)
            if d.weekday() >= 5:
                continue
            drift = ((i % 11) - 5) * 0.0015
            close = max(1000.0, price * (1 + drift))
            rows.append(
                {
                    "trade_date": d,
                    "open": round(close * (1 - 0.002), 2),
                    "high": round(close * 1.006, 2),
                    "low": round(close * 0.994, 2),
                    "close": round(close, 2),
                    "volume": max(int(volume_base * (1 + ((i % 7) - 3) * 0.08)), 1000),
                }
            )
            price = close
        return rows[-lookback_days:] if lookback_days and len(rows) > lookback_days else rows

    def _fallback_news(self, ticker: str, as_of_date: date) -> list[dict[str, Any]]:
        base = datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC)
        return [
            {
                "title": f"{ticker} market sentiment improved",
                "url": f"https://example.com/news/{ticker}/1",
                "publish_time_utc": base - timedelta(hours=10),
                "sentiment_score": 0.25,
                "impact_scope": "single_stock",
                "content_text": f"{ticker} 관련 시장 심리가 개선되었다는 더미 본문입니다.",
                "raw_content": b"",
                "raw_ext": ".txt",
            },
            {
                "title": f"{ticker} outlook remains mixed",
                "url": f"https://example.com/news/{ticker}/2",
                "publish_time_utc": base - timedelta(hours=5),
                "sentiment_score": -0.05,
                "impact_scope": "single_stock",
                "content_text": f"{ticker} 전망이 혼조세라는 더미 본문입니다.",
                "raw_content": b"",
                "raw_ext": ".txt",
            },
        ]

    def _fallback_disclosures(self, ticker: str, as_of_date: date) -> list[dict[str, Any]]:
        base = datetime.combine(as_of_date, datetime.min.time(), tzinfo=UTC)
        return [
            {
                "source_disclosure_id": f"{ticker}-{as_of_date.strftime('%Y%m%d')}-01",
                "title": "single large supply contract",
                "event_type": "contract",
                "publish_time_utc": base - timedelta(days=3),
                "impact_score": 0.3,
                "url": f"https://example.com/disclosure/{ticker}/1",
                "content_text": "단일판매·공급계약 체결 관련 더미 공시 본문입니다.",
                "raw_content": b"",
                "raw_ext": ".txt",
            }
        ]

    def _fallback_catalog(self) -> list[dict[str, str]]:
        # 기본 종목 카탈로그(외부 API 실패 시 사용)
        rows = [
            ("005930", "삼성전자", "00126380"),
            ("000660", "SK하이닉스", "00164779"),
            ("005380", "현대자동차", "00164742"),
            ("035420", "NAVER", "00266961"),
            ("035720", "카카오", "00258801"),
            ("051910", "LG화학", "00356361"),
            ("373220", "LG에너지솔루션", "01515323"),
            ("207940", "삼성바이오로직스", "00616931"),
            ("068270", "셀트리온", "00413046"),
            ("012330", "현대모비스", "00164767"),
        ]
        return [{"ticker": t, "name_kr": n, "name_norm": self._norm_text(n), "corp_code": c, "market": "KR"} for t, n, c in rows]

    def _find_catalog_by_ticker(self, ticker: str) -> dict[str, str] | None:
        for row in self._load_dart_instrument_catalog():
            if row.get("ticker") == ticker:
                return row
        return None

    def _search_alias_candidates(self, query: str) -> list[dict[str, Any]]:
        qn = self._norm_text(query)
        seen: dict[str, dict[str, Any]] = {}
        corp_map = self._load_dart_corp_code_map()
        for alias_key, profile in self._alias_map().items():
            if qn == alias_key or qn == profile.ticker:
                score, mtype = 0.999, "alias_exact"
            elif qn and qn in alias_key:
                score, mtype = 0.96, "alias_contains"
            else:
                score, mtype = self._similarity(qn, alias_key), "alias_fuzzy"
            if score < 0.4:
                continue
            row = {
                "ticker": profile.ticker,
                "name_kr": profile.name_kr,
                "market": profile.market,
                "corp_code": corp_map.get(profile.ticker, ""),
                "score": round(score, 4),
                "match_type": mtype,
            }
            prev = seen.get(profile.ticker)
            if prev is None or row["score"] > prev["score"]:
                seen[profile.ticker] = row
        return list(seen.values())

    def _alias_map(self) -> dict[str, InstrumentProfile]:
        aliases: dict[str, InstrumentProfile] = {}
        for row in self._fallback_catalog():
            p = InstrumentProfile(ticker=row["ticker"], name_kr=row["name_kr"], market=row.get("market", "KR"), sector=self._sector_for_ticker(row["ticker"]))
            aliases[self._norm_text(row["name_kr"])] = p
            aliases[row["ticker"]] = p

        aliases[self._norm_text("삼전")] = aliases.get(self._norm_text("삼성전자"), InstrumentProfile("005930", "삼성전자"))
        aliases[self._norm_text("하이닉스")] = aliases.get(self._norm_text("SK하이닉스"), InstrumentProfile("000660", "SK하이닉스"))
        aliases[self._norm_text("sk hynix")] = aliases.get(self._norm_text("SK하이닉스"), InstrumentProfile("000660", "SK하이닉스"))
        aliases[self._norm_text("네이버")] = aliases.get(self._norm_text("NAVER"), InstrumentProfile("035420", "NAVER"))
        aliases[self._norm_text("현대차")] = aliases.get(self._norm_text("현대자동차"), InstrumentProfile("005380", "현대자동차"))
        return aliases

    def _norm_text(self, value: str) -> str:
        s = (value or "").strip().lower()
        s = s.replace("(주)", "").replace("주식회사", "")
        s = re.sub(r"[\s\-_./]+", "", s)
        return s

    def _similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    def _to_float(self, v: Any) -> float:
        try:
            if v is None:
                return 0.0
            if isinstance(v, (int, float)):
                return float(v)
            txt = str(v).replace(",", "").strip()
            return float(txt) if txt else 0.0
        except Exception:
            return 0.0

    def _strip_html(self, s: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", s or ""))

    def _fetch_web_document(self, url: str) -> tuple[str, bytes, str]:
        try:
            resp = httpx.get(url, timeout=20.0, follow_redirects=True, headers={"User-Agent": "investai-bot/0.3"})
            if not resp.is_success:
                return "", b"", ".html"
            ctype = (resp.headers.get("content-type") or "").lower()
            if "application/pdf" in ctype:
                return self._pdf_to_text(resp.content), resp.content, ".pdf"
            if "application/msword" in ctype:
                txt = resp.content.decode("utf-8", errors="ignore")
                return txt[:20000], resp.content, ".doc"
            if "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in ctype:
                txt = resp.content.decode("utf-8", errors="ignore")
                return txt[:20000], resp.content, ".docx"
            if "application/x-hwp" in ctype or "application/haansofthwp" in ctype:
                txt = resp.content.decode("utf-8", errors="ignore")
                return txt[:20000], resp.content, ".hwp"
            html_txt = resp.text
            plain = self._strip_html(html_txt)
            plain = re.sub(r"\s+", " ", plain).strip()
            return plain[:50000], resp.content, ".html"
        except Exception:
            return "", b"", ".html"

    def _pdf_to_text(self, data: bytes) -> str:
        try:
            from pypdf import PdfReader  # type: ignore
            import io

            reader = PdfReader(io.BytesIO(data))
            pages = [p.extract_text() or "" for p in reader.pages]
            text = " ".join(pages)
            return re.sub(r"\s+", " ", text).strip()[:50000]
        except Exception:
            return data.decode("utf-8", errors="ignore")[:20000]

    def _parse_naver_pubdate(self, s: str) -> datetime | None:
        txt = (s or "").strip()
        if not txt:
            return None
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(txt, fmt).astimezone(UTC)
            except Exception:
                continue
        return None

    def _parse_yyyymmdd(self, s: str) -> datetime | None:
        txt = (s or "").strip()
        if len(txt) != 8:
            return None
        try:
            return datetime.strptime(txt, "%Y%m%d").replace(tzinfo=UTC)
        except Exception:
            return None

    def _parse_iso_datetime(self, s: str) -> datetime | None:
        txt = (s or "").strip()
        if not txt:
            return None
        try:
            return datetime.fromisoformat(txt.replace("Z", "+00:00")).astimezone(UTC)
        except Exception:
            return None

    def _parse_cycle_to_date(self, raw: str) -> date | None:
        txt = (raw or "").strip()
        patterns = [("%Y%m%d", 8), ("%Y%m", 6), ("%YQ%m", 6), ("%Y", 4)]
        for fmt, size in patterns:
            if len(txt) != size:
                continue
            try:
                if fmt == "%YQ%m":
                    year = int(txt[:4])
                    quarter = int(txt[-1])
                    month = quarter * 3
                    return date(year, month, 1)
                return datetime.strptime(txt, fmt).date()
            except Exception:
                continue
        return None

    def _days_since_period(self, raw: str, as_of_date: date) -> int:
        parsed = self._parse_cycle_to_date(raw)
        if parsed is None:
            return 999
        return max((as_of_date - parsed).days, 0)

    def _normalize_macro_level(self, indicator_name: str, value: float) -> float:
        scales = {
            "KRWUSD_CLOSE": 1500.0,
            "KOSPI_INDEX": 3000.0,
            "KOSDAQ_INDEX": 1000.0,
            "KR_TBOND_3Y": 5.0,
            "KR_CORP_AA_3Y": 6.0,
            "KR_CD_91D": 5.0,
            "KR_BASE_RATE": 5.0,
            "KR_M2": 5_000_000.0,
            "KR_EXPORT_VALUE_INDEX": 200.0,
            "US_FED_FUNDS_RATE": 6.0,
            "US_10Y_TREASURY": 6.0,
            "US_UNEMPLOYMENT_RATE": 10.0,
            "US_UNEMPLOYMENT_RATE_BLS": 10.0,
            "US_VIX": 80.0,
            "US_INDUSTRIAL_PRODUCTION": 120.0,
            "US_CPI_INDEX": 400.0,
            "US_NONFARM_PAYROLLS": 200.0,
            "US_REAL_GDP_QOQ": 10.0,
            "US_PCE_PRICE_INDEX": 300.0,
            "US_TOTAL_PUBLIC_DEBT": 40000000000000.0,
            "US_FISCAL_BALANCE": 1000000000000.0,
        }
        scale = scales.get(indicator_name, 100.0)
        return round(value / scale, 3)

    def _normalize_macro_delta(self, indicator_name: str, delta: float) -> float:
        scales = {
            "US_FED_FUNDS_RATE": 0.5,
            "US_10Y_TREASURY": 0.5,
            "US_UNEMPLOYMENT_RATE": 0.5,
            "US_UNEMPLOYMENT_RATE_BLS": 0.5,
            "US_VIX": 5.0,
            "US_INDUSTRIAL_PRODUCTION": 2.0,
            "US_CPI_INDEX": 1.0,
            "US_NONFARM_PAYROLLS": 200.0,
            "US_REAL_GDP_QOQ": 1.0,
            "US_PCE_PRICE_INDEX": 1.0,
            "US_TOTAL_PUBLIC_DEBT": 50000000000.0,
            "US_FISCAL_BALANCE": 100000000000.0,
        }
        scale = scales.get(indicator_name)
        if scale:
            return round(delta / scale, 3)
        return self._normalize_macro_level(indicator_name, delta)

    def _instrument_english_name(self, ticker: str, name_kr: str) -> str:
        mapping = {
            "005930": "Samsung Electronics",
            "000660": "SK hynix",
            "005380": "Hyundai Motor",
            "035420": "NAVER",
            "035720": "Kakao",
            "051910": "LG Chem",
            "373220": "LG Energy Solution",
            "207940": "Samsung Biologics",
            "068270": "Celltrion",
            "012330": "Hyundai Mobis",
        }
        return mapping.get(ticker, name_kr)

    def _naive_sentiment(self, title: str) -> float:
        t = (title or "").lower()
        pos = ["increase", "improve", "growth", "expand", "contract", "record"]
        neg = ["decrease", "deteriorate", "drop", "shrink", "recall", "deficit", "crash"]
        score = 0.0
        if any(k in t for k in pos):
            score += 0.25
        if any(k in t for k in neg):
            score -= 0.25
        return max(-1.0, min(1.0, score))

    def _classify_disclosure(self, title: str) -> str:
        t = (title or "").lower()
        if "contract" in t:
            return "contract"
        if "earning" in t or "profit" in t:
            return "earnings"
        if "cb" in t or "rights issue" in t:
            return "financing"
        if "merge" in t or "split" in t:
            return "mna"
        return "general"

    def _estimate_disclosure_impact(self, title: str) -> float:
        et = self._classify_disclosure(title)
        return {"contract": 0.35, "earnings": 0.25, "financing": -0.15, "mna": 0.2, "general": 0.05}.get(et, 0.05)


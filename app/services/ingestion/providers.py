from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from random import Random
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")

@dataclass
class InstrumentProfile:
    ticker: str
    name_kr: str
    market: str = "KR"
    sector: str = "General"


class SourceProviderClient:
    """Provider facade with real connector attempts + safe fallback."""

    _seed = Random(42)
    _alias = {
        "005930": InstrumentProfile("005930", "삼성전자", sector="반도체"),
        "035420": InstrumentProfile("035420", "NAVER", sector="인터넷"),
        "000660": InstrumentProfile("000660", "SK하이닉스", sector="반도체"),
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        self._kis_token: str | None = None
        self._kis_token_expires_at: datetime | None = None

    def resolve_instrument(self, ticker_or_name: str) -> InstrumentProfile:
        normalized = ticker_or_name.strip().upper().replace(" ", "")
        if normalized in self._alias:
            return self._alias[normalized]
        if normalized.isdigit() and len(normalized) == 6:
            return InstrumentProfile(ticker=normalized, name_kr=normalized, sector="미분류")
        return InstrumentProfile(ticker=normalized, name_kr=ticker_or_name.strip(), sector="미분류")

    def _clean_text(self, value: str) -> str:
        return html.unescape(_TAG_RE.sub("", value or "")).strip()

    def _kis_get_access_token(self) -> str | None:
        if self._kis_token and self._kis_token_expires_at and datetime.now(timezone.utc) < self._kis_token_expires_at:
            return self._kis_token

        if not self.settings.kis_app_key or not self.settings.kis_app_secret:
            return None

        try:
            url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
            payload = {
                "grant_type": "client_credentials",
                "appkey": self.settings.kis_app_key,
                "appsecret": self.settings.kis_app_secret,
            }
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            token = data.get("access_token")
            if not token:
                return None
            self._kis_token = token
            # conservative ttl
            self._kis_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=6)
            return token
        except Exception as exc:
            logger.warning("KIS token request failed: %s", exc)
            return None

    def _fetch_price_daily_kis(self, ticker: str, as_of_date: date, lookback_days: int) -> list[dict]:
        token = self._kis_get_access_token()
        if not token:
            return []
        try:
            headers = {
                "authorization": f"Bearer {token}",
                "appkey": self.settings.kis_app_key,
                "appsecret": self.settings.kis_app_secret,
                "tr_id": "FHKST01010400",
            }
            url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-daily-price"
            params = {
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
                "fid_org_adj_prc": "1",
                "fid_period_div_code": "D",
            }
            with httpx.Client(timeout=12.0) as client:
                resp = client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            output = data.get("output", [])
            if not output:
                return []

            start = as_of_date - timedelta(days=lookback_days)
            rows: list[dict] = []
            for item in output:
                dt_raw = item.get("stck_bsop_date")
                if not dt_raw:
                    continue
                d = datetime.strptime(dt_raw, "%Y%m%d").date()
                if d < start or d > as_of_date:
                    continue
                rows.append(
                    {
                        "trade_date": d,
                        "open": float(item.get("stck_oprc", 0) or 0),
                        "high": float(item.get("stck_hgpr", 0) or 0),
                        "low": float(item.get("stck_lwpr", 0) or 0),
                        "close": float(item.get("stck_clpr", 0) or 0),
                        "volume": int(item.get("acml_vol", 0) or 0),
                    }
                )
            rows.sort(key=lambda x: x["trade_date"])
            return rows
        except Exception as exc:
            logger.warning("KIS daily fetch failed(%s): %s", ticker, exc)
            return []

    def _fetch_news_naver(self, ticker: str, max_items: int = 20) -> list[dict]:
        if not self.settings.naver_client_id or not self.settings.naver_client_secret:
            return []
        try:
            url = "https://openapi.naver.com/v1/search/news.json"
            headers = {
                "X-Naver-Client-Id": self.settings.naver_client_id,
                "X-Naver-Client-Secret": self.settings.naver_client_secret,
            }
            params = {"query": ticker, "display": max_items, "sort": "date"}
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            rows: list[dict] = []
            for item in data.get("items", []):
                pub = item.get("pubDate")
                publish_time = datetime.now(timezone.utc)
                if pub:
                    try:
                        publish_time = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z").astimezone(timezone.utc)
                    except ValueError:
                        pass
                rows.append(
                    {
                        "title": self._clean_text(item.get("title", "")),
                        "url": item.get("originallink") or item.get("link") or "",
                        "publish_time_utc": publish_time,
                        "sentiment_score": 0.0,
                        "impact_scope": "single_stock",
                    }
                )
            return [r for r in rows if r["url"]]
        except Exception as exc:
            logger.warning("Naver news fetch failed(%s): %s", ticker, exc)
            return []

    def _fetch_disclosures_dart(self, ticker: str, as_of_date: date, days: int = 30) -> list[dict]:
        if not self.settings.dart_api_key:
            return []
        try:
            bgn_de = (as_of_date - timedelta(days=days)).strftime("%Y%m%d")
            end_de = as_of_date.strftime("%Y%m%d")
            url = "https://opendart.fss.or.kr/api/list.json"
            params = {
                "crtfc_key": self.settings.dart_api_key,
                "bgn_de": bgn_de,
                "end_de": end_de,
                "page_no": 1,
                "page_count": 100,
            }
            with httpx.Client(timeout=12.0) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            if data.get("status") != "000":
                return []
            rows: list[dict] = []
            for item in data.get("list", []):
                stock_code = (item.get("stock_code") or "").strip()
                if stock_code and stock_code != ticker:
                    continue
                rcept_dt = item.get("rcept_dt")
                rcept_tm = item.get("rcept_no", "")[-6:]
                publish = datetime.now(timezone.utc)
                if rcept_dt and len(rcept_dt) == 8:
                    try:
                        if rcept_tm and rcept_tm.isdigit() and len(rcept_tm) == 6:
                            dt_local = datetime.strptime(f"{rcept_dt}{rcept_tm}", "%Y%m%d%H%M%S")
                        else:
                            dt_local = datetime.strptime(rcept_dt, "%Y%m%d")
                        publish = dt_local.replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
                source_id = item.get("rcept_no") or f"{ticker}-{item.get('report_nm', '')}"
                rows.append(
                    {
                        "source_disclosure_id": source_id,
                        "title": item.get("report_nm", "공시"),
                        "event_type": "disclosure",
                        "publish_time_utc": publish,
                        "impact_score": 0.0,
                    }
                )
            return rows
        except Exception as exc:
            logger.warning("DART disclosure fetch failed(%s): %s", ticker, exc)
            return []

    def fetch_price_daily(self, ticker: str, as_of_date: date, lookback_days: int) -> list[dict]:
        real_rows = self._fetch_price_daily_kis(ticker, as_of_date, lookback_days)
        if real_rows:
            return real_rows

        start = as_of_date - timedelta(days=lookback_days)
        price = 65000.0 + self._seed.randint(-5000, 5000)
        rows: list[dict] = []
        d = start
        while d <= as_of_date:
            drift = self._seed.uniform(-0.02, 0.02)
            close = max(1000.0, price * (1 + drift))
            high = close * (1 + self._seed.uniform(0.0, 0.012))
            low = close * (1 - self._seed.uniform(0.0, 0.012))
            open_price = (close + price) / 2
            volume = int(abs(self._seed.gauss(2_000_000, 700_000)))
            rows.append({"trade_date": d, "open": open_price, "high": high, "low": low, "close": close, "volume": volume})
            price = close
            d += timedelta(days=1)
        return rows

    def fetch_news(self, ticker: str, as_of_date: date, days: int = 30) -> list[dict]:
        real_rows = self._fetch_news_naver(ticker)
        if real_rows:
            return real_rows

        now = datetime.now(timezone.utc)
        return [
            {
                "title": f"{ticker} 수주 확대 기대",
                "url": f"https://example.com/news/{ticker}/1",
                "publish_time_utc": now - timedelta(hours=5),
                "sentiment_score": 0.45,
                "impact_scope": "single_stock",
            },
            {
                "title": f"{ticker} 실적 컨센서스 상회",
                "url": f"https://example.com/news/{ticker}/2",
                "publish_time_utc": now - timedelta(days=2),
                "sentiment_score": 0.60,
                "impact_scope": "single_stock",
            },
        ]

    def fetch_disclosures(self, ticker: str, as_of_date: date, days: int = 90) -> list[dict]:
        real_rows = self._fetch_disclosures_dart(ticker, as_of_date, days=min(days, 30))
        if real_rows:
            return real_rows

        now = datetime.now(timezone.utc)
        return [
            {
                "source_disclosure_id": f"{ticker}-DART-1",
                "title": "단일판매 공급계약 체결",
                "event_type": "contract",
                "publish_time_utc": now - timedelta(days=4),
                "impact_score": 0.55,
            }
        ]

    def fetch_macro(self, as_of_date: date) -> list[dict]:
        return [
            {
                "as_of_date": as_of_date,
                "country": "US",
                "indicator_name": "US_CPI",
                "actual": 3.1,
                "consensus": 3.0,
                "surprise_std": 0.3,
                "directional_interpretation": "inflation_hotter_than_expected",
            },
            {
                "as_of_date": as_of_date,
                "country": "KR",
                "indicator_name": "KR_CPI",
                "actual": 2.3,
                "consensus": 2.4,
                "surprise_std": -0.1,
                "directional_interpretation": "inflation_cooler_than_expected",
            },
        ]

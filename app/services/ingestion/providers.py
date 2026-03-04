from __future__ import annotations

import html
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from threading import Lock
from typing import Any
from xml.etree import ElementTree as ET

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
                return InstrumentProfile(ticker=row["ticker"], name_kr=row["name_kr"], market=row.get("market", "KR"))
            return InstrumentProfile(ticker=q, name_kr=q, market="KR")

        alias = self._alias_map().get(self._norm_text(q))
        if alias:
            return alias

        candidates = self.search_instruments(q, limit=1)
        if candidates:
            c = candidates[0]
            return InstrumentProfile(ticker=c["ticker"], name_kr=c["name_kr"], market=c.get("market", "KR"))

        return InstrumentProfile(ticker=q, name_kr=q, market="KR")

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
        rows = self._fetch_price_daily_kis(ticker, as_of_date, lookback_days)
        return rows or self._fallback_price_daily(ticker, as_of_date, lookback_days)

    def fetch_news(self, ticker: str, as_of_date: date, include_content: bool = False) -> list[dict[str, Any]]:
        rows = self._fetch_news_naver(ticker, max_items=20, include_content=include_content)
        return rows or self._fallback_news(ticker, as_of_date)

    def fetch_disclosures(self, ticker: str, as_of_date: date, include_content: bool = False) -> list[dict[str, Any]]:
        rows = self._fetch_disclosures_dart(ticker, as_of_date, days=30, include_content=include_content)
        return rows or self._fallback_disclosures(ticker, as_of_date)

    def fetch_macro(self, as_of_date: date) -> list[dict[str, Any]]:
        return [
            {
                "as_of_date": as_of_date,
                "country": "KR",
                "indicator_name": "KRWUSD_DAILY_CHANGE",
                "actual": 0.2,
                "consensus": 0.1,
                "surprise_std": 0.1,
                "directional_interpretation": "mild_risk_off",
            },
            {
                "as_of_date": as_of_date,
                "country": "KR",
                "indicator_name": "KOSPI_VOL_PROXY",
                "actual": 0.0,
                "consensus": 0.0,
                "surprise_std": 0.0,
                "directional_interpretation": "neutral",
            },
        ]

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
        try:
            resp = httpx.post(
                f"{base_url}/oauth2/tokenP",
                json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
                timeout=15.0,
            )
            if not resp.is_success:
                return ""
            return str(resp.json().get("access_token") or "")
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
            p = InstrumentProfile(ticker=row["ticker"], name_kr=row["name_kr"], market=row.get("market", "KR"))
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


from __future__ import annotations

from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from sqlalchemy import desc, select

from app.db.models import ExternalDocument
from app.db.session import SessionLocal
from app.schemas.intelligence import MarketPulseOverviewResponse
from app.services.ingestion.providers import SourceProviderClient


class MarketPulseEngine:
    """Market Pulse 엔진."""

    def __init__(self) -> None:
        self.providers = SourceProviderClient()
        self._sector_map = {
            "005930": "반도체",
            "000660": "반도체",
            "035420": "인터넷",
            "035720": "인터넷",
            "051910": "2차전지/화학",
            "373220": "2차전지/화학",
            "207940": "바이오",
            "068270": "바이오",
            "005380": "자동차",
            "012330": "자동차",
        }

    def _classify_regime(self, avg_ret20: float, avg_vol: float, macro_pressure: float) -> tuple[str, float]:
        score = (avg_ret20 * 100) - (avg_vol * 50) - (macro_pressure * 20)
        if score >= 2.5:
            return "리스크온", round(score, 2)
        if score <= -2.5:
            return "리스크오프", round(score, 2)
        return "순환매/중립", round(score, 2)

    def overview(self, as_of_date: date | None = None) -> MarketPulseOverviewResponse:
        d = as_of_date or date.today()
        universe = [x["ticker"] for x in self.providers._fallback_catalog()]
        sector_rows: dict[str, list[dict[str, Any]]] = {}
        reps: list[dict[str, Any]] = []

        ret_list: list[float] = []
        vol_list: list[float] = []
        for t in universe:
            prices = self.providers.fetch_price_daily(t, d, 60)
            closes = [x["close"] for x in prices if x.get("close")]
            if len(closes) < 21:
                continue
            ret20 = (closes[-1] / closes[-21]) - 1
            vol20 = (max(closes[-20:]) - min(closes[-20:])) / max(closes[-20:])
            sec = self._sector_map.get(t, "기타")
            row = {"ticker": t, "ret20": ret20, "vol20": vol20}
            sector_rows.setdefault(sec, []).append(row)
            reps.append(row)
            ret_list.append(ret20)
            vol_list.append(vol20)

        sector_scores: list[dict[str, Any]] = []
        for sec, rows in sector_rows.items():
            sec_ret = mean([x["ret20"] for x in rows])
            sec_vol = mean([x["vol20"] for x in rows])
            score = (sec_ret * 100) - (sec_vol * 30)
            sector_scores.append(
                {
                    "sector": sec,
                    "score": round(score, 2),
                    "ret20_pct": round(sec_ret * 100, 2),
                    "vol20_pct": round(sec_vol * 100, 2),
                    "count": len(rows),
                }
            )
        sector_scores.sort(key=lambda x: x["score"], reverse=True)

        macro = self.providers.fetch_macro(d)
        macro_pressure = mean([x.get("surprise_std") or 0.0 for x in macro]) if macro else 0.0
        avg_ret20 = mean(ret_list) if ret_list else 0.0
        avg_vol20 = mean(vol_list) if vol_list else 0.0
        regime, regime_score = self._classify_regime(avg_ret20, avg_vol20, macro_pressure)

        if regime == "리스크온":
            hints = ["강세 섹터 추세추종, 과열 구간 분할 대응", "실적/모멘텀 동시 확인"]
        elif regime == "리스크오프":
            hints = ["방어 섹터 비중 상향 검토", "현금/저변동 자산 비중 관리"]
        else:
            hints = ["섹터 순환 속도 점검", "단기 이벤트 기반 대응 강화"]

        db = SessionLocal()
        try:
            stmt = (
                select(ExternalDocument)
                .where(ExternalDocument.source_system.in_(["POLICY_BRIEFING", "BOK_PUBLICATIONS"]))
                .order_by(desc(ExternalDocument.created_at_utc))
                .limit(5)
            )
            docs = db.execute(stmt).scalars().all()
            for drow in docs[:3]:
                brief = drow.title
                if isinstance(drow.summary_json, dict):
                    brief = str(drow.summary_json.get("summary") or drow.title)
                hints.append(f"[{drow.source_system}] {brief[:100]}")
        finally:
            db.close()

        market_one_line = f"현재 시장 체제는 {regime}이며, 평균 20일 수익률은 {avg_ret20*100:.2f}%입니다."
        representative_symbols = sorted(reps, key=lambda x: x["ret20"], reverse=True)[:5]
        for r in representative_symbols:
            r["ret20_pct"] = round(r.pop("ret20") * 100, 2)
            r["vol20_pct"] = round(r.pop("vol20") * 100, 2)

        return MarketPulseOverviewResponse(
            as_of_date=d,
            generated_at_utc=datetime.now(timezone.utc),
            market_one_line=market_one_line,
            regime=regime,
            regime_score=regime_score,
            strong_sectors=sector_scores[:3],
            weak_sectors=list(reversed(sector_scores[-3:])),
            macro_summary=macro[:5],
            strategy_hints=hints,
            representative_symbols=representative_symbols,
        )

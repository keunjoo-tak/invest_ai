from __future__ import annotations

from datetime import date, datetime, timezone
from statistics import mean

from sqlalchemy import desc, select

from app.db.models import ExternalDocument
from app.db.session import SessionLocal
from app.schemas.intelligence import StockInsightResponse
from app.services.features.feature_builder import build_features
from app.services.ingestion.providers import SourceProviderClient
from app.services.llm.gemini_client import GeminiClient
from app.services.quality.gates import passes_quality_gate
from app.services.signal.scorer import evaluate_signal


class StockInsightEngine:
    """Stock Insight 엔진."""

    def __init__(self) -> None:
        self.providers = SourceProviderClient()
        self.gemini = GeminiClient()

    def _state_label(self, close: float, ma20: float, ma60: float, rsi14: float) -> str:
        if close > ma20 > ma60 and rsi14 < 72:
            return "상승 추세"
        if close < ma20 < ma60:
            return "하락 추세"
        if rsi14 >= 75:
            return "단기 과열"
        return "박스권/변곡점 탐색"

    def _build_relative_strength(self, ticker: str, as_of_date: date) -> float:
        peers = ["005930", "000660", "035420", "051910", "207940"]
        rows = []
        for t in peers:
            prices = self.providers.fetch_price_daily(t, as_of_date, 40)
            closes = [p["close"] for p in prices if p.get("close")]
            if len(closes) < 21:
                continue
            ret_20d = (closes[-1] / closes[-21]) - 1
            rows.append((t, ret_20d))
        if not rows:
            return 0.0
        target = next((r for t, r in rows if t == ticker), rows[0][1])
        avg = mean([r for _, r in rows])
        return round((target - avg) * 100, 2)

    def analyze(self, ticker_or_name: str, as_of_date: date | None = None) -> StockInsightResponse:
        d = as_of_date or date.today()
        profile = self.providers.resolve_instrument(ticker_or_name)
        prices = self.providers.fetch_price_daily(profile.ticker, d, 365)
        news = self.providers.fetch_news(profile.ticker, d)
        disclosures = self.providers.fetch_disclosures(profile.ticker, d)
        macro = self.providers.fetch_macro(d)

        features = build_features(d, prices, news, disclosures, macro)
        signal = evaluate_signal(features)
        pass_quality, quality_failures = passes_quality_gate(features, signal)
        if not pass_quality:
            signal.risk_flags.extend(quality_failures)

        explanation = self.gemini.explain_signal(
            ticker=profile.ticker,
            signal=signal.model_dump(),
            features=features.model_dump(mode="json"),
        )
        explanation = self.gemini.translate_json_to_korean(explanation)

        state_label = self._state_label(features.close, features.ma_20, features.ma_60, features.rsi_14)
        rel_strength = self._build_relative_strength(profile.ticker, d)
        event_summary = [x["title"] for x in disclosures[:2]] + [x["title"] for x in news[:2]]
        doc_briefs: list[str] = []
        db = SessionLocal()
        try:
            stmt = (
                select(ExternalDocument)
                .where(
                    (ExternalDocument.ticker == profile.ticker)
                    | (ExternalDocument.source_system.in_(["POLICY_BRIEFING", "BOK_PUBLICATIONS"]))
                )
                .order_by(desc(ExternalDocument.created_at_utc))
                .limit(6)
            )
            docs = db.execute(stmt).scalars().all()
            for drow in docs[:3]:
                if isinstance(drow.summary_json, dict):
                    s = str(drow.summary_json.get("summary") or drow.title)
                else:
                    s = drow.title
                doc_briefs.append(f"[{drow.source_system}] {s[:140]}")
        finally:
            db.close()

        event_summary = (event_summary + doc_briefs)[:8]
        one_line = f"{profile.name_kr}은(는) 현재 {state_label} 구간이며 신호 점수는 {signal.score}점입니다."

        if features.close <= 0:
            valuation = "가격 데이터 부족으로 밸류에이션 요약을 생성하지 못했습니다."
        else:
            valuation = f"현재가 대비 MA20 괴리율 {(features.close / max(features.ma_20, 1) - 1) * 100:.2f}%."

        flow_summary = f"상대 거래량 {features.rel_volume}배, 뉴스 감성 {features.news_sentiment_7d}."
        technical_summary = f"RSI14 {features.rsi_14}, 변동성(20일) {features.volatility_20d}."

        checkpoints = [
            "공시 신규 발생 여부",
            "거래량 급증 지속 여부",
            "섹터 상대강도 반전 여부",
        ]
        if features.rsi_14 >= 75:
            checkpoints.append("단기 과열 해소(눌림) 확인")

        return StockInsightResponse(
            ticker=profile.ticker,
            instrument_name=profile.name_kr,
            as_of_date=d,
            generated_at_utc=datetime.now(timezone.utc),
            one_line_diagnosis=one_line,
            state_label=state_label,
            valuation_summary=valuation,
            event_summary=event_summary,
            earnings_summary=f"공시 이벤트 평균 영향도 {features.disclosure_impact_30d}.",
            flow_summary=flow_summary,
            technical_summary=technical_summary,
            sector_relative_strength=rel_strength,
            risk_factors=signal.risk_flags,
            checkpoints=checkpoints,
            features=features,
            signal=signal,
            explanation=explanation,
        )

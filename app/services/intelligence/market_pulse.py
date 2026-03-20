from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from statistics import mean
from threading import Lock
from typing import Any

from sqlalchemy import desc, or_, select

from app.db.models import ExternalDocument
from app.db.session import SessionLocal
from app.schemas.intelligence import MarketPulseOverviewResponse
from app.services.ingestion.providers import SourceProviderClient
from app.services.ingestion.research_repair import ResearchDocumentRepairService


class MarketPulseEngine:
    """가격 폭, 섹터 강도, 거시 문서, 헤드라인 뉴스를 결합해 시장 체제를 계산한다."""

    _overview_cache: dict[str, tuple[datetime, MarketPulseOverviewResponse]] = {}
    _overview_cache_lock: Lock = Lock()
    _market_regime_allowed_report_types = {
        "morning_outlook",
        "close_outlook",
        "daily_strategy",
        "weekly_strategy",
        "monthly_strategy",
        "macro",
        "rates",
        "fx",
        "credit",
        "commodity",
        "policy_brief",
        "sector_report",
        "real_estate",
    }
    _market_regime_preferred_terms = (
        "market",
        "strategy",
        "outlook",
        "macro",
        "rates",
        "fx",
        "credit",
        "inflation",
        "gdp",
        "liquidity",
        "policy",
        "yield",
        "usd/krw",
        "??",
        "??",
        "??",
        "??",
        "??",
        "??",
        "??",
        "??",
        "???",
        "???",
        "???",
        "??",
        "??",
        "??",
    )
    _market_regime_exclude_terms = (
        "attention/transformer",
        "transformer",
        "embedding",
        "layer normalization",
        "residual connection",
        "code example",
        "python tutorial",
        "quant modeling",
        "?? ???",
        "?????",
        "???",
        "??? ???",
        "?? ??",
    )
    _market_regime_disclaimer_terms = (
        "? ???",
        "?? ??",
        "?? ??",
        "??? ? ????",
        "?? ??",
        "??? ????",
        "?? ??? ??",
    )

    def __init__(self) -> None:
        self.providers = SourceProviderClient()
        self.research_repair = ResearchDocumentRepairService()
        self._ttl_seconds = max(60, self.providers.settings.product_cache_ttl_seconds)
        self._sector_map = {
            '005930': '반도체',
            '000660': '반도체',
            '035420': '인터넷',
            '035720': '인터넷',
            '051910': '2차전지·화학',
            '373220': '2차전지·화학',
            '207940': '바이오',
            '068270': '바이오',
            '005380': '자동차',
            '012330': '자동차',
        }
        self._headline_focus_map = {
            'politics': '정책·규제·외교 리스크',
            'economy_finance': '금리·유동성·금융 시스템 안정성',
            'economy_securities': '위험선호·수급 심리·증시 자금 흐름',
            'economy_realestate': '부동산·가계부채·내수 경기 민감도',
            'it_science': '기술 투자 심리·반도체·성장주 밸류에이션',
            'world': '글로벌 리스크·수출·공급망 환경',
        }
        self._headline_label_map = {
            'politics': '정치',
            'economy_finance': '경제-금융',
            'economy_securities': '경제-증권',
            'economy_realestate': '경제-부동산',
            'it_science': 'IT/과학',
            'world': '세계',
        }

    def _classify_regime(self, avg_ret20: float, avg_vol: float, macro_pressure: float) -> tuple[str, float]:
        score = (avg_ret20 * 100) - (avg_vol * 50) - (macro_pressure * 20)
        if score >= 2.5:
            return '위험선호', round(score, 2)
        if score <= -2.5:
            return '위험회피', round(score, 2)
        return '중립', round(score, 2)

    def _headline_direction(self, avg_sentiment: float, avg_impact: float) -> str:
        composite = (avg_sentiment * 0.55) + (avg_impact * 0.45)
        if composite >= 0.22:
            return '긍정 우위'
        if composite <= -0.05:
            return '부정 우위'
        return '중립 또는 혼조'

    def _headline_briefs(self, db: Any, target_date: date) -> list[dict[str, Any]]:
        cutoff = datetime.combine(target_date - timedelta(days=4), time.min, tzinfo=timezone.utc)
        stmt = (
            select(ExternalDocument)
            .where(
                (ExternalDocument.source_system == 'NAVER_HEADLINE_NEWS')
                & (
                    or_(
                        ExternalDocument.publish_time_utc >= cutoff,
                        ExternalDocument.created_at_utc >= cutoff,
                    )
                )
            )
            .order_by(desc(ExternalDocument.publish_time_utc), desc(ExternalDocument.created_at_utc))
        )
        rows = db.execute(stmt).scalars().all()
        grouped: dict[str, list[ExternalDocument]] = {}
        for row in rows:
            row = self.research_repair.ensure_document_ready(db, row)
            meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            section_key = str(meta.get('section_key') or row.category or 'general')
            grouped.setdefault(section_key, []).append(row)

        briefs: list[dict[str, Any]] = []
        for section_key, items in grouped.items():
            sentiments: list[float] = []
            impacts: list[float] = []
            freshness: list[float] = []
            summaries: list[str] = []
            titles: list[str] = []
            article_rows: list[dict[str, Any]] = []
            latest_at: datetime | None = None
            section_label = self._headline_label_map.get(section_key, section_key)
            focus = self._headline_focus_map.get(section_key, '시장 심리와 위험선호')

            for item in items:
                meta = item.metadata_json if isinstance(item.metadata_json, dict) else {}
                score_row = meta.get('scores') if isinstance(meta.get('scores'), dict) else {}
                summary = item.summary_json if isinstance(item.summary_json, dict) else {}
                current_at = item.publish_time_utc or item.created_at_utc
                titles.append(item.title)
                summary_text = str(summary.get('summary') or item.title)
                summaries.append(summary_text)
                article_rows.append(
                    {
                        'title': item.title,
                        'url': item.url,
                        'summary': summary_text,
                        'published_at_utc': current_at,
                    }
                )
                sentiments.append(float(score_row.get('sentiment_score') or 0.0))
                impacts.append(float(score_row.get('impact_score') or 0.0))
                freshness.append(float(score_row.get('freshness_score') or 0.0))
                if current_at and (latest_at is None or current_at > latest_at):
                    latest_at = current_at
                if meta.get('section_label'):
                    section_label = str(meta.get('section_label'))

            avg_sentiment = mean(sentiments) if sentiments else 0.0
            avg_impact = mean(impacts) if impacts else 0.0
            avg_freshness = mean(freshness) if freshness else 0.0
            direction = self._headline_direction(avg_sentiment, avg_impact)
            if direction == '긍정 우위':
                market_impact = f'최근 5일 {section_label} 헤드라인은 {focus} 측면에서 위험선호를 지지하는 흐름입니다.'
            elif direction == '부정 우위':
                market_impact = f'최근 5일 {section_label} 헤드라인은 {focus} 측면에서 단기 위험회피 심리를 자극하는 흐름입니다.'
            else:
                market_impact = f'최근 5일 {section_label} 헤드라인은 {focus} 측면에서 뚜렷한 한 방향보다 혼조 흐름을 보이고 있습니다.'

            briefs.append(
                {
                    'section_key': section_key,
                    'section_label': section_label,
                    'headline_count': len(items),
                    'impact_direction': direction,
                    'impact_score': round((avg_sentiment * 0.55) + (avg_impact * 0.45), 3),
                    'avg_sentiment_score': round(avg_sentiment, 3),
                    'avg_impact_score': round(avg_impact, 3),
                    'avg_freshness_score': round(avg_freshness, 3),
                    'focus': focus,
                    'market_impact': market_impact,
                    'headline_digest': ' / '.join(titles[:3]),
                    'top_headlines': titles[:5],
                    'summary_points': summaries[:3],
                    'top_articles': article_rows[:5],
                    'latest_published_at_utc': latest_at,
                }
            )

        briefs.sort(key=lambda row: (abs(float(row.get('impact_score') or 0.0)), int(row.get('headline_count') or 0)), reverse=True)
        return briefs

    def _market_regime_research_relevance(self, row: ExternalDocument, meta: dict[str, Any], summary_text: str) -> float:
        report_type = str(meta.get("report_type") or row.category or "")
        report_scope = str(meta.get("report_scope") or "")
        text_blob = "\n".join([
            str(row.title or ""),
            str(summary_text or ""),
            str(meta.get("evidence_snippet") or ""),
        ]).lower()

        if report_type == "company_report":
            return 0.0

        score = 0.0
        if report_type in self._market_regime_allowed_report_types:
            score += 0.45
        elif report_type in {"theme_report", "etf_report"}:
            score += 0.12
        else:
            score += 0.05

        if report_scope == "market":
            score += 0.25
        elif report_scope == "sector":
            score += 0.12
        elif report_scope == "company":
            score += 0.05

        if list(meta.get("sector_tags") or []):
            score += 0.05

        preferred_hits = sum(1 for token in self._market_regime_preferred_terms if token in text_blob)
        score += min(0.25, preferred_hits * 0.04)

        if any(token in text_blob for token in self._market_regime_exclude_terms):
            score -= 0.90
        if any(token in summary_text for token in self._market_regime_disclaimer_terms):
            score -= 0.70

        research_scores = meta.get("research_scores") if isinstance(meta.get("research_scores"), dict) else {}
        score += min(0.08, float(research_scores.get("actionability_score") or 0.0) * 0.08)
        return round(max(0.0, min(1.0, score)), 3)

    def _research_briefs(self, db: Any, target_date: date) -> tuple[list[dict[str, Any]], float]:
        cutoff = datetime.combine(target_date - timedelta(days=6), time.min, tzinfo=timezone.utc)
        stmt = (
            select(ExternalDocument)
            .where(
                (ExternalDocument.source_system == 'PUBLIC_RESEARCH_REPORTS')
                & (
                    or_(
                        ExternalDocument.publish_time_utc >= cutoff,
                        ExternalDocument.created_at_utc >= cutoff,
                    )
                )
            )
            .order_by(desc(ExternalDocument.publish_time_utc), desc(ExternalDocument.created_at_utc))
        )
        rows = db.execute(stmt).scalars().all()
        briefs: list[dict[str, Any]] = []
        weighted_bias: list[tuple[float, float]] = []
        for row in rows:
            row = self.research_repair.ensure_document_ready(db, row)
            meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            if 'market_regime' not in list(meta.get('service_targets') or ['market_regime']):
                continue
            summary = row.summary_json if isinstance(row.summary_json, dict) else {}
            summary_text = str(summary.get('summary') or meta.get('evidence_snippet') or row.title)
            relevance_score = self._market_regime_research_relevance(row, meta, summary_text)
            if relevance_score < 0.45:
                continue

            scores = meta.get('research_scores') if isinstance(meta.get('research_scores'), dict) else {}
            freshness = float(scores.get('freshness_score') or 0.45)
            house_quality = float(scores.get('house_quality_score') or meta.get('house_quality_score') or 0.75)
            feature_confidence = float(meta.get('feature_confidence') or 0.55)
            weight = max(0.1, round((freshness * 0.45) + (house_quality * 0.35) + (feature_confidence * 0.20), 3))
            risk_on_off = float(scores.get('risk_on_off_score') or 0.0)
            policy_risk = float(scores.get('policy_risk_score') or 0.0)
            geopolitical_risk = float(scores.get('geopolitical_risk_score') or 0.0)
            composite_bias = max(-1.0, min(1.0, risk_on_off - (policy_risk * 0.35) - (geopolitical_risk * 0.25)))
            weighted_bias.append((weight, composite_bias))
            briefs.append(
                {
                    'house_name': meta.get('house_name') or row.source_id,
                    'report_type': meta.get('report_type') or row.category,
                    'stance': meta.get('stance') or 'neutral',
                    'summary': summary_text,
                    'published_at_utc': row.publish_time_utc or row.created_at_utc,
                    'url': row.url,
                    'sector_tags': list(meta.get('sector_tags') or []),
                    'contribution_score': round(composite_bias * weight, 3),
                    'weight': weight,
                    'relevance_score': relevance_score,
                }
            )
        briefs.sort(
            key=lambda item: (
                float(item.get('relevance_score') or 0.0),
                abs(float(item.get('contribution_score') or 0.0)),
            ),
            reverse=True,
        )
        if not weighted_bias:
            return briefs[:6], 0.0
        total_weight = sum(weight for weight, _ in weighted_bias) or 1.0
        research_bias = round(sum(weight * bias for weight, bias in weighted_bias) / total_weight, 3)
        return briefs[:6], research_bias

    def overview(self, as_of_date: date | None = None) -> MarketPulseOverviewResponse:
        target_date = as_of_date or date.today()
        cache_key = target_date.isoformat()
        now = datetime.now(timezone.utc)
        with self._overview_cache_lock:
            cached = self._overview_cache.get(cache_key)
            if cached is not None and cached[0] > now:
                return cached[1].model_copy(deep=True)

        universe = [row['ticker'] for row in self.providers._fallback_catalog()]
        sector_rows: dict[str, list[dict[str, Any]]] = {}
        representative_rows: list[dict[str, Any]] = []
        ret_list: list[float] = []
        vol_list: list[float] = []

        for ticker in universe:
            prices = self.providers.fetch_price_daily(ticker, target_date, 60)
            closes = [row['close'] for row in prices if row.get('close')]
            if len(closes) < 21:
                continue
            ret20 = (closes[-1] / closes[-21]) - 1
            vol20 = (max(closes[-20:]) - min(closes[-20:])) / max(closes[-20:])
            sector = self._sector_map.get(ticker, '기타')
            profile = self.providers.resolve_instrument(ticker)
            row = {'ticker': ticker, 'name': profile.name_kr, 'ret20': ret20, 'vol20': vol20}
            sector_rows.setdefault(sector, []).append(row)
            representative_rows.append(row)
            ret_list.append(ret20)
            vol_list.append(vol20)

        sector_scores: list[dict[str, Any]] = []
        for sector, rows in sector_rows.items():
            sector_ret = mean(item['ret20'] for item in rows)
            sector_vol = mean(item['vol20'] for item in rows)
            score = (sector_ret * 100) - (sector_vol * 30)
            sector_scores.append(
                {
                    'sector': sector,
                    'score': round(score, 2),
                    'ret20_pct': round(sector_ret * 100, 2),
                    'vol20_pct': round(sector_vol * 100, 2),
                    'count': len(rows),
                }
            )
        sector_scores.sort(key=lambda item: item['score'], reverse=True)

        macro = self.providers.fetch_macro(target_date)
        macro_pressure = mean([row.get('surprise_std') or 0.0 for row in macro]) if macro else 0.0
        avg_ret20 = mean(ret_list) if ret_list else 0.0
        avg_vol20 = mean(vol_list) if vol_list else 0.0
        regime, regime_score = self._classify_regime(avg_ret20, avg_vol20, macro_pressure)
        research_briefs: list[dict[str, Any]] = []
        research_regime_bias = 0.0

        if regime == '위험선호':
            hints = [
                '강한 섹터의 주도주 위주로 접근하되 급등 추격은 피하는 편이 좋습니다.',
                '거래대금 증가와 이벤트 후속 확인이 동반될 때만 비중 확대를 고려합니다.',
            ]
        elif regime == '위험회피':
            hints = [
                '총 익스포저를 줄이고 손절 기준과 무효화 조건을 더 엄격하게 잡는 편이 좋습니다.',
                '방어적 섹터나 촉매가 명확한 종목만 선별적으로 보는 접근이 적절합니다.',
            ]
        else:
            hints = [
                '시장 체제 확인 전까지는 무리한 비중 확대보다 선별 대응이 유리합니다.',
                '이벤트 드리븐 대응은 가능하지만 진입 규모는 보수적으로 관리하는 편이 좋습니다.',
            ]

        headline_news_briefs: list[dict[str, Any]] = []
        db = SessionLocal()
        try:
            stmt = (
                select(ExternalDocument)
                .where(ExternalDocument.source_system.in_(['POLICY_BRIEFING', 'BOK_PUBLICATIONS', 'GLOBAL_MACRO_INTEL', 'INTERNATIONAL_MACRO_INTEL']))
                .order_by(desc(ExternalDocument.created_at_utc))
                .limit(5)
            )
            docs = db.execute(stmt).scalars().all()
            for row in docs[:3]:
                brief = row.title
                if isinstance(row.summary_json, dict):
                    brief = str(row.summary_json.get('summary') or row.title)
                hints.append(f'[{row.source_system}] {brief[:100]}')
            headline_news_briefs = self._headline_briefs(db, target_date)
            for row in headline_news_briefs[:2]:
                hints.append(f"[헤드라인/{row['section_label']}] {row['market_impact']}")
            research_briefs, research_regime_bias = self._research_briefs(db, target_date)
            for row in research_briefs[:3]:
                hints.append(f"[리서치/{row['house_name']}] {row['summary'][:100]}")
        finally:
            db.close()

        regime_score = round(regime_score + (research_regime_bias * 2.0), 2)
        if regime_score >= 2.5:
            regime = '위험선호'
        elif regime_score <= -2.5:
            regime = '위험회피'
        else:
            regime = '중립'

        market_one_line = f'현재 시장 체제는 {regime}이며, 최근 20거래일 평균 수익률은 {avg_ret20 * 100:.2f}%입니다.'
        representative_symbols = sorted(representative_rows, key=lambda item: item['ret20'], reverse=True)[:5]
        for row in representative_symbols:
            row['ret20_pct'] = round(row.pop('ret20') * 100, 2)
            row['vol20_pct'] = round(row.pop('vol20') * 100, 2)

        response = MarketPulseOverviewResponse(
            as_of_date=target_date,
            generated_at_utc=datetime.now(timezone.utc),
            market_one_line=market_one_line,
            regime=regime,
            regime_score=regime_score,
            strong_sectors=sector_scores[:3],
            weak_sectors=list(reversed(sector_scores[-3:])),
            macro_summary=macro[:5],
            strategy_hints=hints,
            representative_symbols=representative_symbols,
            headline_news_briefs=headline_news_briefs,
            research_briefs=research_briefs,
        )
        with self._overview_cache_lock:
            self._overview_cache[cache_key] = (
                datetime.now(timezone.utc) + timedelta(seconds=self._ttl_seconds),
                response.model_copy(deep=True),
            )
        return response

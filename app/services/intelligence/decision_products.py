from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from statistics import mean, pstdev
from threading import Lock
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ExternalDocument, Instrument, WatchlistSubscription
from app.schemas.analysis import AnalyzeTickerRequest, AnalyzeTickerResponse
from app.schemas.decision_products import (
    ActionPlannerRequest,
    ActionPlannerResponse,
    ActionScenario,
    MarketRegimeResponse,
    StockDecisionResponse,
    WatchlistAlertRequest,
    WatchlistAlertResponse,
    WatchlistSubscriptionDeleteResponse,
    WatchlistSubscriptionRequest,
    WatchlistSubscriptionResponse,
)
from app.services.alerts.formatter import format_alert_message
from app.services.ingestion.research_repair import ResearchDocumentRepairService
from app.services.intelligence.market_pulse import MarketPulseEngine
from app.services.intelligence.snapshot_store import ProductSnapshotStore
from app.services.localization.signal_localizer import has_risk_flag
from app.services.pipeline.orchestrator import AnalysisPipeline

logger = logging.getLogger(__name__)


class DecisionProductService:
    def __init__(self) -> None:
        self.pipeline = AnalysisPipeline()
        self.market = MarketPulseEngine()
        self.snapshot_store = ProductSnapshotStore()
        self.research_repair = ResearchDocumentRepairService()
        self._ttl_seconds = max(60, get_settings().product_cache_ttl_seconds)
        self._snapshot_ttl_seconds = max(self._ttl_seconds, 6 * 60 * 60)
        self._cache_lock = Lock()
        self._cache: dict[str, tuple[datetime, Any]] = {}

    async def run_core_analysis(
        self,
        db: Session,
        ticker_or_name: str,
        as_of_date: date | None = None,
        lookback_days: int = 365,
        notify: bool = False,
        force_send: bool = False,
    ) -> AnalyzeTickerResponse:
        normalized = self._normalize_ticker_or_name(ticker_or_name)
        cache_key = f"core:{normalized}:{as_of_date.isoformat() if as_of_date else 'today'}:{lookback_days}:{int(notify)}:{int(force_send)}"
        use_cache = not notify and not force_send
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
        req = AnalyzeTickerRequest(
            ticker_or_name=normalized,
            as_of_date=as_of_date,
            lookback_days=lookback_days,
            analysis_mode='quick',
            notify=notify,
            force_send=force_send,
            channels=['telegram'] if notify or force_send else [],
            response_language='ko',
        )
        try:
            response = await self.pipeline.run(db, req)
        except Exception:
            stale = self._cache_peek_stale(cache_key) if use_cache else None
            if stale is not None:
                logger.exception('core analysis failed; serving stale cache for %s', normalized)
                return stale
            raise
        if use_cache:
            self._cache_set(cache_key, response)
        return response

    def _clip(self, value: float) -> float:
        return round(max(0.0, min(100.0, value)), 2)

    def _normalize_ticker_or_name(self, ticker_or_name: str) -> str:
        value = (ticker_or_name or '').strip()
        if not value:
            raise ValueError('ticker_or_name is required')
        return value

    def _cache_get(self, key: str) -> Any | None:
        now = datetime.now(timezone.utc)
        with self._cache_lock:
            item = self._cache.get(key)
            if item is None:
                return None
            expires_at, payload = item
            if expires_at <= now:
                self._cache.pop(key, None)
                return None
            return payload.model_copy(deep=True) if hasattr(payload, 'model_copy') else payload

    def _cache_peek_stale(self, key: str) -> Any | None:
        with self._cache_lock:
            item = self._cache.get(key)
            if item is None:
                return None
            payload = item[1]
            return payload.model_copy(deep=True) if hasattr(payload, 'model_copy') else payload

    def _cache_set(self, key: str, payload: Any, ttl_seconds: int | None = None) -> Any:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(1, ttl_seconds or self._ttl_seconds))
        copied = payload.model_copy(deep=True) if hasattr(payload, 'model_copy') else payload
        with self._cache_lock:
            self._cache[key] = (expires_at, copied)
        return payload

    def _decorate_pipeline_status(self, payload: Any, **updates: Any) -> Any:
        current = dict(getattr(payload, 'pipeline_status', {}) or {})
        current.update({key: value for key, value in updates.items() if value is not None})
        return payload.model_copy(update={'pipeline_status': current}, deep=True)

    def _pipeline_status(self, response_source: str, analysis_mode: str, **kwargs: Any) -> dict[str, Any]:
        labels = {
            'memory_cache': '메모리 캐시',
            'stale_memory_cache': '이전 캐시 복구',
            'batch_snapshot': '배치 스냅샷',
            'batch_build': '배치 생성',
            'live_collection': '실시간 수집',
            'live_check': '실시간 점검',
            'derived_from_stock_decision': '종목 판단 기반',
        }
        payload = {
            'response_source': response_source,
            'response_source_label': labels.get(response_source, response_source),
            'analysis_mode': analysis_mode,
        }
        payload.update({key: value for key, value in kwargs.items() if value is not None})
        return payload

    def _component_scores(self, analysis: AnalyzeTickerResponse) -> dict[str, float]:
        f = analysis.features
        market_score = 50 + (f.macro_support_score * 24) - (max(0.0, f.macro_pressure_score) * 26) + (f.macro_global_score * 12)
        sector_score = (
            50
            + (f.price_vs_ma20 * 55)
            + (f.return_20d * 28)
            + ((f.rel_volume - 1.0) * 8)
            + (f.sector_fund_flow_score * 18)
            + ((f.sector_coupling_score - 0.5) * 24)
            + (f.sector_breadth_score * 10)
            + (f.sector_leader_relative_strength * 20)
        )
        stock_specific_score = 50 + (f.revenue_growth_yoy * 35) + (f.operating_margin * 45) + (f.net_margin * 25) - (max(f.debt_ratio - 1.0, 0.0) * 12)
        event_score = 50 + (f.news_sentiment_7d * 15) + (f.disclosure_impact_30d * 20) + (f.supply_contract_score * 18) - (f.financing_risk_score * 20)
        valuation_score = 50 + (f.operating_cashflow_margin * 40) + ((f.current_ratio - 1.0) * 8) + (f.shareholder_return_score * 12) + (f.governance_score * 8)
        return {
            'market_score': self._clip(market_score),
            'sector_score': self._clip(sector_score),
            'stock_specific_score': self._clip(stock_specific_score),
            'event_score': self._clip(event_score),
            'valuation_score': self._clip(valuation_score),
        }

    def _horizon_scores(self, analysis: AnalyzeTickerResponse, components: dict[str, float]) -> dict[str, float]:
        f = analysis.features
        short_term = (
            components['event_score'] * 0.35
            + components['sector_score'] * 0.25
            + components['market_score'] * 0.15
            + (50 + f.return_5d * 180) * 0.15
            + (50 + (f.news_attention_score * 25) - (abs(f.gap_return_1d) * 120)) * 0.10
        )
        swing = (
            components['sector_score'] * 0.30
            + components['event_score'] * 0.20
            + components['market_score'] * 0.20
            + components['stock_specific_score'] * 0.15
            + (50 + f.price_vs_ma20 * 150 + f.return_20d * 80) * 0.15
        )
        midterm = (
            components['stock_specific_score'] * 0.35
            + components['valuation_score'] * 0.25
            + components['market_score'] * 0.20
            + components['sector_score'] * 0.10
            + (50 + f.macro_global_score * 15 + f.revenue_growth_yoy * 30) * 0.10
        )
        return {
            'short_term_score': self._clip(short_term),
            'swing_score': self._clip(swing),
            'midterm_score': self._clip(midterm),
        }

    def _state_label(self, analysis: AnalyzeTickerResponse) -> str:
        f = analysis.features
        if has_risk_flag(analysis.signal, 'EVENT_DAY_VOLATILITY_MODE'):
            return '변동성 주의'
        if f.close > f.ma_20 > f.ma_60 and f.rsi_14 < 72:
            return '상승 추세'
        if f.close < f.ma_20 < f.ma_60:
            return '하락 추세'
        if f.rsi_14 >= 75:
            return '단기 과열'
        return '중립 또는 박스권'

    def _relative_strength(self, analysis: AnalyzeTickerResponse) -> float:
        f = analysis.features
        return round(
            (f.return_20d * 100)
            - (f.macro_pressure_score * 10)
            + (f.news_attention_score * 5)
            + (f.sector_leader_relative_strength * 40)
            + (f.sector_fund_flow_score * 10),
            2,
        )

    def _label_source(self, source: str) -> str:
        mapping = {
            'news': '뉴스',
            'disclosure': '공시',
            'document': '문서',
            'financial_statement': '재무제표',
            'POLICY_BRIEFING': '정책브리핑',
            'BOK_PUBLICATIONS': '한국은행',
        }
        return mapping.get(source, source.replace('_', ' '))

    def _label_event_type(self, event_type: str) -> str:
        mapping = {
            'news': '뉴스',
            'disclosure': '공시',
            'contract': '계약',
            'earnings': '실적',
            'policy': '정책',
        }
        key = (event_type or '').strip()
        return mapping.get(key, key.replace('_', ' ')) or '이벤트'

    def _timeline(self, analysis: AnalyzeTickerResponse) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = []
        for item in analysis.explanation.get('document_summaries', [])[:7]:
            source = self._label_source(str(item.get('source') or item.get('category') or 'document'))
            event_type = self._label_event_type(str(item.get('event_type') or item.get('source') or 'event'))
            published_at = str(item.get('published_at') or item.get('publish_time_utc') or item.get('date') or '')
            timeline.append(
                {
                    'source': source,
                    'event_type': event_type,
                    'published_at': published_at,
                    'title': item.get('title') or '',
                    'summary': item.get('summary') or '',
                    'url': item.get('url') or '',
                    'local_doc_dir': item.get('local_doc_dir') or '',
                }
            )
        return timeline

    def _sector_momentum_summary(self, analysis: AnalyzeTickerResponse) -> list[str]:
        momentum = dict(analysis.explanation.get('sector_momentum') or {})
        leader_name = str(momentum.get('leader_name') or momentum.get('leader_ticker') or '-')
        sector_name = str(momentum.get('sector') or '-')
        return [
            f'섹터 {sector_name}',
            f'대장주 {leader_name}',
            f'대장주 커플링 {float(analysis.features.sector_coupling_score):.2f}',
            f'섹터 자금 유입 강도 {float(analysis.features.sector_fund_flow_score):.2f}',
            f'섹터 breadth {float(analysis.features.sector_breadth_score):.2f}',
            f'대장주 대비 상대 강도 {float(analysis.features.sector_leader_relative_strength) * 100:.1f}%',
        ]

    def _sector_peer_snapshot(self, analysis: AnalyzeTickerResponse) -> list[dict[str, Any]]:
        momentum = dict(analysis.explanation.get('sector_momentum') or {})
        rows = list(momentum.get('peer_rows') or [])
        rows.sort(key=lambda item: ({'leader': 0, 'target': 1, 'peer': 2}.get(str(item.get('role') or 'peer'), 3), -float(item.get('return_20d') or 0.0)))
        return rows[:10]

    def _financial_summary(self, analysis: AnalyzeTickerResponse) -> list[str]:
        f = analysis.features
        return [
            f'매출 증가율 {f.revenue_growth_yoy * 100:.1f}%',
            f'영업이익률 {f.operating_margin * 100:.1f}%',
            f'순이익률 {f.net_margin * 100:.1f}%',
            f'부채비율 {f.debt_ratio:.2f}',
            f'유동비율 {f.current_ratio:.2f}',
            f'영업현금흐름 마진 {f.operating_cashflow_margin * 100:.1f}%',
        ]

    def _event_pattern_summary(self, analysis: AnalyzeTickerResponse) -> list[str]:
        event_pattern = dict(analysis.explanation.get('event_pattern') or {})
        if not event_pattern:
            return []
        event_type = self._label_event_type(str(event_pattern.get('current_event_type') or 'event'))
        sample_size = int(event_pattern.get('sample_size') or 0)
        avg_1d = float(event_pattern.get('avg_return_1d') or 0.0) * 100
        avg_5d = float(event_pattern.get('avg_return_5d') or 0.0) * 100
        confidence = float(event_pattern.get('pattern_confidence') or 0.0)
        lines = [
            f'현재 이벤트 유형 {event_type}',
            f'유사 이벤트 표본 {sample_size}건',
            f'유사 이벤트 후 평균 1일 반응 {avg_1d:.1f}%',
            f'유사 이벤트 후 평균 5일 반응 {avg_5d:.1f}%',
            f'패턴 신뢰도 {confidence:.2f}',
        ]
        if event_pattern.get('volatility_caution_mode'):
            lines.insert(0, '주요 이벤트 당일 또는 직후 구간으로 변동성 주의 모드가 적용되었습니다.')
        return lines[:6]

    def _sector_macro_theme(self, analysis: AnalyzeTickerResponse) -> str:
        sector = str((analysis.explanation.get('sector_momentum') or {}).get('sector') or '')
        export_sectors = {'반도체', '자동차', '조선', '철강', '2차전지·화학', '디스플레이·전자부품', '운송·물류'}
        rate_sectors = {'인터넷', '바이오', '헬스케어서비스', '게임·엔터', '화장품·생활소비재', '유통'}
        domestic_sectors = {'통신', '식음료', '유통', '게임·엔터', '화장품·생활소비재'}
        if sector in export_sectors:
            return 'export'
        if sector in rate_sectors:
            return 'rate_sensitive'
        if sector in domestic_sectors:
            return 'domestic_demand'
        return 'broad_market'
        return 'broad_market'

    def _macro_row_relevance(self, row: dict[str, Any], analysis: AnalyzeTickerResponse) -> tuple[float, str]:
        indicator = str(row.get('indicator_name') or '').upper()
        text = ' '.join([
            indicator,
            str(row.get('directional_interpretation') or ''),
            str(row.get('content_text') or ''),
        ]).upper()
        theme = self._sector_macro_theme(analysis)
        sector_name = str((analysis.explanation.get('sector_momentum') or {}).get('sector') or '')
        score = 0.0
        reason = '시장 전반'

        risk_tokens = ['VIX', 'RISK', 'EVENT_RISK', 'KOSPI', 'KOSDAQ', 'BROAD_ISSUE_STREAM_TONE']
        fx_tokens = ['KRW', 'USD', 'FX', 'EXPORT', 'TRADE', 'WORLD', 'GDP', 'INDUSTRIAL_PRODUCTION', 'INDPRO']
        rate_tokens = ['FED_FUNDS', 'BASE_RATE', '10Y', 'TREASURY', 'CPI', 'HICP', 'PCE', 'INFLATION', 'YIELD', 'RATE']
        semi_tokens = ['SEMICONDUCTOR', 'NASDAQ', 'CHIP']
        domestic_tokens = ['CPI', 'UNEMPLOYMENT', 'KOSPI', 'KOSDAQ', 'CONSUM', 'RETAIL']

        if any(token in text for token in risk_tokens):
            score += 0.75
            reason = '시장 위험선호/변동성'
        if theme == 'export' and any(token in text for token in fx_tokens):
            score += 1.0
            reason = '환율·수출·글로벌 수요'
        if theme == 'rate_sensitive' and any(token in text for token in rate_tokens):
            score += 1.0
            reason = '금리·인플레이션'
        if theme == 'domestic_demand' and any(token in text for token in domestic_tokens):
            score += 0.9
            reason = '내수·소비 심리'
        if sector_name == '반도체' and any(token in text for token in semi_tokens + fx_tokens):
            score += 0.95
            reason = '반도체 업황·미국 성장주 환경'
        if str(row.get('country') or '').upper() == 'KR':
            score += 0.15
        if float(row.get('surprise_confidence') or 0.0) <= 0.15:
            score -= 0.15
        return round(score, 3), reason

    def _format_macro_row(self, row: dict[str, Any], reason: str) -> str:
        indicator = str(row.get('indicator_name') or row.get('country') or '거시 지표')
        surprise = row.get('surprise_index')
        actual = row.get('actual')
        if surprise not in {None, ''}:
            return f'{indicator}: 서프라이즈 지수 {float(surprise):.2f} ({reason})'
        if actual not in {None, ''}:
            return f'{indicator}: 실제값 {actual} ({reason})'
        return f'{indicator}: {reason}'

    def _macro_summary(self, regime: MarketRegimeResponse, analysis: AnalyzeTickerResponse) -> list[str]:
        summary: list[str] = []
        overnight = dict(analysis.explanation.get('overnight_transmission') or {})
        if overnight.get('applied'):
            summary.append(
                f"장전 미국 지수 {overnight.get('reference_label') or overnight.get('reference_index')}: 전일 {float(overnight.get('latest_us_return') or 0.0) * 100:.1f}% 변동, 예상 갭 영향 {float(overnight.get('overnight_signal') or 0.0) * 100:.2f}%p"
            )

        ranked_rows: list[tuple[float, str, dict[str, Any]]] = []
        for row in regime.global_macro_pressure:
            candidate = dict(row)
            score, reason = self._macro_row_relevance(candidate, analysis)
            if score >= 0.85:
                ranked_rows.append((score, reason, candidate))
        ranked_rows.sort(key=lambda item: (-item[0], abs(float(item[2].get('surprise_index') or item[2].get('surprise_std') or 0.0))))
        for _, reason, row in ranked_rows[:3]:
            summary.append(self._format_macro_row(row, reason))

        if not summary and analysis.features.macro_pressure_score >= 0.4:
            summary.append(f'{regime.regime}: 현재는 종목 개별 재료보다 시장 변수 영향이 더 크게 작용하는 구간입니다.')
        return summary[:5]

    def _load_research_consensus(self, db: Session, analysis: AnalyzeTickerResponse) -> tuple[dict[str, Any], list[str], list[str], list[str], list[dict[str, Any]]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        stmt = (
            select(ExternalDocument)
            .where(ExternalDocument.source_system == 'PUBLIC_RESEARCH_REPORTS')
            .order_by(ExternalDocument.publish_time_utc.desc(), ExternalDocument.created_at_utc.desc())
            .limit(80)
        )
        rows = db.execute(stmt).scalars().all()
        sector_name = str((analysis.explanation.get('sector_momentum') or {}).get('sector') or '')
        matched: list[dict[str, Any]] = []
        for row in rows:
            row = self.research_repair.ensure_document_ready(db, row)
            current_at = row.publish_time_utc or row.created_at_utc
            if current_at and current_at.tzinfo is None:
                current_at = current_at.replace(tzinfo=timezone.utc)
            if current_at and current_at < cutoff:
                continue
            meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            if 'stock_decision' not in list(meta.get('service_targets') or ['stock_decision']):
                continue
            ticker_tags = {str(x) for x in list(meta.get('ticker_tags') or []) if x}
            company_tags = {str(x) for x in list(meta.get('company_tags') or []) if x}
            sector_tags = {str(x) for x in list(meta.get('sector_tags') or []) if x}
            ticker_match = analysis.ticker in ticker_tags
            company_match = analysis.instrument_name in company_tags
            sector_match = bool(sector_name) and sector_name in sector_tags
            if not (ticker_match or company_match or sector_match):
                continue
            scores = meta.get('research_scores') if isinstance(meta.get('research_scores'), dict) else {}
            weight = max(
                0.1,
                float(scores.get('freshness_score') or 0.4) * 0.40
                + float(scores.get('house_quality_score') or meta.get('house_quality_score') or 0.75) * 0.30
                + float(meta.get('feature_confidence') or 0.55) * 0.20
                + (0.10 if (ticker_match or company_match) else 0.05),
            )
            matched.append(
                {
                    'row': row,
                    'meta': meta,
                    'scores': scores,
                    'weight': round(weight, 3),
                    'ticker_match': ticker_match or company_match,
                    'sector_match': sector_match,
                }
            )

        if not matched:
            return ({
                'recommendation_score': 0.0,
                'dispersion_score': 0.0,
                'target_price_upside_pct': 0.0,
                'target_price_revision_score': 0.0,
                'industry_tailwind_score': 0.0,
                'industry_headwind_score': 0.0,
                'catalyst_near_term_score': 0.0,
                'thesis_positive_score': 0.0,
                'thesis_negative_score': 0.0,
                'matched_doc_count': 0,
            }, [], [], [], [])

        company_rows = [item for item in matched if item['ticker_match']]
        sector_rows = [item for item in matched if item['sector_match']]

        def _wavg(name: str, rows_to_use: list[dict[str, Any]]) -> float:
            if not rows_to_use:
                return 0.0
            total = sum(float(item['weight']) for item in rows_to_use) or 1.0
            return round(sum(float(item['scores'].get(name) or 0.0) * float(item['weight']) for item in rows_to_use) / total, 3)

        rec_samples = [float(item['scores'].get('company_recommendation_score') or 0.0) for item in company_rows]
        consensus = {
            'recommendation_score': _wavg('company_recommendation_score', company_rows or matched),
            'dispersion_score': round(pstdev(rec_samples), 3) if len(rec_samples) >= 2 else 0.0,
            'target_price_upside_pct': round(
                (
                    sum(float(item['meta'].get('price_upside_pct') or 0.0) * float(item['weight']) for item in company_rows if item['meta'].get('price_upside_pct') not in {None, ''})
                    / (sum(float(item['weight']) for item in company_rows if item['meta'].get('price_upside_pct') not in {None, ''}) or 1.0)
                ),
                2,
            ) if company_rows else 0.0,
            'target_price_revision_score': _wavg('target_price_revision_score', company_rows),
            'industry_tailwind_score': _wavg('industry_tailwind_score', sector_rows or matched),
            'industry_headwind_score': _wavg('industry_headwind_score', sector_rows or matched),
            'catalyst_near_term_score': _wavg('catalyst_near_term_score', matched),
            'thesis_positive_score': _wavg('thesis_positive_score', matched),
            'thesis_negative_score': _wavg('thesis_negative_score', matched),
            'matched_doc_count': len(matched),
        }
        bullish = []
        bearish = []
        checkpoints = []
        evidence_docs: list[dict[str, Any]] = []
        for item in sorted(matched, key=lambda row: (row['ticker_match'], row['weight']), reverse=True)[:6]:
            meta = item['meta']
            summary = item['row'].summary_json if isinstance(item['row'].summary_json, dict) else {}
            stance = str(meta.get('stance') or 'neutral')
            house = str(meta.get('house_name') or item['row'].source_id)
            snippet = str(summary.get('summary') or meta.get('evidence_snippet') or item['row'].title)
            if stance == 'positive' and snippet:
                bullish.append(f'{house}: {snippet[:90]}')
            elif stance == 'negative' and snippet:
                bearish.append(f'{house}: {snippet[:90]}')
            evidence_docs.append(
                {
                    'house_name': house,
                    'report_type': meta.get('report_type') or item['row'].category,
                    'stance': stance,
                    'title': item['row'].title,
                    'summary': snippet,
                    'published_at_utc': item['row'].publish_time_utc or item['row'].created_at_utc,
                    'url': item['row'].url,
                    'weight': item['weight'],
                }
            )
            for bullet in list(meta.get('catalyst_bullets') or [])[:1]:
                checkpoints.append(f'{house}: {bullet}')
        return consensus, bullish[:3], bearish[:3], checkpoints[:3], evidence_docs[:6]

    def _bullish_factors(self, analysis: AnalyzeTickerResponse) -> list[str]:
        positives = [reason.description for reason in analysis.signal.reasons if reason.score_contribution > 0]
        docs = [str(item.get('summary') or item.get('title') or '') for item in analysis.explanation.get('document_summaries', [])]
        merged = [item for item in positives + docs if item]
        return merged[:5]

    def _bearish_factors(self, analysis: AnalyzeTickerResponse) -> list[str]:
        negatives = [reason.description for reason in analysis.signal.reasons if reason.score_contribution < 0]
        negatives.extend(analysis.signal.risk_flags)
        return negatives[:5]

    def _change_triggers(self, analysis: AnalyzeTickerResponse) -> list[str]:
        f = analysis.features
        triggers = [
            '신규 공시 또는 정책 이벤트 발생',
            '거시 위험 점수 방향 전환',
            '거래대금 증가를 동반한 추세 돌파 여부',
        ]
        if f.rsi_14 >= 72:
            triggers.append('단기 과열 해소 여부 확인')
        if f.financing_risk_score >= 0.4:
            triggers.append('자금조달 리스크 완화 여부 확인')
        if has_risk_flag(analysis.signal, 'EVENT_DAY_VOLATILITY_MODE'):
            triggers.append('이벤트 당일 변동성 안정 여부와 장중 방향성 재확인')
        return triggers[:5]

    def _market_regime_snapshot_key(self, as_of_date: date) -> str:
        return as_of_date.isoformat()

    async def build_market_regime(self, as_of_date: date | None = None, db: Session | None = None) -> MarketRegimeResponse:
        target_date = as_of_date or date.today()
        snapshot_key = self._market_regime_snapshot_key(target_date)
        cache_key = f'market_regime:{snapshot_key}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return self._decorate_pipeline_status(
                cached,
                response_source='memory_cache',
                response_source_label='메모리 캐시',
                analysis_mode='quick',
                note='최근 계산된 시장 체제 결과를 메모리 캐시에서 반환했습니다.',
            )

        if db is not None:
            snapshot = self.snapshot_store.load_valid_snapshot(db, 'market_regime', snapshot_key)
            if snapshot is not None:
                response = MarketRegimeResponse(**snapshot['snapshot_json'])
                response = self._decorate_pipeline_status(
                    response,
                    **self._pipeline_status(
                        'batch_snapshot',
                        'batch_snapshot',
                        snapshot_ready=True,
                        snapshot_key=snapshot_key,
                        snapshot_generated_at_utc=snapshot.get('updated_at_utc'),
                        cache_expires_at_utc=snapshot.get('expires_at_utc'),
                        note='배치로 미리 계산한 시장 체제 스냅샷을 사용했습니다.',
                    ),
                )
                self._cache_set(cache_key, response)
                return response

        try:
            base = self.market.overview(target_date)
        except Exception:
            stale = self._cache_peek_stale(cache_key)
            if stale is not None:
                logger.exception('market regime build failed; serving stale cache')
                return self._decorate_pipeline_status(
                    stale,
                    response_source='stale_memory_cache',
                    response_source_label='이전 캐시 복구',
                    analysis_mode='quick',
                    note='실시간 계산에 실패해 이전 캐시를 반환했습니다.',
                )
            raise

        response = MarketRegimeResponse(
            as_of_date=base.as_of_date,
            generated_at_utc=base.generated_at_utc,
            regime=base.regime,
            regime_score=base.regime_score,
            market_one_line=base.market_one_line,
            global_macro_pressure=base.macro_summary,
            strong_sectors=base.strong_sectors,
            weak_sectors=base.weak_sectors,
            strategy_hints=base.strategy_hints,
            representative_symbols=base.representative_symbols,
            headline_news_briefs=base.headline_news_briefs,
            research_briefs=base.research_briefs,
            pipeline_status=self._pipeline_status(
                'live_collection',
                'quick',
                snapshot_ready=False,
                note='실시간 수집으로 시장 체제를 계산했습니다.',
            ),
        )
        self._cache_set(cache_key, response)
        return response

    def refresh_market_regime_snapshot(self, db: Session, as_of_date: date | None = None) -> MarketRegimeResponse:
        target_date = as_of_date or date.today()
        snapshot_key = self._market_regime_snapshot_key(target_date)
        base = self.market.overview(target_date)
        generated_at = datetime.now(timezone.utc)
        expires_at = generated_at + timedelta(seconds=self._snapshot_ttl_seconds)
        response = MarketRegimeResponse(
            as_of_date=base.as_of_date,
            generated_at_utc=generated_at,
            regime=base.regime,
            regime_score=base.regime_score,
            market_one_line=base.market_one_line,
            global_macro_pressure=base.macro_summary,
            strong_sectors=base.strong_sectors,
            weak_sectors=base.weak_sectors,
            strategy_hints=base.strategy_hints,
            representative_symbols=base.representative_symbols,
            headline_news_briefs=base.headline_news_briefs,
            research_briefs=base.research_briefs,
            pipeline_status=self._pipeline_status(
                'batch_snapshot',
                'batch_snapshot',
                snapshot_ready=True,
                snapshot_key=snapshot_key,
                snapshot_generated_at_utc=generated_at,
                cache_expires_at_utc=expires_at,
                note='시장 체제 스냅샷을 배치로 미리 생성했습니다.',
            ),
        )
        self.snapshot_store.save_snapshot(
            db,
            product_type='market_regime',
            snapshot_key=snapshot_key,
            as_of_date=target_date,
            snapshot_json=response.model_dump(mode='json'),
            meta_json={'regime': response.regime, 'regime_score': response.regime_score},
            expires_at_utc=expires_at,
        )
        db.commit()
        self._cache_set(f'market_regime:{snapshot_key}', response, ttl_seconds=self._snapshot_ttl_seconds)
        return response

    async def build_stock_decision(self, db: Session, ticker_or_name: str, as_of_date: date | None = None, lookback_days: int = 365) -> StockDecisionResponse:
        normalized = self._normalize_ticker_or_name(ticker_or_name)
        cache_key = f"stock_decision:{normalized}:{as_of_date.isoformat() if as_of_date else 'today'}:{lookback_days}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return self._decorate_pipeline_status(
                cached,
                response_source='memory_cache',
                response_source_label='메모리 캐시',
                analysis_mode='quick',
                note='최근 계산된 종목 판단 결과를 메모리 캐시에서 반환했습니다.',
            )

        analysis = await self.run_core_analysis(db, normalized, as_of_date, lookback_days, notify=False, force_send=False)
        regime = await self.build_market_regime(as_of_date, db=db)
        research_consensus, research_bulls, research_bears, research_checkpoints, research_evidence_docs = self._load_research_consensus(db, analysis)
        components = self._component_scores(analysis)
        horizons = self._horizon_scores(analysis, components)
        if int(research_consensus.get('matched_doc_count') or 0) > 0:
            research_company_component = self._clip(50 + float(research_consensus.get('recommendation_score') or 0.0) * 22 + float(research_consensus.get('target_price_upside_pct') or 0.0) * 0.35 + float(research_consensus.get('target_price_revision_score') or 0.0) * 15 + float(research_consensus.get('thesis_positive_score') or 0.0) * 18 - float(research_consensus.get('thesis_negative_score') or 0.0) * 16 - float(research_consensus.get('dispersion_score') or 0.0) * 12)
            research_industry_component = self._clip(50 + float(research_consensus.get('industry_tailwind_score') or 0.0) * 20 - float(research_consensus.get('industry_headwind_score') or 0.0) * 18 + float(research_consensus.get('catalyst_near_term_score') or 0.0) * 14)
            components['stock_specific_score'] = self._clip((components['stock_specific_score'] * 0.85) + (research_company_component * 0.15))
            components['sector_score'] = self._clip((components['sector_score'] * 0.85) + (research_industry_component * 0.15))
            horizons = {
                'short_term_score': self._clip(horizons['short_term_score'] * 0.90 + (50 + float(research_consensus.get('catalyst_near_term_score') or 0.0) * 35 - float(research_consensus.get('thesis_negative_score') or 0.0) * 20) * 0.10),
                'swing_score': self._clip(horizons['swing_score'] * 0.70 + research_company_component * 0.20 + research_industry_component * 0.10),
                'midterm_score': self._clip(horizons['midterm_score'] * 0.70 + research_company_component * 0.20 + research_industry_component * 0.10),
            }
        composite = mean([horizons['short_term_score'], horizons['swing_score'], horizons['midterm_score']])
        volatility_mode = has_risk_flag(analysis.signal, 'EVENT_DAY_VOLATILITY_MODE')
        conclusion = '관찰'
        if composite >= 70 and analysis.signal.quality_score >= 60:
            conclusion = '분할매수'
        elif composite >= 60:
            conclusion = '보유'
        elif composite < 45:
            conclusion = '비중축소'
        if volatility_mode and conclusion in {'분할매수', '보유'}:
            conclusion = '관찰'

        sector_momentum = dict(analysis.explanation.get('sector_momentum') or {})
        research_summary = []
        if int(research_consensus.get('matched_doc_count') or 0) > 0:
            research_summary = [
                f"최근 리서치 추천 점수 {float(research_consensus.get('recommendation_score') or 0.0):.2f}",
                f"평균 목표가 상승여력 {float(research_consensus.get('target_price_upside_pct') or 0.0):.1f}%",
                f"산업 tailwind 점수 {float(research_consensus.get('industry_tailwind_score') or 0.0):.2f}",
                f"가까운 촉매 점수 {float(research_consensus.get('catalyst_near_term_score') or 0.0):.2f}",
            ]
        response = StockDecisionResponse(
            ticker=analysis.ticker,
            instrument_name=analysis.instrument_name,
            as_of_date=analysis.as_of_date,
            generated_at_utc=datetime.now(timezone.utc),
            market_regime=regime.regime,
            conclusion=conclusion,
            state_label=self._state_label(analysis),
            confidence_score=round(composite, 2),
            quality_score=analysis.signal.quality_score,
            short_term_score=horizons['short_term_score'],
            swing_score=horizons['swing_score'],
            midterm_score=horizons['midterm_score'],
            market_score=components['market_score'],
            sector_score=components['sector_score'],
            stock_specific_score=components['stock_specific_score'],
            event_score=components['event_score'],
            valuation_score=components['valuation_score'],
            bullish_factors=(research_bulls + self._bullish_factors(analysis))[:5],
            bearish_factors=(research_bears + self._bearish_factors(analysis))[:5],
            change_triggers=(research_checkpoints + self._change_triggers(analysis))[:5],
            recent_timeline=self._timeline(analysis),
            sector_name=sector_momentum.get('sector'),
            sector_leader_ticker=sector_momentum.get('leader_ticker'),
            sector_leader_name=sector_momentum.get('leader_name'),
            sector_coupling_score=analysis.features.sector_coupling_score,
            sector_fund_flow_score=analysis.features.sector_fund_flow_score,
            sector_breadth_score=analysis.features.sector_breadth_score,
            sector_relative_strength=self._relative_strength(analysis),
            sector_momentum_summary=self._sector_momentum_summary(analysis),
            sector_peer_snapshot=self._sector_peer_snapshot(analysis),
            financial_summary=self._financial_summary(analysis),
            policy_macro_summary=self._macro_summary(regime, analysis) + self._event_pattern_summary(analysis),
            research_consensus=research_consensus,
            research_summary=research_summary,
            research_evidence_docs=research_evidence_docs,
            source_analysis=analysis,
            pipeline_status=self._pipeline_status(
                'live_collection',
                'quick',
                market_regime_source=regime.pipeline_status.get('response_source'),
                note='종목 판단은 빠른 분석 모드로 계산했습니다.',
            ),
        )
        self._cache_set(cache_key, response)
        return response

    async def build_action_plan(self, db: Session, req: ActionPlannerRequest) -> ActionPlannerResponse:
        decision = await self.build_stock_decision(db, req.ticker_or_name, req.as_of_date, req.lookback_days)
        f = decision.source_analysis.features
        base_score = {
            'short_term': decision.short_term_score,
            'swing': decision.swing_score,
            'midterm': decision.midterm_score,
        }[req.investment_horizon]
        validity_map = {
            'short_term': '1~3거래일',
            'swing': '1~3주',
            'midterm': '1~3개월',
        }
        if req.risk_profile == 'conservative':
            buy_pct, invalid_pct, target_pct = 0.04, 0.05, 0.08
        elif req.risk_profile == 'aggressive':
            buy_pct, invalid_pct, target_pct = 0.02, 0.07, 0.14
        else:
            buy_pct, invalid_pct, target_pct = 0.03, 0.06, 0.10

        volatility_mode = has_risk_flag(decision.source_analysis.signal, 'EVENT_DAY_VOLATILITY_MODE')
        if volatility_mode:
            action = '보유 지속' if req.has_position else '관찰 유지'
            action_reason = '주요 이벤트 전후 구간으로 일반 예측보다 변동성 관리가 우선입니다.'
        elif base_score >= 72 and decision.quality_score >= 65:
            action = '신규 진입' if not req.has_position else '보유 지속'
            action_reason = '추세, 수급, 이벤트, 품질 점수가 함께 우호적인 구간입니다.'
        elif base_score >= 60:
            action = '분할매수' if not req.has_position else '보유 지속'
            action_reason = '기본 시나리오는 양호하지만 추가 확인을 병행하는 편이 적절합니다.'
        elif base_score >= 45:
            action = '관찰 유지'
            action_reason = '즉시 실행보다 추세 확인과 재료 검증이 우선인 구간입니다.'
        else:
            action = '비중 축소' if req.has_position else '관찰 유지'
            action_reason = '공격적 진입보다 방어적 대응이 우선인 구간입니다.'

        close = max(f.close, 1.0)
        buy_zone = f'{close * (1 - buy_pct):.0f} ~ {close * (1 + buy_pct * 0.35):.0f}'
        invalidation_zone = f'{close * (1 - invalid_pct):.0f} 하회'
        target_zone = f'{close * (1 + target_pct):.0f} ~ {close * (1 + target_pct * 1.35):.0f}'
        preconditions = [
            '시장 체제가 추가로 악화되지 않는지 확인합니다.',
            '신규 악재 공시가 없는지 확인합니다.',
            '거래대금과 이벤트 관련도가 유지되는지 확인합니다.',
        ]
        if volatility_mode:
            preconditions.insert(0, '이벤트 결과 확정과 후속 변동성 안정 여부를 먼저 확인합니다.')
        scenarios = [
            ActionScenario(scenario='상방', trigger='주가가 MA20 위에서 유지되고 이벤트 후속 해석이 긍정적일 때', expected_path='상승 추세 지속', action='목표 구간까지 분할 대응'),
            ActionScenario(scenario='중립', trigger='주가가 MA20 부근에서 횡보할 때', expected_path='박스권 흐름', action='확인 신호 전까지 추가 진입을 자제'),
            ActionScenario(scenario='하방', trigger='무효화 구간 이탈 또는 악재 공시가 확인될 때', expected_path='추세 약화', action='비중 축소 또는 현금 비중 확대'),
        ]
        holding_plan = '보유 중이라면 무효화 구간 이탈 전까지는 보유를 유지하되, 이벤트 영향이 약해지면 일부 차익 실현을 검토합니다.'
        no_position_plan = '미보유자라면 추격 매수보다 매수 관심 구간 진입을 기다리는 편이 유리합니다.'
        return ActionPlannerResponse(
            ticker=decision.ticker,
            instrument_name=decision.instrument_name,
            as_of_date=decision.as_of_date,
            generated_at_utc=datetime.now(timezone.utc),
            recommended_action=action,
            action_reason=action_reason,
            investment_horizon=req.investment_horizon,
            risk_profile=req.risk_profile,
            objective=req.objective,
            has_position=req.has_position,
            avg_buy_price=req.avg_buy_price,
            action_score=round(base_score, 2),
            plan_validity_window=validity_map[req.investment_horizon],
            preconditions=preconditions,
            buy_interest_zone=buy_zone,
            invalidation_zone=invalidation_zone,
            target_zone=target_zone,
            holding_plan=holding_plan,
            no_position_plan=no_position_plan,
            scenarios=scenarios,
            source_decision=decision,
            pipeline_status=self._pipeline_status(
                'derived_from_stock_decision',
                'quick',
                source_decision_source=decision.pipeline_status.get('response_source'),
                note='행동 계획은 종목 판단 결과를 기반으로 재가공했습니다.',
            ),
        )

    async def build_watchlist_alert(self, db: Session, req: WatchlistAlertRequest) -> WatchlistAlertResponse:
        analysis = await self.run_core_analysis(db, req.ticker_or_name, req.as_of_date, req.lookback_days, notify=req.notify, force_send=req.force_send)
        f = analysis.features
        key_triggers = [
            '신규 공시 또는 정책 문서 발생',
            '점수 또는 품질 점수 급변',
            '목표 구간 진입 또는 무효화 구간 이탈',
        ]
        catalyst_watchlist = [
            '실적 발표 또는 가이던스 변경',
            '수주·공급 계약 공시',
            '자금조달 또는 규제 이벤트',
            '거시 체제 전환',
        ]
        should_alert_now = analysis.alert.should_send or analysis.signal.score >= 70 or len(analysis.signal.risk_flags) >= 3
        monitoring_state = '즉시 점검' if should_alert_now else '관찰 유지'
        preview = format_alert_message(analysis.ticker, analysis.instrument_name, analysis.features, analysis.signal, analysis.explanation)
        if f.financing_risk_score >= 0.4:
            key_triggers.append('자금조달 리스크 정상화 여부 확인')
        if f.macro_pressure_score >= 0.4:
            key_triggers.append('거시 압력 완화 여부 확인')
        return WatchlistAlertResponse(
            ticker=analysis.ticker,
            instrument_name=analysis.instrument_name,
            as_of_date=analysis.as_of_date,
            generated_at_utc=datetime.now(timezone.utc),
            should_alert_now=should_alert_now,
            monitoring_state=monitoring_state,
            key_triggers=key_triggers[:5],
            risk_flags=analysis.signal.risk_flags,
            catalyst_watchlist=catalyst_watchlist,
            alert_preview=preview,
            source_signal=analysis.signal,
            source_analysis=analysis,
            pipeline_status=self._pipeline_status(
                'live_check',
                'quick',
                notify=req.notify,
                force_send=req.force_send,
                note='관찰 알림은 현재 시점 데이터를 다시 점검해 생성했습니다.',
            ),
        )

    def _resolve_instrument(self, db: Session, ticker_or_name: str) -> Instrument:
        profile = self.pipeline.providers.resolve_instrument(ticker_or_name)
        stmt = select(Instrument).where(Instrument.ticker == profile.ticker)
        instrument = db.execute(stmt).scalar_one_or_none()
        if instrument:
            return instrument
        instrument = Instrument(ticker=profile.ticker, name_kr=profile.name_kr, market=profile.market, sector=profile.sector)
        db.add(instrument)
        db.flush()
        return instrument

    def add_watchlist_subscription(self, db: Session, req: WatchlistSubscriptionRequest) -> WatchlistSubscriptionResponse:
        instrument = self._resolve_instrument(db, req.ticker_or_name)
        stmt = select(WatchlistSubscription).where(
            WatchlistSubscription.instrument_id == instrument.id,
            WatchlistSubscription.channel == req.channel,
        )
        row = db.execute(stmt).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if row is None:
            row = WatchlistSubscription(
                instrument_id=instrument.id,
                channel=req.channel,
                is_active=True,
                notes=req.notes,
                updated_at_utc=now,
            )
            db.add(row)
        else:
            row.is_active = True
            row.notes = req.notes
            row.updated_at_utc = now
        db.commit()
        db.refresh(row)
        return WatchlistSubscriptionResponse(
            id=row.id,
            ticker=instrument.ticker,
            instrument_name=instrument.name_kr,
            channel=row.channel,
            is_active=row.is_active,
            notes=row.notes,
            created_at_utc=row.created_at_utc,
            updated_at_utc=row.updated_at_utc,
        )

    def list_watchlist_subscriptions(self, db: Session) -> list[WatchlistSubscriptionResponse]:
        stmt = (
            select(WatchlistSubscription, Instrument)
            .join(Instrument, Instrument.id == WatchlistSubscription.instrument_id)
            .where(WatchlistSubscription.is_active.is_(True))
            .order_by(WatchlistSubscription.created_at_utc.desc())
        )
        rows = db.execute(stmt).all()
        return [
            WatchlistSubscriptionResponse(
                id=sub.id,
                ticker=inst.ticker,
                instrument_name=inst.name_kr,
                channel=sub.channel,
                is_active=sub.is_active,
                notes=sub.notes,
                created_at_utc=sub.created_at_utc,
                updated_at_utc=sub.updated_at_utc,
            )
            for sub, inst in rows
        ]

    def delete_watchlist_subscription(self, db: Session, ticker_or_name: str, channel: str = 'telegram') -> WatchlistSubscriptionDeleteResponse:
        instrument = self._resolve_instrument(db, ticker_or_name)
        stmt = select(WatchlistSubscription).where(
            WatchlistSubscription.instrument_id == instrument.id,
            WatchlistSubscription.channel == channel,
            WatchlistSubscription.is_active.is_(True),
        )
        row = db.execute(stmt).scalar_one_or_none()
        if row is None:
            return WatchlistSubscriptionDeleteResponse(deleted=False, ticker=instrument.ticker, channel=channel)
        row.is_active = False
        row.updated_at_utc = datetime.now(timezone.utc)
        db.commit()
        return WatchlistSubscriptionDeleteResponse(deleted=True, ticker=instrument.ticker, channel=channel)

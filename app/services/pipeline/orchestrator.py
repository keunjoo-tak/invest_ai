from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AlertHistory, DisclosureParsed, Instrument, MacroSnapshot, NewsParsed, PriceDaily, SignalDecision
from app.schemas.analysis import AlertPayload, AnalyzeTickerRequest, AnalyzeTickerResponse
from app.services.alerts.dedup import build_reason_fingerprint, is_alert_blocked_by_cooldown
from app.services.alerts.formatter import format_alert_message
from app.services.alerts.telegram import TelegramNotifier
from app.services.features.feature_builder import build_features
from app.services.ingestion.providers import SourceProviderClient
from app.services.llm.gemini_client import GeminiClient
from app.services.quality.gates import passes_quality_gate
from app.services.signal.scorer import evaluate_signal


class AnalysisPipeline:
    def __init__(self) -> None:
        self.providers = SourceProviderClient()
        self.gemini = GeminiClient()
        self.telegram = TelegramNotifier()

    def _get_or_create_instrument(self, db: Session, ticker_or_name: str) -> Instrument:
        profile = self.providers.resolve_instrument(ticker_or_name)
        stmt = select(Instrument).where(Instrument.ticker == profile.ticker)
        instrument = db.execute(stmt).scalar_one_or_none()
        if instrument:
            return instrument
        instrument = Instrument(ticker=profile.ticker, name_kr=profile.name_kr, market=profile.market, sector=profile.sector)
        db.add(instrument)
        db.flush()
        return instrument

    def _persist_collected_data(
        self,
        db: Session,
        instrument: Instrument,
        prices: list[dict],
        news: list[dict],
        disclosures: list[dict],
        macro_rows: list[dict],
    ) -> None:
        existing_price_dates = {
            x[0]
            for x in db.execute(
                select(PriceDaily.trade_date).where(PriceDaily.instrument_id == instrument.id)
            ).all()
        }
        existing_urls = {
            x[0]
            for x in db.execute(select(NewsParsed.url).where(NewsParsed.instrument_id == instrument.id)).all()
        }
        existing_disclosure_ids = {
            x[0]
            for x in db.execute(
                select(DisclosureParsed.source_disclosure_id).where(DisclosureParsed.instrument_id == instrument.id)
            ).all()
        }

        for row in prices[-5:]:
            if row["trade_date"] in existing_price_dates:
                continue
            db.add(
                PriceDaily(
                    instrument_id=instrument.id,
                    trade_date=row["trade_date"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                )
            )
        for row in news[:5]:
            normalized_url = row["url"]
            if normalized_url in existing_urls:
                continue
            db.add(
                NewsParsed(
                    instrument_id=instrument.id,
                    title=row["title"],
                    url=normalized_url,
                    publish_time_utc=row["publish_time_utc"],
                    sentiment_score=row["sentiment_score"],
                    impact_scope=row["impact_scope"],
                    llm_payload={},
                )
            )
        for row in disclosures[:5]:
            source_disclosure_id = row["source_disclosure_id"]
            if source_disclosure_id in existing_disclosure_ids:
                continue
            db.add(
                DisclosureParsed(
                    instrument_id=instrument.id,
                    source_disclosure_id=source_disclosure_id,
                    title=row["title"],
                    event_type=row["event_type"],
                    publish_time_utc=row["publish_time_utc"],
                    impact_score=row["impact_score"],
                    llm_payload={},
                )
            )
        for row in macro_rows:
            db.add(
                MacroSnapshot(
                    as_of_date=row["as_of_date"],
                    country=row["country"],
                    indicator_name=row["indicator_name"],
                    actual=row["actual"],
                    consensus=row["consensus"],
                    surprise_std=row["surprise_std"],
                    directional_interpretation=row["directional_interpretation"],
                )
            )
        db.flush()

    async def run(self, db: Session, req: AnalyzeTickerRequest) -> AnalyzeTickerResponse:
        request_id = str(uuid.uuid4())
        as_of_date = req.as_of_date or date.today()
        instrument = self._get_or_create_instrument(db, req.ticker_or_name)

        prices = self.providers.fetch_price_daily(instrument.ticker, as_of_date, req.lookback_days)
        news = self.providers.fetch_news(instrument.ticker, as_of_date)
        disclosures = self.providers.fetch_disclosures(instrument.ticker, as_of_date)
        macro_rows = self.providers.fetch_macro(as_of_date)
        self._persist_collected_data(db, instrument, prices, news, disclosures, macro_rows)

        features = build_features(as_of_date, prices, news, disclosures, macro_rows)
        signal = evaluate_signal(features)
        pass_quality, quality_failures = passes_quality_gate(features, signal)
        if not pass_quality:
            signal.risk_flags.extend(quality_failures)

        explanation = self.gemini.explain_signal(
            ticker=instrument.ticker,
            signal=signal.model_dump(),
            features=features.model_dump(mode="json"),
        )

        db.add(
            SignalDecision(
                instrument_id=instrument.id,
                as_of_time_utc=datetime.now(timezone.utc),
                signal_type=signal.signal_type,
                direction=signal.direction,
                score=signal.score,
                quality_score=signal.quality_score,
                reasons_json={"reasons": [x.model_dump() for x in signal.reasons]},
                risk_flags_json={"flags": signal.risk_flags},
            )
        )
        db.flush()

        dedup_blocked = is_alert_blocked_by_cooldown(db, instrument, signal)
        should_send = req.notify and signal.score >= 60 and signal.quality_score >= 60 and (not dedup_blocked)
        message = format_alert_message(instrument.ticker, instrument.name_kr, features, signal, explanation)
        channel_results: dict[str, Any] = {}

        if should_send and "telegram" in req.channels:
            channel_results["telegram"] = await self.telegram.send(message)
            if channel_results["telegram"].get("status") in {"sent", "skipped"}:
                db.add(
                    AlertHistory(
                        instrument_id=instrument.id,
                        signal_direction=signal.direction,
                        reason_fingerprint=build_reason_fingerprint(signal),
                        channel="telegram",
                        payload_text=message,
                        status=channel_results["telegram"].get("status", "unknown"),
                    )
                )
        elif dedup_blocked:
            channel_results["telegram"] = {"status": "blocked", "reason": "cooldown_active"}
        else:
            channel_results["telegram"] = {"status": "skipped", "reason": "threshold_not_met_or_notify_false"}

        db.commit()
        return AnalyzeTickerResponse(
            request_id=request_id,
            ticker=instrument.ticker,
            instrument_name=instrument.name_kr,
            as_of_date=as_of_date,
            generated_at_utc=datetime.now(timezone.utc),
            features=features,
            signal=signal,
            explanation=explanation,
            alert=AlertPayload(
                should_send=should_send,
                dedup_blocked=dedup_blocked,
                channel_results=channel_results,
                message=message,
            ),
        )

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
from app.services.ingestion.raw_archive import RawArchiveManager
from app.services.llm.gemini_client import GeminiClient
from app.services.quality.gates import passes_quality_gate
from app.services.signal.scorer import evaluate_signal


class AnalysisPipeline:
    """동작 설명은 인수인계 문서를 참고하세요."""

    def __init__(self) -> None:
        """동작 설명은 인수인계 문서를 참고하세요."""
        self.providers = SourceProviderClient()
        self.gemini = GeminiClient()
        self.telegram = TelegramNotifier()
        self.archive = RawArchiveManager()

    def _localize_channel_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """채널 결과를 한글 중심 구조로 정규화한다."""
        status_code = str(result.get("status") or "unknown")
        reason_code = str(result.get("reason") or "")
        status_ko_map = {
            "sent": "발송됨",
            "skipped": "건너뜀",
            "blocked": "차단됨",
            "failed": "실패",
            "unknown": "알 수 없음",
        }
        reason_ko_map = {
            "threshold_not_met_or_notify_false": "알림 임계치 미충족 또는 notify=false 설정으로 발송하지 않았습니다.",
            "cooldown_active": "중복 방지 쿨다운이 적용되어 발송하지 않았습니다.",
            "telegram_disabled": "텔레그램 알림이 비활성화되어 있습니다.",
            "telegram_config_missing": "텔레그램 설정(토큰/채팅 ID)이 누락되었습니다.",
            "force_send_enabled": "force_send=true로 강제 발송이 적용되었습니다.",
        }
        out = dict(result)
        out["status_code"] = status_code
        out["status"] = status_ko_map.get(status_code, status_code)
        if reason_code:
            out["reason_code"] = reason_code
            out["reason"] = reason_ko_map.get(reason_code, reason_code)
        return out

    def _get_or_create_instrument(self, db: Session, ticker_or_name: str) -> Instrument:
        """동작 설명은 인수인계 문서를 참고하세요."""
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
        """동작 설명은 인수인계 문서를 참고하세요."""
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
                    llm_payload={
                        "content_excerpt": str(row.get("content_text") or "")[:1200],
                        "local_doc_dir": row.get("local_doc_dir", ""),
                        "summary": row.get("doc_summary", ""),
                    },
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
                    llm_payload={
                        "content_excerpt": str(row.get("content_text") or "")[:1200],
                        "local_doc_dir": row.get("local_doc_dir", ""),
                        "summary": row.get("doc_summary", ""),
                    },
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
        """동작 설명은 인수인계 문서를 참고하세요."""
        request_id = str(uuid.uuid4())
        as_of_date = req.as_of_date or date.today()
        instrument = self._get_or_create_instrument(db, req.ticker_or_name)
        call_dir = self.archive.create_call_dir(channel="analyze_ticker", request_id=request_id)

        prices = self.providers.fetch_price_daily(instrument.ticker, as_of_date, req.lookback_days)
        news = self.providers.fetch_news(instrument.ticker, as_of_date, include_content=True)
        disclosures = self.providers.fetch_disclosures(instrument.ticker, as_of_date, include_content=True)
        macro_rows = self.providers.fetch_macro(as_of_date)
        self.archive.save_json(
            call_dir,
            "snapshots/market_snapshot.json",
            {
                "request_id": request_id,
                "ticker": instrument.ticker,
                "as_of_date": str(as_of_date),
                "prices_count": len(prices),
                "news_count": len(news),
                "disclosures_count": len(disclosures),
                "macro_count": len(macro_rows),
            },
        )

        doc_inputs: list[dict[str, Any]] = []
        for idx, row in enumerate(news):
            saved = self.archive.save_document(
                root=call_dir,
                source="news",
                doc_id=f"news_{idx+1}",
                title=str(row.get("title") or f"news_{idx+1}"),
                url=str(row.get("url") or ""),
                content_text=str(row.get("content_text") or ""),
                metadata={
                    "publish_time_utc": str(row.get("publish_time_utc") or ""),
                    "sentiment_score": row.get("sentiment_score"),
                    "impact_scope": row.get("impact_scope"),
                },
                raw_bytes=row.get("raw_content") or b"",
                raw_ext=str(row.get("raw_ext") or ".html"),
            )
            row["local_doc_dir"] = saved["doc_dir"]
            doc_inputs.append(
                {
                    "source": "news",
                    "title": row.get("title", ""),
                    "content_text": row.get("content_text", ""),
                    "url": row.get("url", ""),
                }
            )

        for idx, row in enumerate(disclosures):
            saved = self.archive.save_document(
                root=call_dir,
                source="disclosures",
                doc_id=str(row.get("source_disclosure_id") or f"disc_{idx+1}"),
                title=str(row.get("title") or f"disclosure_{idx+1}"),
                url=str(row.get("url") or ""),
                content_text=str(row.get("content_text") or ""),
                metadata={
                    "publish_time_utc": str(row.get("publish_time_utc") or ""),
                    "event_type": row.get("event_type"),
                    "impact_score": row.get("impact_score"),
                },
                raw_bytes=row.get("raw_content") or b"",
                raw_ext=str(row.get("raw_ext") or ".html"),
            )
            row["local_doc_dir"] = saved["doc_dir"]
            doc_inputs.append(
                {
                    "source": "disclosure",
                    "title": row.get("title", ""),
                    "content_text": row.get("content_text", ""),
                    "url": row.get("url", ""),
                }
            )

        doc_summaries = self.gemini.summarize_documents(doc_inputs)
        for item in doc_summaries:
            title = str(item.get("title") or "")
            summary = str(item.get("summary") or "")
            for row in news:
                if str(row.get("title") or "") == title:
                    row["doc_summary"] = summary
            for row in disclosures:
                if str(row.get("title") or "") == title:
                    row["doc_summary"] = summary
        self.archive.save_json(
            call_dir,
            "snapshots/document_summaries.json",
            {"request_id": request_id, "items": doc_summaries},
        )
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
        explanation["document_summaries"] = doc_summaries[:8]
        explanation["archive_call_dir"] = str(call_dir)

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
        normal_should_send = req.notify and signal.score >= 60 and signal.quality_score >= 60 and (not dedup_blocked)
        force_should_send = bool(req.force_send and ("telegram" in req.channels))
        should_send = force_should_send or normal_should_send
        message = format_alert_message(instrument.ticker, instrument.name_kr, features, signal, explanation)
        channel_results: dict[str, Any] = {}

        if should_send and "telegram" in req.channels:
            channel_results["telegram"] = self._localize_channel_result(await self.telegram.send(message))
            if force_should_send:
                channel_results["telegram"]["force_send_applied"] = True
                if channel_results["telegram"].get("status_code") == "sent":
                    channel_results["telegram"]["reason_code"] = "force_send_enabled"
                    channel_results["telegram"]["reason"] = "force_send=true로 강제 발송이 적용되었습니다."
            if channel_results["telegram"].get("status_code") in {"sent", "skipped"}:
                db.add(
                    AlertHistory(
                        instrument_id=instrument.id,
                        signal_direction=signal.direction,
                        reason_fingerprint=build_reason_fingerprint(signal),
                        channel="telegram",
                        payload_text=message,
                        status=channel_results["telegram"].get("status_code", "unknown"),
                    )
                )
        elif dedup_blocked:
            channel_results["telegram"] = self._localize_channel_result(
                {"status": "blocked", "reason": "cooldown_active"}
            )
        else:
            channel_results["telegram"] = self._localize_channel_result(
                {"status": "skipped", "reason": "threshold_not_met_or_notify_false"}
            )

        response_language = req.response_language or "ko"
        if response_language == "ko":
            explanation = self.gemini.translate_json_to_korean(explanation)

        db.commit()
        return AnalyzeTickerResponse(
            request_id=request_id,
            ticker=instrument.ticker,
            instrument_name=instrument.name_kr,
            as_of_date=as_of_date,
            generated_at_utc=datetime.now(timezone.utc),
            response_language=response_language,
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

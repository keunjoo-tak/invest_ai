from __future__ import annotations

import asyncio
from typing import Any, Callable

from app.core.config import get_settings
from app.services.llm.gemini_client import GeminiClient


class GeminiTaskRunner:
    """Async wrapper for Gemini calls with timeout and concurrency control."""

    _semaphore: asyncio.Semaphore | None = None

    def __init__(self, gemini: GeminiClient) -> None:
        self.gemini = gemini
        self.settings = get_settings()
        if GeminiTaskRunner._semaphore is None:
            GeminiTaskRunner._semaphore = asyncio.Semaphore(max(1, self.settings.llm_task_concurrency))

    async def _run_with_timeout(self, label: str, fn: Callable[..., Any], *args: Any) -> dict[str, Any]:
        semaphore = GeminiTaskRunner._semaphore
        assert semaphore is not None
        if not self.settings.gemini_enabled:
            return {"status": "skipped", "reason": "gemini_disabled", "label": label, "result": None}
        try:
            async with semaphore:
                result = await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=float(self.settings.llm_task_timeout_seconds))
            return {"status": "completed", "reason": "ok", "label": label, "result": result}
        except asyncio.TimeoutError:
            return {"status": "timeout", "reason": "llm_timeout", "label": label, "result": None}
        except Exception as exc:
            return {"status": "failed", "reason": type(exc).__name__, "label": label, "result": None}

    async def run_document_stage(self, documents: list[dict[str, Any]]) -> dict[str, Any]:
        summaries_task = self._run_with_timeout("document_summaries", self.gemini.summarize_documents, documents)
        signals_task = self._run_with_timeout("prediction_signals", self.gemini.extract_prediction_signals, documents)
        summaries_result, signals_result = await asyncio.gather(summaries_task, signals_task)
        return {
            "summaries": summaries_result.get("result") or [],
            "signals": signals_result.get("result") or [],
            "meta": {
                "summaries": {k: v for k, v in summaries_result.items() if k != "result"},
                "signals": {k: v for k, v in signals_result.items() if k != "result"},
            },
        }

    async def run_explanation_stage(self, ticker: str, signal: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
        result = await self._run_with_timeout("signal_explanation", self.gemini.explain_signal, ticker, signal, features)
        return {"explanation": result.get("result") or self.gemini._fallback_explanation(signal), "meta": {k: v for k, v in result.items() if k != "result"}}

    async def run_translation_stage(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self._run_with_timeout("json_translation", self.gemini.translate_json_to_korean, payload)
        return {"payload": result.get("result") or payload, "meta": {k: v for k, v in result.items() if k != "result"}}

    async def run_disclosure_scoring_stage(self, disclosures: list[dict[str, Any]]) -> dict[str, Any]:
        result = await self._run_with_timeout("material_disclosure_scoring", self.gemini.score_material_disclosures, disclosures)
        fallback = self.gemini._fallback_material_disclosure_scores(disclosures) if result.get("result") is None else result.get("result")
        return {"scores": fallback or [], "meta": {k: v for k, v in result.items() if k != "result"}}

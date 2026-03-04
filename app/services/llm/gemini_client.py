from __future__ import annotations

import json
import os
from typing import Any

from app.core.config import get_settings


class GeminiClient:
    """Gemini 래퍼.

    신호 설명 생성과 JSON 기반 후처리 번역을 담당한다.
    """

    def __init__(self) -> None:
        """설정 로드."""
        self.settings = get_settings()

    def _fallback_explanation(self, signal: dict) -> dict[str, Any]:
        """Gemini 미사용/실패 시 사용할 기본 설명."""
        return {
            "summary_short": "규칙 기반 대체 설명이 적용되었습니다.",
            "bull_points": [str(r.get("description") or r.get("code") or "") for r in signal.get("reasons", [])[:3] if r],
            "bear_points": [],
            "risk_factors": signal.get("risk_flags", []),
            "check_before_order": ["유동성 점검", "장중 변동성 점검", "신규 공시 확인"],
            "confidence": 0.55,
        }

    def _generate_json(self, prompt: str, payload: dict[str, Any], temperature: float = 0.1) -> dict[str, Any]:
        """Gemini로 JSON 응답을 생성한다."""
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(self.settings.credentials_path())
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=self.settings.gemini_project_id,
            location=self.settings.gemini_location,
        )
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=f"{prompt}\nINPUT_JSON:\n{json.dumps(payload, ensure_ascii=False)}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=temperature,
            ),
        )
        text = getattr(response, "text", None) or "{}"
        return json.loads(text)

    def explain_signal(self, ticker: str, signal: dict, features: dict) -> dict[str, Any]:
        """신호 설명 JSON 생성."""
        if not self.settings.gemini_enabled:
            return self._fallback_explanation(signal)

        prompt = (
            "역할: 투자자용 신호 설명을 생성하라(매매 지시 금지).\n"
            "규칙: JSON 객체만 반환하고, 키 구조를 유지한다.\n"
            "필드: summary_short, bull_points, bear_points, risk_factors, check_before_order, confidence.\n"
            "언어: 한국어.\n"
        )
        payload = {"ticker": ticker, "signal": signal, "features": features}
        try:
            return self._generate_json(prompt=prompt, payload=payload, temperature=0.1)
        except Exception:
            return self._fallback_explanation(signal)

    def translate_json_to_korean(self, payload: dict[str, Any]) -> dict[str, Any]:
        """JSON 값을 한국어로 번역한다.

        키 이름/숫자/불리언/날짜 형태는 유지하고, 사람이 읽는 문자열 값만 한국어로 번역한다.
        """
        if not self.settings.gemini_enabled:
            return payload

        prompt = (
            "역할: 입력 JSON을 한국어로 번역하라.\n"
            "규칙:\n"
            "1) JSON 구조/키 이름/숫자/불리언/날짜/티커 코드는 변경하지 않는다.\n"
            "2) 사람이 읽는 영어 문자열 값만 자연스러운 한국어로 번역한다.\n"
            "3) JSON 객체만 반환한다.\n"
        )
        try:
            return self._generate_json(prompt=prompt, payload=payload, temperature=0.0)
        except Exception:
            return payload

    def summarize_documents(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """문서 리스트를 요약한다.

        입력: [{"source","title","content_text","url"}...]
        출력: [{"source","title","summary","key_points":[...],"risk_tags":[...]}...]
        """
        docs = [x for x in documents if (x.get("title") or x.get("content_text"))][:8]
        if not docs:
            return []
        if not self.settings.gemini_enabled:
            out: list[dict[str, Any]] = []
            for d in docs:
                text = str(d.get("content_text") or "")[:400]
                out.append(
                    {
                        "source": d.get("source", "unknown"),
                        "title": d.get("title", ""),
                        "summary": text or str(d.get("title") or ""),
                        "key_points": [str(d.get("title") or "")],
                        "risk_tags": [],
                    }
                )
            return out

        prompt = (
            "역할: 투자 인텔리전스 문서 요약기.\n"
            "규칙: 입력 문서 배열을 같은 길이의 JSON 배열로 요약하라.\n"
            "각 항목 필드: source, title, summary, key_points(3개 이내), risk_tags(문자열 배열).\n"
            "언어: 한국어. 과장/투자권유 표현 금지.\n"
        )
        try:
            res = self._generate_json(prompt=prompt, payload={"documents": docs}, temperature=0.1)
            items = res.get("documents") if isinstance(res, dict) else res
            return items if isinstance(items, list) else (res if isinstance(res, list) else [])
        except Exception:
            out = []
            for d in docs:
                out.append(
                    {
                        "source": d.get("source", "unknown"),
                        "title": d.get("title", ""),
                        "summary": str(d.get("content_text") or str(d.get("title") or ""))[:400],
                        "key_points": [str(d.get("title") or "")],
                        "risk_tags": [],
                    }
                )
            return out

from __future__ import annotations

import json
import os
from typing import Any

from app.core.config import get_settings


class GeminiClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _fallback_explanation(self, signal: dict) -> dict[str, Any]:
        return {
            "summary_short": "기본 규칙 엔진 기반 신호입니다. 세부 근거와 리스크를 확인하세요.",
            "bull_points": [r["code"] for r in signal.get("reasons", [])[:3]],
            "risk_factors": signal.get("risk_flags", []),
            "check_before_order": ["체결 유동성", "장중 변동성", "당일 공시 추가 여부"],
            "confidence": 0.55,
        }

    def explain_signal(self, ticker: str, signal: dict, features: dict) -> dict[str, Any]:
        if not self.settings.gemini_enabled:
            return self._fallback_explanation(signal)

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(self.settings.credentials_path())
        prompt = (
            "역할: 주식 자동주문이 아닌 반자동 알림 설명 엔진.\n"
            "규칙: JSON 객체만 응답. 확정 매수/매도 지시 금지. 입력 근거 밖의 정보 생성 금지.\n"
            "필드: summary_short, bull_points, bear_points, risk_factors, check_before_order, confidence.\n"
        )
        payload = {"ticker": ticker, "signal": signal, "features": features}

        try:
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
                    temperature=0.1,
                ),
            )
            text = getattr(response, "text", None) or "{}"
            return json.loads(text)
        except Exception:
            return self._fallback_explanation(signal)

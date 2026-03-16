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

    def extract_prediction_signals(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """문서에서 주가 예측용 구조화 신호를 추출한다.

        입력: [{"source","title","content_text","url"}...]
        출력: [{"title","primary_event","sentiment_bias","liquidity_hint","risk_hint","key_drivers":[...]}...]
        """
        docs = [x for x in documents if (x.get("title") or x.get("content_text"))][:8]
        if not docs:
            return []
        if not self.settings.gemini_enabled:
            out: list[dict[str, Any]] = []
            for d in docs:
                text = " ".join([str(d.get("title") or ""), str(d.get("content_text") or "")]).lower()
                primary_event = "general"
                if any(token in text for token in ["공급계약", "수주", "contract"]):
                    primary_event = "contract"
                elif any(token in text for token in ["실적", "영업이익", "earnings"]):
                    primary_event = "earnings"
                elif any(token in text for token in ["유상증자", "cb", "bw", "financing"]):
                    primary_event = "financing"
                out.append(
                    {
                        "title": d.get("title", ""),
                        "primary_event": primary_event,
                        "sentiment_bias": "positive" if "개선" in text or "growth" in text else "neutral",
                        "liquidity_hint": "normal",
                        "risk_hint": "financing" if primary_event == "financing" else "normal",
                        "key_drivers": [str(d.get("title") or "")],
                    }
                )
            return out

        prompt = (
            "역할: 투자 예측 feature 엔지니어.\n"
            "규칙:\n"
            "1) 각 문서를 주가 예측용 구조화 신호로 변환한다.\n"
            "2) title별로 1개 결과를 만든다.\n"
            "3) primary_event는 contract, earnings, financing, shareholder_return, governance, macro_policy, general 중 하나만 사용한다.\n"
            "4) sentiment_bias는 positive, neutral, negative 중 하나만 사용한다.\n"
            "5) liquidity_hint는 improve, normal, weaken 중 하나만 사용한다.\n"
            "6) risk_hint는 normal, financing, litigation, governance, macro, volatility 중 하나만 사용한다.\n"
            "7) JSON 배열만 반환한다.\n"
        )
        try:
            res = self._generate_json(prompt=prompt, payload={"documents": docs}, temperature=0.0)
            items = res.get("documents") if isinstance(res, dict) else res
            return items if isinstance(items, list) else (res if isinstance(res, list) else [])
        except Exception:
            return []

    def _fallback_material_disclosure_scores(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """LLM? ??? ? ?? ? ??? ?? ?? ??? ????."""
        docs = [x for x in documents if (x.get("title") or x.get("content_text"))][:6]
        out: list[dict[str, Any]] = []
        for doc in docs:
            text = " ".join([str(doc.get("title") or ""), str(doc.get("content_text") or "")]).lower()
            bullish = 0.15
            bearish = 0.10
            label = "general"
            rationale: list[str] = []
            if any(token in text for token in ["????", "??", "contract", "??", "????"]):
                bullish += 0.55
                label = "supply_contract"
                rationale.append("???? ?? ?? ??? ??? ???????.")
            if any(token in text for token in ["????", "cb", "bw", "????", "????????", "????", "financing"]):
                bearish += 0.65
                label = "financing"
                rationale.append("?? ?? ???? ?? ???? ?? ??? ???????.")
            if any(token in text for token in ["???", "??", "??", "????", "share buyback"]):
                bullish += 0.35
                label = "shareholder_return"
                rationale.append("???? ??? ??? ???????.")
            if any(token in text for token in ["??", "??", "??", "????", "????"]):
                bearish += 0.45
                label = "legal_or_distress"
                rationale.append("?? ?? ?? ???? ??? ???????.")
            severity = min(1.0, max(bullish, bearish) + (0.15 if "??" in text or "??" in text else 0.0))
            bullish = round(min(1.0, bullish), 3)
            bearish = round(min(1.0, bearish), 3)
            out.append(
                {
                    "title": str(doc.get("title") or ""),
                    "event_label": label,
                    "bullish_score": bullish,
                    "bearish_score": bearish,
                    "net_score": round(max(-1.0, min(1.0, bullish - bearish)), 3),
                    "event_severity": round(severity, 3),
                    "rationale": " ".join(rationale) or "?? ?? ?? ?? ?? ?????.",
                }
            )
        return out

    def score_material_disclosures(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """????? ??/?? ??? ?????."""
        docs = [x for x in documents if (x.get("title") or x.get("content_text"))][:6]
        if not docs:
            return []
        if not self.settings.gemini_enabled:
            return self._fallback_material_disclosure_scores(docs)

        prompt = (
            "??: ?? ??? ????? ?? ??? ?? ??? ????.\n"
            "??:\n"
            "1) ? ???? title, event_label, bullish_score, bearish_score, net_score, event_severity, rationale ??? ????.\n"
            "2) bullish_score? bearish_score? 0~1, net_score? -1~1, event_severity? 0~1 ??? ????.\n"
            "3) ?? ???, ?? ??, ????, ????????, ????? ?? ??? ???.\n"
            "4) ??? ????, ?? ??, ?? ??, ????? ?? ??? ???.\n"
            "5) JSON ??? ????.\n"
        )
        try:
            res = self._generate_json(prompt=prompt, payload={"documents": docs}, temperature=0.0)
            items = res.get("documents") if isinstance(res, dict) else res
            if isinstance(items, list):
                return items
            if isinstance(res, list):
                return res
        except Exception:
            pass
        return self._fallback_material_disclosure_scores(docs)

    def triage_market_documents(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """시장 영향 가능성이 있는 문서를 선별한다.

        입력: [{"source","title","content_text","url","category"}...]
        출력: [{"title","should_keep","relevance_score","impact_scope","policy_area","related_assets","reason"}...]
        """
        docs = [x for x in documents if (x.get("title") or x.get("content_text"))][:20]
        if not docs:
            return []
        if not self.settings.gemini_enabled:
            out: list[dict[str, Any]] = []
            keywords = ["금리", "통화정책", "물가", "환율", "수출", "반도체", "관세", "보조금", "규제", "예산", "지원"]
            for d in docs:
                text = " ".join([str(d.get("title") or ""), str(d.get("content_text") or "")]).lower()
                hits = sum(1 for token in keywords if token in text)
                out.append(
                    {
                        "title": d.get("title", ""),
                        "should_keep": hits > 0,
                        "relevance_score": min(1.0, 0.25 + hits * 0.12) if hits > 0 else 0.1,
                        "impact_scope": "macro" if any(token in text for token in ["금리", "물가", "환율", "예산"]) else "sector",
                        "policy_area": "macro_policy",
                        "related_assets": [],
                        "reason": "키워드 기반 휴리스틱 선별",
                    }
                )
            return out

        prompt = (
            "역할: 한국 정책/중앙은행 문서 중 주식시장 예측에 활용할 문서만 선별하는 애널리스트.\n"
            "규칙:\n"
            "1) 각 문서마다 should_keep, relevance_score, impact_scope, policy_area, related_assets, reason을 생성한다.\n"
            "2) should_keep은 주식시장, 금리, 환율, 경기, 수출, 산업정책, 규제, 세제, 보조금, 공급망, 특정 상장사/섹터에 유의미한 영향 가능성이 있을 때만 true로 한다.\n"
            "3) impact_scope는 macro, sector, single_stock, none 중 하나만 사용한다.\n"
            "4) policy_area는 monetary, fiscal, industry, trade, regulation, labor, housing, general 중 하나만 사용한다.\n"
            "5) related_assets는 종목명, 섹터명, 자산군을 짧은 문자열 배열로 넣는다.\n"
            "6) relevance_score는 0~1 사이 숫자다.\n"
            "7) JSON 배열만 반환한다.\n"
        )
        try:
            res = self._generate_json(prompt=prompt, payload={"documents": docs}, temperature=0.0)
            items = res.get("documents") if isinstance(res, dict) else res
            return items if isinstance(items, list) else (res if isinstance(res, list) else [])
        except Exception:
            return []

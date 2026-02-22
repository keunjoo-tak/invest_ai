from __future__ import annotations

import httpx

from app.core.config import get_settings


class TelegramNotifier:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def send(self, message: str) -> dict:
        if not self.settings.telegram_enabled:
            return {"status": "skipped", "reason": "telegram_disabled"}
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            return {"status": "failed", "reason": "telegram_config_missing"}

        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": self.settings.telegram_chat_id, "text": message}
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
        if resp.is_success:
            return {"status": "sent", "http_status": resp.status_code}
        return {"status": "failed", "http_status": resp.status_code, "body": resp.text[:400]}

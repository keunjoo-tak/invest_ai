from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

from app.services.alerts.telegram import TelegramNotifier


async def _run() -> int:
    """동작 설명은 인수인계 문서를 참고하세요."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"

    if not enabled:
        print("[INFO] TELEGRAM_ENABLED=false")
    if not token or not chat_id:
        print("[FAIL] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return 1

    notifier = TelegramNotifier()
    result = await notifier.send("[InvestAI] Telegram integration health check")
    print(result)
    return 0 if result.get("status") == "sent" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)


def main() -> int:
    """동작 설명은 인수인계 문서를 참고하세요."""
    url = os.getenv("DATABASE_URL", "postgresql+psycopg://investai:investai@localhost:5432/investai")
    try:
        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            value = conn.execute(text("select 1")).scalar_one()
        print(f"[OK] PostgreSQL connected: {value}")
        return 0
    except Exception as exc:
        msg = f"[FAIL] PostgreSQL connection failed: {type(exc).__name__}: {repr(exc)}"
        print(msg.encode("ascii", "backslashreplace").decode("ascii"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

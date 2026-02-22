from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha1

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AlertHistory, Instrument
from app.schemas.common import SignalResult


def build_reason_fingerprint(signal: SignalResult) -> str:
    raw = "|".join([signal.direction, signal.signal_type] + sorted([r.code for r in signal.reasons]))
    return sha1(raw.encode("utf-8")).hexdigest()[:24]


def is_alert_blocked_by_cooldown(db: Session, instrument: Instrument, signal: SignalResult) -> bool:
    settings = get_settings()
    fp = build_reason_fingerprint(signal)
    stmt = (
        select(AlertHistory)
        .where(AlertHistory.instrument_id == instrument.id)
        .where(AlertHistory.reason_fingerprint == fp)
        .order_by(desc(AlertHistory.sent_at_utc))
        .limit(1)
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.alert_cooldown_minutes)
    sent_at = row.sent_at_utc
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    return sent_at >= cutoff

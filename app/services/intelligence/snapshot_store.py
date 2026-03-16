from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProductSnapshotCache


class ProductSnapshotStore:
    """사용자 제품 스냅샷을 DB에 저장하고 조회한다."""

    def load_valid_snapshot(self, db: Session, product_type: str, snapshot_key: str) -> dict[str, Any] | None:
        row = db.execute(
            select(ProductSnapshotCache).where(
                ProductSnapshotCache.product_type == product_type,
                ProductSnapshotCache.snapshot_key == snapshot_key,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        now = datetime.now(timezone.utc)
        expires_at_utc = row.expires_at_utc
        if expires_at_utc is not None and expires_at_utc.tzinfo is None:
            expires_at_utc = expires_at_utc.replace(tzinfo=timezone.utc)
        if expires_at_utc is not None and expires_at_utc < now:
            return None
        return {
            'snapshot_json': dict(row.snapshot_json or {}),
            'meta_json': dict(row.meta_json or {}),
            'created_at_utc': row.created_at_utc,
            'updated_at_utc': row.updated_at_utc,
            'expires_at_utc': expires_at_utc,
            'as_of_date': row.as_of_date,
        }

    def save_snapshot(
        self,
        db: Session,
        *,
        product_type: str,
        snapshot_key: str,
        as_of_date,
        snapshot_json: dict[str, Any],
        meta_json: dict[str, Any],
        expires_at_utc: datetime | None,
    ) -> ProductSnapshotCache:
        row = db.execute(
            select(ProductSnapshotCache).where(
                ProductSnapshotCache.product_type == product_type,
                ProductSnapshotCache.snapshot_key == snapshot_key,
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if row is None:
            row = ProductSnapshotCache(
                product_type=product_type,
                snapshot_key=snapshot_key,
                as_of_date=as_of_date,
                snapshot_json=snapshot_json,
                meta_json=meta_json,
                expires_at_utc=expires_at_utc,
                updated_at_utc=now,
            )
            db.add(row)
        else:
            row.as_of_date = as_of_date
            row.snapshot_json = snapshot_json
            row.meta_json = meta_json
            row.expires_at_utc = expires_at_utc
            row.updated_at_utc = now
        db.flush()
        return row

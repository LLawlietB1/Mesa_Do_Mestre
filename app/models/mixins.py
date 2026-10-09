from datetime import datetime, timezone

from app.extensions import db


def utcnow() -> datetime:
    """Datas/horas são armazenadas em UTC (sem tzinfo) e convertidas para o fuso local na exibição."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

"""Runtime-editable settings persisted in the ``app_settings`` table."""

from sqlalchemy.orm import Session

from app.db.models import AppSetting

THRESHOLD_KEY = "confidence_threshold"


def get_threshold(session: Session, default: float) -> float:
    row = session.get(AppSetting, THRESHOLD_KEY)
    return float(row.value) if row is not None else default


def set_threshold(session: Session, value: float) -> None:
    row = session.get(AppSetting, THRESHOLD_KEY)
    if row is None:
        session.add(AppSetting(key=THRESHOLD_KEY, value=value))
    else:
        row.value = value

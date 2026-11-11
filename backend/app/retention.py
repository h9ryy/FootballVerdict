import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import INACTIVE_DELETE_DAYS, RETENTION_CHECK_SECONDS
from .db import SessionLocal
from .models import Prediction, Series, SeriesMatch, User

log = logging.getLogger("retention")


def delete_user_data(db: Session, user: User) -> None:
    """Полностью удалить игрока: серии, прогнозы и саму запись."""
    sids = [s.id for s in db.query(Series).filter_by(user_id=user.id).all()]
    if sids:
        db.query(SeriesMatch).filter(SeriesMatch.series_id.in_(sids)).delete(synchronize_session=False)
        db.query(Series).filter(Series.id.in_(sids)).delete(synchronize_session=False)
    db.query(Prediction).filter_by(user_id=user.id).delete()
    db.delete(user)
    db.commit()


def purge_inactive(db: Session, days: int = INACTIVE_DELETE_DAYS) -> int:
    """Удалить игроков, которые не заходили дольше срока хранения."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    last_activity = func.coalesce(User.last_seen_at, User.created_at)
    old = db.query(User).filter(last_activity < cutoff).all()
    for u in old:
        delete_user_data(db, u)
    return len(old)


async def retention_loop(every_seconds: int = RETENTION_CHECK_SECONDS):
    """Раз в сутки удаляет давно неактивные профили (первый раз сразу при запуске)."""
    while True:
        try:
            db = SessionLocal()
            try:
                n = purge_inactive(db)
            finally:
                db.close()
            print(f"[очистка] проверка неактивных профилей: удалено {n}", flush=True)
        except Exception:
            log.exception("Ошибка очистки неактивных профилей")
        await asyncio.sleep(every_seconds)
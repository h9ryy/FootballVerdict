import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

from .db import SessionLocal
from .models import Favorite, Match, Prediction, User

log = logging.getLogger("notify")

MSK = timezone(timedelta(hours=3))
SEND_FROM_HOUR, SEND_TO_HOUR = 10, 21      # пишем только днём и вечером по Москве
CHECK_EVERY = 15 * 60
NOT_PLAYABLE = ("CANCELLED", "POSTPONED", "SUSPENDED")
MAX_LINES = 8


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def pending_matches(db, user: User, now: datetime) -> list[Match]:
    """Сегодняшние (по МСК) ещё не начатые матчи избранных команд, на которые нет прогноза."""
    teams = [f.team for f in db.query(Favorite).filter_by(user_id=user.id).all()]
    if not teams:
        return []
    start = now.astimezone(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    rows = (db.query(Match)
            .filter(Match.kickoff_at > now, Match.kickoff_at < end,
                    Match.status.notin_(NOT_PLAYABLE),
                    (Match.home.in_(teams)) | (Match.away.in_(teams)))
            .order_by(Match.kickoff_at).all())
    if not rows:
        return []
    predicted = {p.match_id for p in db.query(Prediction).filter(
        Prediction.user_id == user.id, Prediction.match_id.in_([m.id for m in rows]))}
    return [m for m in rows if m.id not in predicted]


def digest_text(matches: list[Match], name) -> str:
    lines = ["⚽ Сегодня играют твои избранные команды:\n"]
    for m in matches[:MAX_LINES]:
        t = _aware(m.kickoff_at).astimezone(MSK).strftime("%H:%M")
        lines.append(f"{t} {name(m.home)} — {name(m.away)}")
    if len(matches) > MAX_LINES:
        lines.append(f"…и ещё {len(matches) - MAX_LINES}")
    lines.append("\nУспей сделать прогноз до начала матча (время МСК).")
    lines.append("Отключить напоминания: /notify")
    return "\n".join(lines)


async def notify_once(bot, kb, name, now: datetime | None = None) -> int:
    """Одна проверка: каждому подписанному игроку не больше одного сообщения в день."""
    now = now or datetime.now(timezone.utc)
    msk = now.astimezone(MSK)
    if not (SEND_FROM_HOUR <= msk.hour < SEND_TO_HOUR):
        return 0
    today = msk.date().isoformat()
    sent = 0
    db = SessionLocal()
    try:
        users = (db.query(User)
                 .filter(User.notify_enabled.is_(True), User.nickname.isnot(None),
                         (User.notify_last_day.is_(None)) | (User.notify_last_day != today))
                 .all())
        for u in users:
            matches = pending_matches(db, u, now)
            if not matches:
                continue
            try:
                await bot.send_message(u.telegram_id, digest_text(matches, name), reply_markup=kb())
                u.notify_last_day = today
                sent += 1
            except TelegramForbiddenError:
                u.notify_enabled = False          # бот заблокирован: больше не пишем
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)  # повторим на следующей проверке
            except TelegramAPIError as e:
                log.warning("Не удалось отправить напоминание %s: %s", u.id, e)
            db.commit()
            await asyncio.sleep(0.05)             # не превышаем лимиты Telegram
    finally:
        db.close()
    return sent


async def notify_loop(bot, kb, name):
    while True:
        try:
            n = await notify_once(bot, kb, name)
            if n:
                print(f"[напоминания] отправлено: {n}", flush=True)
        except Exception:
            log.exception("Ошибка рассылки напоминаний")
        await asyncio.sleep(CHECK_EVERY)
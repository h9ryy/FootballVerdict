import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from .config import FOOTBALL_DATA_TOKEN, LEAGUES
from .db import SessionLocal
from .models import Match
from .scoring import settle_match, settle_series

log = logging.getLogger("sync")

BASE = "https://api.football-data.org/v4"
FULL_EVERY = 6 * 3600   # полное обновление расписания: раз в 6 часов
LIVE_EVERY = 120        # пока идут матчи: раз в 2 минуты
IDLE_EVERY = 900        # когда матчей нет: раз в 15 минут
FINAL = ("FINISHED", "AWARDED")


def score_90(m: dict) -> tuple[int, int] | None:
    """Счёт за основное время (90 мин), без пенальти и допвремени."""
    score = m.get("score") or {}
    s = score.get("regularTime") or score.get("fullTime") or {}
    h, a = s.get("home"), s.get("away")
    if h is None or a is None:
        return None
    return int(h), int(a)


def outcome(m: dict) -> str | None:
    sc = score_90(m)
    if sc is None:
        return None
    h, a = sc
    return "H" if h > a else "A" if h < a else "D"


def apply_match(db, m: dict, code: str):
    """Создать или обновить матч по данным football-data.org."""
    home = (m.get("homeTeam") or {}).get("name")
    away = (m.get("awayTeam") or {}).get("name")
    if not home or not away or not m.get("utcDate"):
        return None  # пара ещё не известна (плей-офф)
    row = db.query(Match).filter_by(external_id=m["id"]).first()
    if not row:
        row = Match(external_id=m["id"], league=code)
        db.add(row)
    row.matchday = m.get("matchday")
    row.stage = m.get("stage")
    row.home, row.away = home, away
    row.kickoff_at = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
    row.status = m["status"]
    if m["status"] in FINAL and not row.settled:
        sc = score_90(m)
        if sc:
            row.home_goals, row.away_goals = sc
        row.result = outcome(m)
    elif m["status"] == "CANCELLED":
        row.settled = True   # отменён: очков нет, прогнозы не засчитываются
    elif row.settled and row.result is None:
        row.settled = False  # был отменён, но снова назначен
    return row


def settle_finished(db) -> int:
    """Начислить очки по завершённым матчам в порядке времени начала (важно для серий)."""
    rows = (db.query(Match)
            .filter(Match.result.isnot(None), Match.settled.is_(False))
            .order_by(Match.kickoff_at).all())
    for row in rows:
        settle_match(db, row)
    settle_series(db)
    return len(rows)


async def fetch(client: httpx.AsyncClient, path: str, params: dict | None = None):
    r = await client.get(BASE + path, params=params,
                         headers={"X-Auth-Token": FOOTBALL_DATA_TOKEN})
    if r.status_code == 429:
        log.warning("Лимит запросов football-data.org, пауза 60 секунд")
        await asyncio.sleep(60)
        return None
    r.raise_for_status()
    return r.json()


async def sync_full(client: httpx.AsyncClient):
    """Всё расписание сезона по каждой лиге (6 запросов с паузами)."""
    for code in LEAGUES:
        try:
            data = await fetch(client, f"/competitions/{code}/matches")
            if data:
                db = SessionLocal()
                try:
                    for m in data.get("matches", []):
                        apply_match(db, m, code)
                    db.commit()
                    settle_finished(db)
                finally:
                    db.close()
        except Exception as e:
            log.error("Полное обновление %s не удалось: %s", code, e)
        await asyncio.sleep(7)  # лимит бесплатного тарифа: 10 запросов в минуту


async def sync_live(client: httpx.AsyncClient):
    """Вчера, сегодня и завтра по всем лигам одним запросом."""
    today = datetime.now(timezone.utc).date()
    params = {
        "competitions": ",".join(LEAGUES),
        "dateFrom": (today - timedelta(days=1)).isoformat(),
        "dateTo": (today + timedelta(days=2)).isoformat(),  # конец диапазона не включается
    }
    data = await fetch(client, "/matches", params)
    if not data:
        return
    db = SessionLocal()
    try:
        for m in data.get("matches", []):
            code = (m.get("competition") or {}).get("code")
            if code in LEAGUES:
                apply_match(db, m, code)
        db.commit()
        settle_finished(db)
    finally:
        db.close()


def has_active_matches() -> bool:
    """Идут ли сейчас матчи или они вот-вот начнутся или недавно закончились."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        return db.query(Match).filter(
            Match.settled.is_(False),
            Match.kickoff_at >= now - timedelta(hours=4),
            Match.kickoff_at <= now + timedelta(minutes=15),
        ).first() is not None
    finally:
        db.close()


async def sync_loop():
    if not FOOTBALL_DATA_TOKEN:
        log.warning("FOOTBALL_DATA_TOKEN не задан: загрузка матчей выключена")
        return
    last_full = None
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                if last_full is None or time.monotonic() - last_full >= FULL_EVERY:
                    await sync_full(client)
                    last_full = time.monotonic()
                await sync_live(client)
            except Exception:
                log.exception("Ошибка обновления матчей")
            await asyncio.sleep(LIVE_EVERY if has_active_matches() else IDLE_EVERY)
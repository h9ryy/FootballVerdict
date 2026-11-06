import asyncio, logging
from datetime import datetime
import httpx
from .config import FOOTBALL_DATA_TOKEN, LEAGUES
from .db import SessionLocal
from .models import Match
from .scoring import settle_match

log = logging.getLogger("sync")
API = "https://api.football-data.org/v4/competitions/{code}/matches"


def outcome(m: dict) -> str | None:
    """Исход за основное время (90 мин), без пенальти и допвремени."""
    score = m.get("score", {})
    s = score.get("regularTime") or score.get("fullTime") or {}
    h, a = s.get("home"), s.get("away")
    if h is None or a is None:
        return None
    return "H" if h > a else "A" if h < a else "D"


async def sync_league(client: httpx.AsyncClient, code: str):
    r = await client.get(API.format(code=code), headers={"X-Auth-Token": FOOTBALL_DATA_TOKEN})
    r.raise_for_status()
    db = SessionLocal()
    try:
        for m in r.json().get("matches", []):
            if not m["homeTeam"].get("name") or not m["awayTeam"].get("name"):
                continue  # пары плей-офф ещё не известны
            row = db.query(Match).filter_by(external_id=m["id"]).first()
            if not row:
                row = Match(external_id=m["id"], league=code)
                db.add(row)
            row.matchday = m.get("matchday")
            row.stage = m.get("stage")
            row.home = m["homeTeam"]["name"]
            row.away = m["awayTeam"]["name"]
            row.kickoff_at = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
            row.status = m["status"]
            if m["status"] == "FINISHED":
                row.result = outcome(m)
            db.commit()
            if row.result and not row.settled:
                settle_match(db, row)
    finally:
        db.close()


async def sync_loop(every_seconds: int = 1800):
    if not FOOTBALL_DATA_TOKEN:
        log.warning("FOOTBALL_DATA_TOKEN не задан — синхронизация матчей выключена")
        return
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            for code in LEAGUES:
                try:
                    await sync_league(client, code)
                except Exception as e:  # одна лига не должна ронять весь цикл
                    log.error("sync %s failed: %s", code, e)
                await asyncio.sleep(7)  # лимит бесплатного тарифа: 10 запросов/мин
            await asyncio.sleep(every_seconds)
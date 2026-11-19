import asyncio
import gzip
import json
import logging
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url

from . import models  # noqa: F401  (чтобы все таблицы были известны)
from .config import BACKUP_CHAT_ID, BACKUP_KEEP, BOT_TOKEN, DATABASE_URL
from .db import Base, engine

log = logging.getLogger("backup")
MSK = timezone(timedelta(hours=3))
BACKUP_HOUR_MSK = 4   # во сколько делать ежедневную копию (по Москве)


def db_file() -> Path | None:
    """Путь к файлу базы, если это SQLite."""
    url = make_url(DATABASE_URL)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def make_backup(src: Path, out_dir: Path, keep: int = 7, stamp: str | None = None) -> Path:
    """Согласованная копия базы (штатным способом SQLite), сжатая gzip. Лишние старые удаляются."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tmp = out_dir / f"tmp-{stamp}.db"
    with closing(sqlite3.connect(src)) as a, closing(sqlite3.connect(tmp)) as b:
        a.backup(b)
    out = out_dir / f"football-{stamp}.db.gz"
    with open(tmp, "rb") as f, gzip.open(out, "wb") as g:
        shutil.copyfileobj(f, g)
    tmp.unlink()
    for old in sorted(out_dir.glob("football-*.db.gz"))[:-keep]:
        old.unlink()
    return out


def backup_dir() -> Path:
    """Куда класть копии при Postgres: в постоянную папку /data, если она есть."""
    data = Path("/data")
    return (data if data.exists() else Path(".")) / "backups"


def make_json_backup(out_dir: Path, keep: int = 7, stamp: str | None = None) -> Path:
    """Копия всех таблиц в gzip-JSON (для Postgres). Лишние старые удаляются."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"football-{stamp}.json.gz"
    data: dict[str, list] = {}
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            data[table.name] = [dict(r) for r in conn.execute(select(table)).mappings().all()]
    with gzip.open(out, "wt", encoding="utf-8") as g:
        json.dump(data, g, default=str, ensure_ascii=False)
    for old in sorted(out_dir.glob("football-*.json.gz"))[:-keep]:
        old.unlink()
    return out


async def send_backup(path: Path, caption: str) -> bool:
    """Отправить копию владельцу в личные сообщения (если задан BACKUP_CHAT_ID)."""
    if not (BACKUP_CHAT_ID and BOT_TOKEN):
        return False
    from aiogram import Bot
    from aiogram.types import FSInputFile
    bot = Bot(BOT_TOKEN)
    try:
        await bot.send_document(BACKUP_CHAT_ID, FSInputFile(path), caption=caption)
        return True
    except Exception:
        log.exception("Не удалось отправить копию базы в Telegram")
        return False
    finally:
        await bot.session.close()


async def run_backup(send: bool = True):
    """Сделать копию сейчас. Возвращает (путь или None, отправлена ли в Telegram)."""
    src = db_file()
    if src is not None:
        if not src.exists():
            return None, False
        out = await asyncio.to_thread(make_backup, src, src.parent / "backups", BACKUP_KEEP)
    else:
        out = await asyncio.to_thread(make_json_backup, backup_dir(), BACKUP_KEEP)
    sent = await send_backup(out, f"Копия базы: {out.name}") if send else False
    return out, sent


def seconds_to_next(now: datetime | None = None) -> float:
    now = (now or datetime.now(timezone.utc)).astimezone(MSK)
    nxt = now.replace(hour=BACKUP_HOUR_MSK, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


async def backup_loop():
    while True:
        await asyncio.sleep(seconds_to_next())
        try:
            out, sent = await run_backup()
            print(f"[бэкап] {out.name if out else 'файл базы не найден'}, "
                  f"в Telegram: {'да' if sent else 'нет'}", flush=True)
        except Exception:
            log.exception("Ошибка резервного копирования")
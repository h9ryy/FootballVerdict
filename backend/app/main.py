import asyncio, re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from .config import LEAGUES, APP_NAME
from .db import Base, engine, get_db
from .models import User, Match, Prediction
from .auth import current_user
from .sync import sync_loop
from .bot import run_bot

NICK_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_]{3,16}$")
BANNED_PARTS: list[str] = []  # сюда добавим запрещённые слова для ников


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)          # создать таблицы, если их нет
    sync_task = asyncio.create_task(sync_loop())   # загрузка матчей в фоне
    bot_task = asyncio.create_task(run_bot())      # бот в фоне
    yield
    sync_task.cancel()
    bot_task.cancel()

app = FastAPI(title=APP_NAME, lifespan=lifespan, docs_url=None, redoc_url=None)


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def me_dict(u: User) -> dict:
    wr = round(u.correct / u.total * 100) if u.total else 0
    return {"nickname": u.nickname, "adult": bool(u.adult_confirmed_at), "points": u.points,
            "total": u.total, "correct": u.correct, "winrate": wr,
            "streak": u.streak, "best_streak": u.best_streak}


@app.get("/api/config")
def config():
    return {"app_name": APP_NAME}


@app.get("/api/me")
def me(u: User = Depends(current_user)):
    return me_dict(u)


class NickIn(BaseModel):
    nickname: str
    adult: bool


@app.put("/api/me/nickname")
def set_nick(body: NickIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    nick = body.nickname.strip()
    if not NICK_RE.match(nick):
        raise HTTPException(400, "Ник: 3–16 символов, буквы, цифры и _")
    if any(w in nick.lower() for w in BANNED_PARTS):
        raise HTTPException(400, "Этот ник недоступен")
    if not body.adult:
        raise HTTPException(400, "Сервис только для совершеннолетних (18+)")
    taken = db.query(User).filter(User.nickname_lower == nick.lower(), User.id != u.id).first()
    if taken:
        raise HTTPException(409, "Ник уже занят")
    u.nickname, u.nickname_lower = nick, nick.lower()
    u.adult_confirmed_at = u.adult_confirmed_at or datetime.now(timezone.utc)
    db.commit()
    return me_dict(u)


@app.delete("/api/me")
def delete_me(u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Право на удаление: стираем аккаунт и все его прогнозы."""
    db.query(Prediction).filter_by(user_id=u.id).delete()
    db.delete(u)
    db.commit()
    return {"ok": True}


@app.get("/api/leagues")
def leagues(db: Session = Depends(get_db), u: User = Depends(current_user)):
    now = datetime.now(timezone.utc)
    out = []
    for code, name in LEAGUES.items():
        open_n = db.query(Match).filter(Match.league == code, Match.kickoff_at > now).count()
        out.append({"code": code, "name": name, "open": open_n})
    return out


@app.get("/api/leagues/{code}/matches")
def league_matches(code: str, matchday: int | None = None,
                   db: Session = Depends(get_db), u: User = Depends(current_user)):
    if code not in LEAGUES:
        raise HTTPException(404)
    if matchday is None:  # ближайший не завершённый тур
        matchday = db.query(func.min(Match.matchday)).filter(
            Match.league == code, Match.status != "FINISHED").scalar()
        if matchday is None:
            matchday = db.query(func.max(Match.matchday)).filter(Match.league == code).scalar()
    q = (db.query(Match).filter(Match.league == code, Match.matchday == matchday)
         .order_by(Match.kickoff_at))
    picks = {p.match_id: p.pick for p in db.query(Prediction).filter_by(user_id=u.id).all()}
    now = datetime.now(timezone.utc)
    return {"matchday": matchday, "matches": [
        {"id": m.id, "home": m.home, "away": m.away, "kickoff": aware(m.kickoff_at).isoformat(),
         "locked": aware(m.kickoff_at) <= now, "result": m.result, "pick": picks.get(m.id)}
        for m in q]}


class PickIn(BaseModel):
    match_id: int
    pick: str


@app.post("/api/predictions")
def predict(body: PickIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not u.nickname:
        raise HTTPException(403, "Сначала выберите ник")
    if body.pick not in ("H", "D", "A"):
        raise HTTPException(400, "Неверный выбор")
    m = db.get(Match, body.match_id)
    if not m:
        raise HTTPException(404)
    if aware(m.kickoff_at) <= datetime.now(timezone.utc):
        raise HTTPException(409, "Матч уже начался")
    p = db.query(Prediction).filter_by(user_id=u.id, match_id=m.id).first()
    if p:
        p.pick = body.pick
    else:
        db.add(Prediction(user_id=u.id, match_id=m.id, pick=body.pick))
    db.commit()
    return {"ok": True}


@app.get("/api/me/predictions")
def my_predictions(u: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = (db.query(Prediction, Match).join(Match).filter(Prediction.user_id == u.id)
            .order_by(Match.kickoff_at.desc()).limit(50).all())
    return [{"home": m.home, "away": m.away, "pick": p.pick, "result": m.result,
             "points": p.points_awarded} for p, m in rows]


@app.get("/api/leaderboard")
def leaderboard(min_games: int = 20, db: Session = Depends(get_db), u: User = Depends(current_user)):
    """Только игроки с минимумом прогнозов, иначе лидер — «1 из 1»."""
    rows = (db.query(User).filter(User.nickname.isnot(None), User.total >= max(min_games, 0))
            .order_by(User.points.desc()).limit(50).all())
    return [{"nickname": r.nickname, "points": r.points,
             "winrate": round(r.correct / r.total * 100) if r.total else 0} for r in rows]


# фронтенд отдаётся этим же сервером (должен быть В КОНЦЕ файла)
FRONT = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=FRONT, html=True), name="front")
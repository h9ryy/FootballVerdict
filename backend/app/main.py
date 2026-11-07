import asyncio, re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import LEAGUES, APP_NAME
from .db import Base, engine, get_db
from .models import User, Match, Prediction, Series, SeriesMatch
from .auth import current_user
from .sync import sync_loop
from .bot import run_bot
from .scoring import (EXACT_BONUS, SERIES_BONUS, SERIES_MAX, SERIES_MIN, SERIES_WINDOW_HOURS)

NICK_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_]{3,16}$")
BANNED_PARTS: list[str] = []  # сюда добавим запрещённые слова для ников


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)               # создать таблицы, если их нет
    sync_task = asyncio.create_task(sync_loop())   # загрузка матчей в фоне
    bot_task = asyncio.create_task(run_bot())      # бот в фоне
    yield
    sync_task.cancel()
    bot_task.cancel()


app = FastAPI(title=APP_NAME, lifespan=lifespan, docs_url=None, redoc_url=None)


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


LOCKED_STATUSES = {"IN_PLAY", "PAUSED", "FINISHED", "AWARDED", "CANCELLED", "SUSPENDED"}


def is_locked(m: Match) -> bool:
    """Приём прогнозов закрыт: матч начался, идёт, завершён или отменён."""
    return aware(m.kickoff_at) <= datetime.now(timezone.utc) or m.status in LOCKED_STATUSES


def outcome_of(h: int, a: int) -> str:
    return "H" if h > a else "A" if h < a else "D"


def series_match_ids(db: Session, user_id: int) -> set[int]:
    """Матчи в открытых сериях игрока: прогнозы на них менять нельзя."""
    rows = (db.query(SeriesMatch.match_id)
            .join(Series, Series.id == SeriesMatch.series_id)
            .filter(Series.user_id == user_id, Series.status == "open").all())
    return {r[0] for r in rows}


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
    """Право на удаление: стираем аккаунт, прогнозы и серии."""
    sids = [s.id for s in db.query(Series).filter_by(user_id=u.id).all()]
    if sids:
        db.query(SeriesMatch).filter(SeriesMatch.series_id.in_(sids)).delete(synchronize_session=False)
        db.query(Series).filter(Series.id.in_(sids)).delete(synchronize_session=False)
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
    preds = {p.match_id: p for p in db.query(Prediction).filter_by(user_id=u.id).all()}
    in_series = series_match_ids(db, u.id)
    return {"matchday": matchday, "exact_bonus": EXACT_BONUS, "matches": [
        {"id": m.id, "home": m.home, "away": m.away, "kickoff": aware(m.kickoff_at).isoformat(),
         "locked": is_locked(m), "status": m.status, "result": m.result,
         "home_goals": m.home_goals, "away_goals": m.away_goals,
         "pick": preds[m.id].pick if m.id in preds else None,
         "my_home": preds[m.id].pred_home if m.id in preds else None,
         "my_away": preds[m.id].pred_away if m.id in preds else None,
         "in_series": m.id in in_series}
        for m in q]}


class PickIn(BaseModel):
    match_id: int
    pick: str | None = None      # H / D / A
    home: int | None = None      # точный счёт (по желанию), тогда исход берётся из счёта
    away: int | None = None
    clear_score: bool = False    # убрать точный счёт, оставив исход


@app.post("/api/predictions")
def predict(body: PickIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not u.nickname:
        raise HTTPException(403, "Сначала выберите ник")
    m = db.get(Match, body.match_id)
    if not m:
        raise HTTPException(404)
    if is_locked(m):
        raise HTTPException(409, "Приём прогнозов на этот матч закрыт")
    if m.id in series_match_ids(db, u.id):
        raise HTTPException(409, "Матч входит в серию дня: прогноз менять нельзя")
    p = db.query(Prediction).filter_by(user_id=u.id, match_id=m.id).first()

    if body.home is not None or body.away is not None:
        if (body.home is None or body.away is None
                or not (0 <= body.home <= 9 and 0 <= body.away <= 9)):
            raise HTTPException(400, "Счёт: два числа от 0 до 9")
        pick, home, away = outcome_of(body.home, body.away), body.home, body.away
    else:
        if body.pick not in ("H", "D", "A"):
            raise HTTPException(400, "Неверный выбор")
        pick, home, away = body.pick, None, None
        # счёт сохраняем, если он не противоречит новому исходу
        if (not body.clear_score and p and p.pred_home is not None
                and outcome_of(p.pred_home, p.pred_away) == pick):
            home, away = p.pred_home, p.pred_away

    if p:
        p.pick, p.pred_home, p.pred_away = pick, home, away
    else:
        db.add(Prediction(user_id=u.id, match_id=m.id, pick=pick, pred_home=home, pred_away=away))
    db.commit()
    return {"ok": True, "pick": pick, "home": home, "away": away}


@app.get("/api/me/predictions")
def my_predictions(u: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = (db.query(Prediction, Match).join(Match).filter(Prediction.user_id == u.id)
            .order_by(Match.kickoff_at.desc()).limit(50).all())
    return [{"home": m.home, "away": m.away, "pick": p.pick, "result": m.result,
             "points": p.points_awarded} for p, m in rows]


def series_dict(s: Series, picks: dict) -> dict:
    return {"id": s.id, "status": s.status, "bonus": s.bonus_awarded,
            "potential": SERIES_BONUS.get(len(s.items), 0), "day": s.day,
            "matches": [{"home": it.match.home, "away": it.match.away,
                         "kickoff": aware(it.match.kickoff_at).isoformat(),
                         "pick": picks.get(it.match_id), "result": it.match.result,
                         "status": it.match.status} for it in s.items]}


@app.get("/api/series")
def get_series(db: Session = Depends(get_db), u: User = Depends(current_user)):
    now = datetime.now(timezone.utc)
    picks = {p.match_id: p.pick for p in db.query(Prediction).filter_by(user_id=u.id).all()}
    rows = db.query(Series).filter_by(user_id=u.id).order_by(Series.id.desc()).limit(10).all()
    can_create = not any(s.day == now.date().isoformat() for s in rows)
    candidates = []
    if can_create:
        busy = series_match_ids(db, u.id)
        upcoming = (db.query(Match)
                    .filter(Match.kickoff_at > now,
                            Match.kickoff_at <= now + timedelta(hours=SERIES_WINDOW_HOURS))
                    .order_by(Match.kickoff_at).all())
        candidates = [{"id": m.id, "home": m.home, "away": m.away,
                       "kickoff": aware(m.kickoff_at).isoformat(), "pick": picks[m.id]}
                      for m in upcoming if m.id in picks and m.id not in busy and not is_locked(m)]
    return {"series": [series_dict(s, picks) for s in rows], "can_create": can_create,
            "candidates": candidates, "bonus": {str(k): v for k, v in SERIES_BONUS.items()},
            "min": SERIES_MIN, "max": SERIES_MAX}


class SeriesIn(BaseModel):
    match_ids: list[int]


@app.post("/api/series")
def create_series(body: SeriesIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not u.nickname:
        raise HTTPException(403, "Сначала выберите ник")
    ids = list(dict.fromkeys(body.match_ids))
    if not (SERIES_MIN <= len(ids) <= SERIES_MAX):
        raise HTTPException(400, f"Выбери от {SERIES_MIN} до {SERIES_MAX} матчей")
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    if db.query(Series).filter_by(user_id=u.id, day=today).first():
        raise HTTPException(409, "Сегодня серия уже собрана")
    matches = db.query(Match).filter(Match.id.in_(ids)).all()
    if len(matches) != len(ids):
        raise HTTPException(404, "Матч не найден")
    busy = series_match_ids(db, u.id)
    predicted = {p.match_id for p in db.query(Prediction).filter(
        Prediction.user_id == u.id, Prediction.match_id.in_(ids))}
    for m in matches:
        if is_locked(m):
            raise HTTPException(409, "Один из матчей уже начался")
        if aware(m.kickoff_at) > now + timedelta(hours=SERIES_WINDOW_HOURS):
            raise HTTPException(400, f"В серию можно взять матчи ближайших {SERIES_WINDOW_HOURS} часов")
        if m.id not in predicted:
            raise HTTPException(400, "Сначала сделай прогноз на каждый матч серии")
        if m.id in busy:
            raise HTTPException(409, "Один из матчей уже в другой серии")
    s = Series(user_id=u.id, day=today)
    db.add(s)
    db.flush()
    for m in matches:
        db.add(SeriesMatch(series_id=s.id, match_id=m.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Сегодня серия уже собрана")
    return {"ok": True}


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
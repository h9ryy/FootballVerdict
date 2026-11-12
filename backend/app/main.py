import asyncio, re
from .config import LEAGUES, APP_NAME, LEADERBOARD_MIN_GAMES
from .auth import current_user, identity
from .retention import delete_user_data, retention_loop
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from .models import User, Match, Prediction, Series, SeriesMatch, Favorite
from .sync import sync_loop
from .bot import run_bot
from .scoring import (EXACT_BONUS, SERIES_BONUS, SERIES_MAX, SERIES_MIN, SERIES_WINDOW_HOURS)

NICK_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_]{3,16}$")
BANNED_PARTS: list[str] = []  # сюда добавим запрещённые слова для ников


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)                       # создать таблицы, если их нет
    sync_task = asyncio.create_task(sync_loop())           # загрузка матчей в фоне
    bot_task = asyncio.create_task(run_bot())              # бот в фоне
    retention_task = asyncio.create_task(retention_loop()) # удаление давно неактивных профилей
    yield
    sync_task.cancel()
    bot_task.cancel()
    retention_task.cancel()

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
def me(tg_id: int = Depends(identity), db: Session = Depends(get_db)):
    """Профиль. Пока человек не принял условия, запись о нём НЕ создаётся."""
    u = db.query(User).filter_by(telegram_id=tg_id).first()
    if not u:
        return {"registered": False}
    return {"registered": True, **me_dict(u)}


class RegisterIn(BaseModel):
    nickname: str
    adult: bool


@app.post("/api/register")
def register(body: RegisterIn, tg_id: int = Depends(identity), db: Session = Depends(get_db)):
    """Первый вход: подтверждение 18+ и ник. Запись о человеке создаётся только после этого."""
    if not body.adult:
        raise HTTPException(400, "Сервис только для совершеннолетних (18+)")
    nick = body.nickname.strip()
    if not NICK_RE.match(nick):
        raise HTTPException(400, "Ник: 3–16 символов, буквы, цифры и _")
    if any(w in nick.lower() for w in BANNED_PARTS):
        raise HTTPException(400, "Этот ник недоступен")
    if db.query(User).filter_by(telegram_id=tg_id).first():
        raise HTTPException(409, "Ты уже зарегистрирован")
    if db.query(User).filter(User.nickname_lower == nick.lower()).first():
        raise HTTPException(409, "Ник уже занят")
    now = datetime.now(timezone.utc)
    u = User(telegram_id=tg_id, nickname=nick, nickname_lower=nick.lower(),
             adult_confirmed_at=now, last_seen_at=now)
    db.add(u)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ник уже занят")
    return {"registered": True, **me_dict(u)}


@app.delete("/api/me")
def delete_me(u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Право на удаление: стираем аккаунт, прогнозы и серии."""
    delete_user_data(db, u)
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

@app.delete("/api/predictions/{match_id}")
def cancel_prediction(match_id: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    """Отменить свой прогноз (пока матч не начался и не лежит в серии дня)."""
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(404)
    if is_locked(m):
        raise HTTPException(409, "Приём прогнозов на этот матч закрыт")
    if m.id in series_match_ids(db, u.id):
        raise HTTPException(409, "Матч входит в серию дня: прогноз менять нельзя")
    db.query(Prediction).filter_by(user_id=u.id, match_id=m.id).delete()
    db.commit()
    return {"ok": True}


@app.get("/api/me/predictions")
def my_predictions(offset: int = 0, db: Session = Depends(get_db), u: User = Depends(current_user)):
    """Лента прогнозов: ждущие матча (на первой странице) и сыгранные (порциями по 30)."""
    in_series = series_match_ids(db, u.id)

    def item(p: Prediction, m: Match) -> dict:
        return {"match_id": m.id, "league": LEAGUES.get(m.league, m.league),
                "home": m.home, "away": m.away, "kickoff": aware(m.kickoff_at).isoformat(),
                "status": m.status, "result": m.result, "locked": is_locked(m),
                "pick": p.pick, "my_home": p.pred_home, "my_away": p.pred_away,
                "home_goals": m.home_goals, "away_goals": m.away_goals,
                "points": p.points_awarded, "in_series": m.id in in_series}

    base = db.query(Prediction, Match).join(Match).filter(Prediction.user_id == u.id)
    pending = []
    if offset == 0:
        pending = [item(p, m) for p, m in base.filter(Match.settled.is_(False))
                   .order_by(Match.kickoff_at.asc()).limit(50).all()]
    rows = (base.filter(Match.settled.is_(True)).order_by(Match.kickoff_at.desc())
            .offset(max(offset, 0)).limit(31).all())
    return {"pending": pending, "done": [item(p, m) for p, m in rows[:30]],
        "has_more": len(rows) > 30, "exact_bonus": EXACT_BONUS}


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
def leaderboard(db: Session = Depends(get_db), u: User = Depends(current_user)):
    """Рейтинг за всё время. В него попадают игроки с минимумом прогнозов с итогом."""
    def wr(r: User) -> int:
        return round(r.correct / r.total * 100) if r.total else 0

    players = (db.query(User)
               .filter(User.nickname.isnot(None), User.total >= LEADERBOARD_MIN_GAMES).all())
    # при равных очках выше тот, у кого больше процент угаданных; затем по id
    players.sort(key=lambda r: (-r.points, -(r.correct / r.total if r.total else 0), r.id))
    rows = [{"place": i + 1, "nickname": r.nickname, "points": r.points,
             "winrate": wr(r), "me": r.id == u.id} for i, r in enumerate(players[:50])]
    place = next((i + 1 for i, r in enumerate(players) if r.id == u.id), None)
    return {"min_games": LEADERBOARD_MIN_GAMES, "rows": rows,
            "me": {"place": place, "points": u.points, "winrate": wr(u), "total": u.total}}


MAX_FAVORITES = 30


def match_dict(m: Match, preds: dict, in_series: set) -> dict:
    p = preds.get(m.id)
    return {"id": m.id, "home": m.home, "away": m.away, "kickoff": aware(m.kickoff_at).isoformat(),
            "league": LEAGUES.get(m.league, m.league),
            "locked": is_locked(m), "status": m.status, "result": m.result,
            "home_goals": m.home_goals, "away_goals": m.away_goals,
            "pick": p.pick if p else None,
            "my_home": p.pred_home if p else None,
            "my_away": p.pred_away if p else None,
            "in_series": m.id in in_series}


@app.get("/api/teams")
def teams(db: Session = Depends(get_db), u: User = Depends(current_user)):
    """Все команды из загруженных матчей: для выбора избранных."""
    favs = {f.team for f in db.query(Favorite).filter_by(user_id=u.id).all()}
    found: dict[str, str] = {}
    for col in (Match.home, Match.away):
        for name, league in db.query(col, Match.league).distinct():
            if name not in found or found[name] == "CL":   # приоритет: национальная лига
                found[name] = league
    order = list(LEAGUES)
    out = [{"name": n, "league": LEAGUES.get(l, l), "fav": n in favs}
           for n, l in sorted(found.items(), key=lambda kv: (order.index(kv[1]) if kv[1] in order else 99, kv[0]))]
    return out


class FavIn(BaseModel):
    team: str


@app.post("/api/favorites")
def add_favorite(body: FavIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    team = body.team.strip()
    if not db.query(Match.id).filter((Match.home == team) | (Match.away == team)).first():
        raise HTTPException(404, "Команда не найдена")
    if db.query(Favorite).filter_by(user_id=u.id, team=team).first():
        return {"ok": True}
    if db.query(Favorite).filter_by(user_id=u.id).count() >= MAX_FAVORITES:
        raise HTTPException(409, f"Можно добавить не больше {MAX_FAVORITES} команд")
    db.add(Favorite(user_id=u.id, team=team))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"ok": True}


@app.delete("/api/favorites")
def remove_favorite(team: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(Favorite).filter_by(user_id=u.id, team=team).delete()
    db.commit()
    return {"ok": True}


@app.get("/api/favorites/matches")
def favorite_matches(db: Session = Depends(get_db), u: User = Depends(current_user)):
    """Ближайшие матчи избранных команд."""
    teams_ = [f.team for f in db.query(Favorite).filter_by(user_id=u.id).all()]
    if not teams_:
        return {"teams": [], "matches": [], "exact_bonus": EXACT_BONUS}
    now = datetime.now(timezone.utc)
    rows = (db.query(Match)
            .filter(Match.kickoff_at > now, (Match.home.in_(teams_)) | (Match.away.in_(teams_)))
            .order_by(Match.kickoff_at).limit(40).all())
    preds = {p.match_id: p for p in db.query(Prediction).filter_by(user_id=u.id).all()}
    in_series = series_match_ids(db, u.id)
    return {"teams": teams_, "exact_bonus": EXACT_BONUS,
            "matches": [match_dict(m, preds, in_series) for m in rows]}

# фронтенд отдаётся этим же сервером (должен быть В КОНЦЕ файла)
FRONT = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=FRONT, html=True), name="front")
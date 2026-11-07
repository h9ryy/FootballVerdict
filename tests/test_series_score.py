from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.models import User, Match, Prediction, Series, SeriesMatch
from backend.app.scoring import settle_match, settle_series


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def make_user(db, tg=1):
    u = User(telegram_id=tg, nickname=f"user{tg}", nickname_lower=f"user{tg}")
    db.add(u)
    db.commit()
    return u


def make_match(db, n, result="H", goals=None, status="FINISHED"):
    m = Match(external_id=n, league="PL", matchday=1, home="A", away="B",
              kickoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=n),
              status=status, result=result)
    if goals:
        m.home_goals, m.away_goals = goals
    db.add(m)
    db.commit()
    return m


def bet(db, u, m, pick, score=None):
    p = Prediction(user_id=u.id, match_id=m.id, pick=pick)
    if score:
        p.pred_home, p.pred_away = score
    db.add(p)
    db.commit()


def make_series(db, u, matches):
    s = Series(user_id=u.id, day="2026-01-01")
    db.add(s)
    db.flush()
    for m in matches:
        db.add(SeriesMatch(series_id=s.id, match_id=m.id))
    db.commit()
    return s


def matches_with_picks(db, u, count=3, results=None, picks=None):
    results = results or ["H"] * count
    picks = picks or ["H"] * count
    out = []
    for n in range(1, count + 1):
        m = make_match(db, n, results[n - 1])
        bet(db, u, m, picks[n - 1])
        out.append(m)
    return out


# ---------- точный счёт ----------

def test_exact_score_bonus(db):
    u = make_user(db)
    m = make_match(db, 1, "H", goals=(2, 1))
    bet(db, u, m, "H", score=(2, 1))
    settle_match(db, m)
    assert u.points == 25            # 10 + 15


def test_right_outcome_wrong_score(db):
    u = make_user(db)
    m = make_match(db, 1, "H", goals=(2, 1))
    bet(db, u, m, "H", score=(1, 0))
    settle_match(db, m)
    assert u.points == 10


def test_exact_score_zero_zero(db):
    u = make_user(db)
    m = make_match(db, 1, "D", goals=(0, 0))
    bet(db, u, m, "D", score=(0, 0))
    settle_match(db, m)
    assert u.points == 28            # 10 + 3 за ничью + 15


def test_no_bonus_without_goals_in_match(db):
    u = make_user(db)
    m = make_match(db, 1, "H")       # счёт матча неизвестен
    bet(db, u, m, "H", score=(2, 1))
    settle_match(db, m)
    assert u.points == 10


# ---------- серия дня ----------

def test_series_won(db):
    u = make_user(db)
    ms = matches_with_picks(db, u)
    s = make_series(db, u, ms)
    for m in ms:
        settle_match(db, m)
    settle_series(db)
    assert s.status == "won" and s.bonus_awarded == 20
    assert u.points == 10 + 10 + 15 + 20      # на третьем матче ещё +5 за стрик


def test_series_five_matches_bonus(db):
    u = make_user(db)
    ms = matches_with_picks(db, u, count=5)
    s = make_series(db, u, ms)
    for m in ms:
        settle_match(db, m)
    settle_series(db)
    assert s.status == "won" and s.bonus_awarded == 60


def test_series_lost_keeps_normal_points(db):
    u = make_user(db)
    ms = matches_with_picks(db, u, picks=["H", "A", "H"])
    s = make_series(db, u, ms)
    for m in ms:
        settle_match(db, m)
    settle_series(db)
    assert s.status == "lost" and s.bonus_awarded == 0
    assert u.points == 20                     # 10 + 0 + 10


def test_series_waits_for_all_matches(db):
    u = make_user(db)
    ms = matches_with_picks(db, u)
    for m in ms:                                   # матчи «только что» состоялись
        m.kickoff_at = datetime.now(timezone.utc)
    db.commit()
    s = make_series(db, u, ms)
    settle_match(db, ms[0])
    settle_match(db, ms[1])
    settle_series(db)
    assert s.status == "open"


def test_series_void_when_match_never_played(db):
    u = make_user(db)
    ms = matches_with_picks(db, u)     # даты в прошлом: третий матч так и не сыгран
    s = make_series(db, u, ms)
    settle_match(db, ms[0])
    settle_match(db, ms[1])
    settle_series(db)
    assert s.status == "void"


def test_series_void_when_match_cancelled(db):
    u = make_user(db)
    ms = matches_with_picks(db, u)
    ms[2].status, ms[2].result, ms[2].settled = "CANCELLED", None, True
    db.commit()
    s = make_series(db, u, ms)
    settle_series(db)
    assert s.status == "void" and u.points == 0
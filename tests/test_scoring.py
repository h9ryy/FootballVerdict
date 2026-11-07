from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.models import User, Match, Prediction
from backend.app.scoring import settle_match
from backend.app.sync import outcome


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


def make_match(db, n, result="H"):
    m = Match(external_id=n, league="PL", matchday=1, home="A", away="B",
              kickoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=n),
              status="FINISHED", result=result)
    db.add(m)
    db.commit()
    return m


def bet(db, u, m, pick):
    db.add(Prediction(user_id=u.id, match_id=m.id, pick=pick))
    db.commit()


def test_correct_gets_10_wrong_gets_0(db):
    u = make_user(db)
    m1, m2 = make_match(db, 1, "H"), make_match(db, 2, "A")
    bet(db, u, m1, "H")
    bet(db, u, m2, "H")
    settle_match(db, m1)
    assert u.points == 10
    settle_match(db, m2)
    assert u.points == 10 and u.total == 2 and u.correct == 1 and u.streak == 0


def test_streak_bonuses(db):
    u = make_user(db)
    for n in range(1, 6):
        m = make_match(db, n)
        bet(db, u, m, "H")
        settle_match(db, m)
    # 10 + 10 + (10+5) + 10 + (10+10)
    assert u.points == 65
    assert u.streak == 5 and u.best_streak == 5


def test_wrong_pick_resets_streak(db):
    u = make_user(db)
    for n in (1, 2):
        m = make_match(db, n)
        bet(db, u, m, "H")
        settle_match(db, m)
    m3 = make_match(db, 3, "A")
    bet(db, u, m3, "H")
    settle_match(db, m3)
    assert u.streak == 0 and u.best_streak == 2


def test_no_double_settle(db):
    u = make_user(db)
    m = make_match(db, 1)
    bet(db, u, m, "H")
    settle_match(db, m)
    settle_match(db, m)
    assert u.points == 10 and u.total == 1


def test_match_without_result_not_settled(db):
    u = make_user(db)
    m = make_match(db, 1, result=None)
    bet(db, u, m, "H")
    settle_match(db, m)
    assert u.points == 0 and m.settled is False


def test_outcome_uses_90_minutes():
    # после допвремени и пенальти: за 90 минут была ничья
    m = {"score": {"regularTime": {"home": 1, "away": 1}, "fullTime": {"home": 3, "away": 2}}}
    assert outcome(m) == "D"
    assert outcome({"score": {"fullTime": {"home": 2, "away": 0}}}) == "H"
    assert outcome({"score": {"fullTime": {"home": None, "away": None}}}) is None
    
def crowd(db, result, picks):
    """picks: выборы игроков, например ['A', 'H', 'H']. Возвращает матч и игроков."""
    m = make_match(db, 1, result)
    users = []
    for i, pick in enumerate(picks, start=1):
        u = make_user(db, tg=i)
        bet(db, u, m, pick)
        users.append(u)
    return m, users


def test_draw_bonus(db):
    u = make_user(db)
    m = make_match(db, 1, "D")
    bet(db, u, m, "D")
    settle_match(db, m)
    assert u.points == 13


def test_rare_bonus_top_tier(db):
    m, users = crowd(db, "A", ["A"] + ["H"] * 9)   # за A выбрал 1 из 10 = 10%
    settle_match(db, m)
    assert users[0].points == 20
    assert users[1].points == 0


def test_rare_bonus_middle_tier(db):
    m, users = crowd(db, "A", ["A"] * 2 + ["H"] * 8)   # 20%
    settle_match(db, m)
    assert users[0].points == 16


def test_rare_bonus_low_tier_boundary(db):
    m, users = crowd(db, "A", ["A"] * 3 + ["H"] * 7)   # ровно 30%: уже следующая ступень
    settle_match(db, m)
    assert users[0].points == 13


def test_popular_pick_no_bonus(db):
    m, users = crowd(db, "H", ["H"] * 6 + ["A"] * 4)   # 60%
    settle_match(db, m)
    assert users[0].points == 10


def test_rare_bonus_needs_enough_votes(db):
    m, users = crowd(db, "A", ["A"] + ["H"] * 4)   # всего 5 прогнозов
    settle_match(db, m)
    assert users[0].points == 10


def test_rare_draw_stacks(db):
    m, users = crowd(db, "D", ["D"] + ["H"] * 9)   # 10 + 3 за ничью + 10 за редкость
    settle_match(db, m)
    assert users[0].points == 23
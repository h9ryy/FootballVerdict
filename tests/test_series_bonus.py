from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.models import Match, Series, SeriesMatch, User
from backend.app.scoring import series_bonuses


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def won_series(db, leagues, bonus, days_ago=1):
    u = User(telegram_id=1, nickname="u1", nickname_lower="u1")
    db.add(u)
    db.commit()
    s = Series(user_id=u.id, day="2026-01-01", status="won", bonus_awarded=bonus)
    db.add(s)
    db.flush()
    for i, lg in enumerate(leagues):
        m = Match(external_id=i + 1, league=lg, home="A", away="B", status="FINISHED", result="H", settled=True,
                  kickoff_at=datetime.now(timezone.utc) - timedelta(days=days_ago))
        db.add(m)
        db.flush()
        db.add(SeriesMatch(series_id=s.id, match_id=m.id))
    db.commit()
    return u


def test_all_leagues_gets_full_bonus(db):
    u = won_series(db, ["PL", "PL", "PD", "PD"], 35)
    assert series_bonuses(db) == {u.id: 35}


def test_league_gets_share(db):
    u = won_series(db, ["PL", "PL", "PD", "PD"], 35)
    assert series_bonuses(db, league="PL") == {u.id: 17}
    assert series_bonuses(db, league="PD") == {u.id: 17}


def test_uneven_split_and_foreign_league(db):
    u = won_series(db, ["PL", "PL", "PL", "PD"], 35)
    assert series_bonuses(db, league="PL") == {u.id: 26}
    assert series_bonuses(db, league="PD") == {u.id: 8}
    assert series_bonuses(db, league="SA") == {}


def test_period_filter(db):
    won_series(db, ["PL", "PL", "PL"], 20, days_ago=10)
    since_week = datetime.now(timezone.utc) - timedelta(days=7)
    since_month = datetime.now(timezone.utc) - timedelta(days=30)
    assert series_bonuses(db, since_week) == {}
    assert len(series_bonuses(db, since_month)) == 1
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.models import User, Match, Prediction, Series, SeriesMatch
from backend.app.retention import delete_user_data, purge_inactive


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def days_ago(n):
    return datetime.now(timezone.utc) - timedelta(days=n)


def make_user(db, tg, last_seen=None, created=None):
    u = User(telegram_id=tg, nickname=f"user{tg}", nickname_lower=f"user{tg}", last_seen_at=last_seen)
    if created:
        u.created_at = created
    db.add(u)
    db.commit()
    return u


def add_data(db, u):
    m = Match(external_id=u.telegram_id, league="PL", home="A", away="B",
              kickoff_at=datetime.now(timezone.utc) + timedelta(hours=5))
    db.add(m)
    db.commit()
    db.add(Prediction(user_id=u.id, match_id=m.id, pick="H"))
    s = Series(user_id=u.id, day="2026-01-01")
    db.add(s)
    db.flush()
    db.add(SeriesMatch(series_id=s.id, match_id=m.id))
    db.commit()


def test_purge_removes_inactive_user_with_all_data(db):
    old = make_user(db, 1, last_seen=days_ago(400))
    fresh = make_user(db, 2, last_seen=days_ago(10))
    add_data(db, old)
    add_data(db, fresh)
    old_id = old.id

    assert purge_inactive(db, days=365) == 1

    assert db.query(User).filter_by(telegram_id=1).first() is None
    assert db.query(Prediction).filter_by(user_id=old_id).count() == 0
    assert db.query(Series).filter_by(user_id=old_id).count() == 0
    assert db.query(User).filter_by(telegram_id=2).first() is not None
    assert db.query(Series).count() == 1 and db.query(SeriesMatch).count() == 1


def test_purge_uses_created_at_when_never_seen(db):
    make_user(db, 1, last_seen=None, created=days_ago(400))
    make_user(db, 2, last_seen=None, created=days_ago(5))
    assert purge_inactive(db, days=365) == 1
    assert db.query(User).count() == 1


def test_delete_user_data_removes_everything(db):
    u = make_user(db, 1, last_seen=days_ago(1))
    add_data(db, u)
    uid = u.id
    delete_user_data(db, u)
    assert db.query(User).count() == 0
    assert db.query(Prediction).filter_by(user_id=uid).count() == 0
    assert db.query(Series).count() == 0 and db.query(SeriesMatch).count() == 0
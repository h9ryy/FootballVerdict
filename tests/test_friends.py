from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.friends import MAX_FRIENDS, friend_ids, link_friends
from backend.app.models import Friend, FriendRequest, Match, Prediction, User
from backend.app.retention import delete_user_data
from backend.app.scoring import INVITE_BONUS, settle_match


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def make_user(db, tg):
    u = User(telegram_id=tg, nickname=f"user{tg}", nickname_lower=f"user{tg}")
    db.add(u)
    db.commit()
    return u


def finished_match(db, n):
    m = Match(external_id=n, league="PL", matchday=1, home="A", away="B",
              kickoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=n),
              status="FINISHED", result="H")
    db.add(m)
    db.commit()
    return m


def test_link_is_mutual_and_limited(db):
    a, b = make_user(db, 1), make_user(db, 2)
    assert link_friends(db, a.id, b.id)
    db.commit()
    assert friend_ids(db, a.id) == {b.id} and friend_ids(db, b.id) == {a.id}
    assert link_friends(db, a.id, b.id)           # повтор безопасен
    for tg in range(3, 3 + MAX_FRIENDS - 1):
        assert link_friends(db, a.id, make_user(db, tg).id)
        db.commit()
    assert not link_friends(db, a.id, make_user(db, 999).id)   # лимит


def test_delete_user_clears_friendships(db):
    a, b = make_user(db, 1), make_user(db, 2)
    link_friends(db, a.id, b.id)
    db.add(FriendRequest(from_id=a.id, to_id=b.id))
    db.commit()
    delete_user_data(db, a)
    assert db.query(Friend).count() == 0 and db.query(FriendRequest).count() == 0


def test_invite_bonus_after_three_games_once(db):
    inviter, friend = make_user(db, 1), make_user(db, 2)
    friend.invited_by = inviter.id
    db.commit()
    for n in range(1, 4):
        m = finished_match(db, n)
        db.add(Prediction(user_id=friend.id, match_id=m.id, pick="H"))
        db.commit()
        settle_match(db, m)
        assert inviter.points == (INVITE_BONUS if n == 3 else 0)
    m = finished_match(db, 4)
    db.add(Prediction(user_id=friend.id, match_id=m.id, pick="H"))
    db.commit()
    settle_match(db, m)
    assert inviter.points == INVITE_BONUS          # второй раз не начисляется
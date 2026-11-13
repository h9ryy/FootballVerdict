from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base
from backend.app.models import Favorite, Match, Prediction, User
from backend.app.notify import digest_text, pending_matches

NOW = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)   # 12:00 по Москве


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def setup(db, kickoff, status="SCHEDULED", team="Arsenal"):
    u = User(telegram_id=1, nickname="u1", nickname_lower="u1")
    db.add(u)
    db.commit()
    db.add(Favorite(user_id=u.id, team=team))
    m = Match(external_id=1, league="PL", home="Arsenal", away="Chelsea", kickoff_at=kickoff, status=status)
    db.add(m)
    db.commit()
    return u, m


def test_today_match_without_prediction(db):
    u, m = setup(db, datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc))
    assert [x.id for x in pending_matches(db, u, NOW)] == [m.id]


def test_skips_predicted_match(db):
    u, m = setup(db, datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc))
    db.add(Prediction(user_id=u.id, match_id=m.id, pick="H"))
    db.commit()
    assert pending_matches(db, u, NOW) == []


def test_skips_tomorrow_started_and_cancelled(db):
    u, _ = setup(db, datetime(2026, 11, 21, 17, 0, tzinfo=timezone.utc))
    assert pending_matches(db, u, NOW) == []
    db.query(Match).update({"kickoff_at": datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)})   # уже началось
    db.commit()
    assert pending_matches(db, u, NOW) == []
    db.query(Match).update({"kickoff_at": datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc), "status": "CANCELLED"})
    db.commit()
    assert pending_matches(db, u, NOW) == []


def test_other_team_ignored(db):
    u, _ = setup(db, datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc), team="Liverpool")
    assert pending_matches(db, u, NOW) == []


def test_digest_text_has_time_and_opt_out(db):
    u, m = setup(db, datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc))
    text = digest_text([m], lambda n: n)
    assert "20:00 Arsenal — Chelsea" in text and "/notify" in text
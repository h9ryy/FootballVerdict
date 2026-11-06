from sqlalchemy.orm import Session
from .models import Match, Prediction, User

POINTS_CORRECT = 10
STREAK_BONUS = {3: 5, 5: 10, 10: 25}  # бонус за серию угаданных подряд


def settle_match(db: Session, match: Match) -> int:
    """Начислить очки по завершённому матчу. Повторный вызов безопасен."""
    if match.settled or not match.result:
        return 0

    n = 0
    for p in db.query(Prediction).filter_by(match_id=match.id).all():
        u = db.get(User, p.user_id)
        u.total += 1
        if p.pick == match.result:
            u.correct += 1
            u.streak += 1
            u.best_streak = max(u.best_streak, u.streak)
            pts = POINTS_CORRECT + STREAK_BONUS.get(u.streak, 0)
        else:
            u.streak = 0
            pts = 0
        p.points_awarded = pts
        u.points += pts
        n += 1

    match.settled = True
    db.commit()
    return n
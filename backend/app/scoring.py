from collections import Counter

from sqlalchemy.orm import Session

from .models import Match, Prediction, User

POINTS_CORRECT = 10                    # верный исход
DRAW_BONUS = 3                         # дополнительно за верную ничью
STREAK_BONUS = {3: 5, 5: 10, 10: 25}   # бонус за серию верных подряд
MIN_VOTES_FOR_RARE = 10                # бонус за редкий исход включается от 10 прогнозов на матч
# (доля игроков, выбравших этот исход, меньше которой даётся бонус; размер бонуса)
RARE_TIERS = [(0.15, 10), (0.30, 6), (0.45, 3)]


def rare_bonus(share: float, votes: int) -> int:
    """Бонус за непопулярный исход: чем меньше игроков его выбрали, тем больше."""
    if votes < MIN_VOTES_FOR_RARE:
        return 0
    for limit, bonus in RARE_TIERS:
        if share < limit:
            return bonus
    return 0


def settle_match(db: Session, match: Match) -> int:
    """Начислить очки по завершённому матчу. Повторный вызов безопасен."""
    if match.settled or not match.result:
        return 0

    preds = db.query(Prediction).filter_by(match_id=match.id).order_by(Prediction.id).all()
    total = len(preds)
    votes = Counter(p.pick for p in preds)

    for p in preds:
        u = db.get(User, p.user_id)
        u.total += 1
        if p.pick == match.result:
            u.correct += 1
            u.streak += 1
            u.best_streak = max(u.best_streak, u.streak)
            pts = POINTS_CORRECT
            if p.pick == "D":
                pts += DRAW_BONUS
            pts += rare_bonus(votes[p.pick] / total, total)
            pts += STREAK_BONUS.get(u.streak, 0)
        else:
            u.streak = 0
            pts = 0
        p.points_awarded = pts
        u.points += pts

    match.settled = True
    db.commit()
    return total
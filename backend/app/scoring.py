from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import Match, Prediction, Series, User

POINTS_CORRECT = 10                    # верный исход
DRAW_BONUS = 3                         # дополнительно за верную ничью
STREAK_BONUS = {3: 5, 5: 10, 10: 25}   # бонус за стрик (верные прогнозы подряд)
MIN_VOTES_FOR_RARE = 10                # бонус за редкий исход включается от 10 прогнозов на матч
# (доля игроков, выбравших этот исход, меньше которой даётся бонус; размер бонуса)
RARE_TIERS = [(0.15, 10), (0.30, 6), (0.45, 3)]
EXACT_BONUS = 15                       # точный счёт за 90 минут

# Серия дня
SERIES_MIN, SERIES_MAX = 3, 5
SERIES_BONUS = {3: 20, 4: 35, 5: 60}   # бонус, если угаданы все матчи серии
SERIES_WINDOW_HOURS = 48               # в серию попадают матчи ближайших 48 часов
SERIES_EXPIRE_DAYS = 7                 # если матч так и не сыгран, серия аннулируется


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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
    has_score = match.home_goals is not None and match.away_goals is not None

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
            if has_score and p.pred_home == match.home_goals and p.pred_away == match.away_goals:
                pts += EXACT_BONUS
        else:
            u.streak = 0
            pts = 0
        p.points_awarded = pts
        u.points += pts

    match.settled = True
    db.commit()
    return total


def settle_series(db: Session) -> int:
    """Подвести итог по открытым сериям дня. Повторный вызов безопасен."""
    now = datetime.now(timezone.utc)
    done = 0
    for s in db.query(Series).filter_by(status="open").all():
        matches = [it.match for it in s.items]
        if not matches:
            continue
        if any(m.status == "CANCELLED" for m in matches):
            s.status = "void"          # матч отменён: серия аннулируется без потерь
            done += 1
            continue
        if all(m.settled and m.result for m in matches):
            picks = {p.match_id: p.pick for p in db.query(Prediction).filter(
                Prediction.user_id == s.user_id,
                Prediction.match_id.in_([m.id for m in matches]))}
            if all(picks.get(m.id) == m.result for m in matches):
                bonus = SERIES_BONUS.get(len(matches), 0)
                s.status = "won"
                s.bonus_awarded = bonus
                u = db.get(User, s.user_id)
                if u:
                    u.points += bonus
            else:
                s.status = "lost"
            done += 1
            continue
        if now - max(_aware(m.kickoff_at) for m in matches) > timedelta(days=SERIES_EXPIRE_DAYS):
            s.status = "void"          # матч слишком долго не сыгран
            done += 1
    db.commit()
    return done
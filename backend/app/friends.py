import secrets
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import current_user
from .config import BOT_USERNAME, LEAGUES
from .db import get_db
from .models import Friend, FriendRequest, Match, Prediction, User
from .ranks import rank_info
from .ratelimit import strict_limit
from .scoring import INVITE_BONUS, INVITE_MAX_REWARDS, series_bonuses

log = logging.getLogger("friends")
router = APIRouter()
MAX_FRIENDS = 30
PERIOD_DAYS = {"week": 7, "month": 30}


def friend_ids(db: Session, uid: int) -> set[int]:
    return {r[0] for r in db.query(Friend.friend_id).filter(Friend.user_id == uid).all()}


def friend_count(db: Session, uid: int) -> int:
    return db.query(func.count(Friend.id)).filter(Friend.user_id == uid).scalar() or 0


def request_count(db: Session, uid: int) -> int:
    return db.query(func.count(FriendRequest.id)).filter(FriendRequest.to_id == uid).scalar() or 0


def link_friends(db: Session, a: int, b: int) -> bool:
    """Делает двух игроков друзьями (в обе стороны). False, если у кого-то список полон. Коммитит вызывающий."""
    if a == b:
        return False
    if b in friend_ids(db, a):
        return True
    if friend_count(db, a) >= MAX_FRIENDS or friend_count(db, b) >= MAX_FRIENDS:
        return False
    db.add(Friend(user_id=a, friend_id=b))
    db.add(Friend(user_id=b, friend_id=a))
    db.query(FriendRequest).filter(
        ((FriendRequest.from_id == a) & (FriendRequest.to_id == b))
        | ((FriendRequest.from_id == b) & (FriendRequest.to_id == a))).delete(synchronize_session=False)
    return True


def ensure_ref_code(db: Session, u: User) -> str:
    if not u.ref_code:
        for _ in range(5):
            code = secrets.token_urlsafe(6)[:8]
            if not db.query(User.id).filter_by(ref_code=code).first():
                u.ref_code = code
                db.commit()
                break
    return u.ref_code


def apply_referral(db: Session, u: User, code: str) -> None:
    """Новый игрок пришёл по ссылке: запоминаем, кто пригласил, и дружим. Ошибки регистрацию не ломают."""
    try:
        inviter = db.query(User).filter_by(ref_code=code.strip()).first()
        if not inviter:
            log.warning("Приглашение: код %r не найден", code)
            return
        if inviter.id == u.id:
            return
        u.invited_by = inviter.id
        if not link_friends(db, u.id, inviter.id):
            log.warning("Приглашение: список друзей полон (%s, %s)", u.id, inviter.id)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Не удалось применить приглашение")


@router.get("/api/friends")
def get_friends(db: Session = Depends(get_db), u: User = Depends(current_user)):
    code = ensure_ref_code(db, u)
    ids = friend_ids(db, u.id)
    users = db.query(User).filter(User.id.in_(ids)).all() if ids else []
    users.sort(key=lambda x: x.nickname_lower or "")
    rewarded = (db.query(func.count(User.id))
                .filter(User.invited_by == u.id, User.invite_rewarded.is_(True)).scalar() or 0)
    return {"friends": [{"nickname": f.nickname, "rank": rank_info(f.points)["key"], "points": f.points}
                        for f in users],
            "limit": MAX_FRIENDS, "link": f"https://t.me/{BOT_USERNAME}?start=ref_{code}",
            "bonus": INVITE_BONUS, "rewarded": rewarded, "max_rewards": INVITE_MAX_REWARDS}


class CodeIn(BaseModel):
    code: str


@router.post("/api/friends/by-link")
def friend_by_link(body: CodeIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    """Друзья по ссылке: подтверждение не нужно."""
    inviter = db.query(User).filter_by(ref_code=body.code.strip()).first()
    if not inviter:
        raise HTTPException(404, "Ссылка устарела")
    if inviter.id == u.id:
        raise HTTPException(400, "Это твоя ссылка")
    if not link_friends(db, u.id, inviter.id):
        raise HTTPException(409, f"Список друзей полон (лимит {MAX_FRIENDS})")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"ok": True, "nickname": inviter.nickname}


class NickIn(BaseModel):
    nickname: str


@router.post("/api/friends/request", dependencies=[Depends(strict_limit)])
def send_request(body: NickIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    """Заявка по нику: человек подтверждает её в уведомлениях."""
    other = db.query(User).filter(User.nickname_lower == body.nickname.strip().lower()).first()
    if not other:
        raise HTTPException(404, "Игрок с таким ником не найден")
    if other.id == u.id:
        raise HTTPException(400, "Это твой ник")
    if other.id in friend_ids(db, u.id):
        raise HTTPException(409, "Вы уже друзья")
    if friend_count(db, u.id) >= MAX_FRIENDS:
        raise HTTPException(409, f"Можно добавить не больше {MAX_FRIENDS} друзей")
    if db.query(FriendRequest).filter_by(from_id=other.id, to_id=u.id).first():   # встречная заявка: сразу дружим
        if not link_friends(db, u.id, other.id):
            raise HTTPException(409, "У этого игрока список друзей полон")
        db.commit()
        return {"status": "friends"}
    if not db.query(FriendRequest).filter_by(from_id=u.id, to_id=other.id).first():
        db.add(FriendRequest(from_id=u.id, to_id=other.id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return {"status": "sent"}


@router.get("/api/notifications")
def notifications(db: Session = Depends(get_db), u: User = Depends(current_user)):
    rows = (db.query(FriendRequest, User).join(User, User.id == FriendRequest.from_id)
            .filter(FriendRequest.to_id == u.id).order_by(FriendRequest.id.desc()).limit(50).all())
    return {"requests": [{"id": r.id, "nickname": s.nickname, "rank": rank_info(s.points)["key"]}
                         for r, s in rows]}


@router.post("/api/friends/requests/{rid}/accept")
def accept_request(rid: int, db: Session = Depends(get_db), u: User = Depends(current_user)):
    r = db.get(FriendRequest, rid)
    if not r or r.to_id != u.id:
        raise HTTPException(404)
    if not link_friends(db, u.id, r.from_id):
        raise HTTPException(409, f"Список друзей полон (лимит {MAX_FRIENDS})")
    db.commit()
    return {"ok": True}


@router.delete("/api/friends/requests/{rid}")
def decline_request(rid: int, db: Session = Depends(get_db), u: User = Depends(current_user)):
    db.query(FriendRequest).filter(FriendRequest.id == rid, FriendRequest.to_id == u.id).delete()
    db.commit()
    return {"ok": True}


@router.delete("/api/friends")
def remove_friend(nickname: str, db: Session = Depends(get_db), u: User = Depends(current_user)):
    other = db.query(User).filter(User.nickname_lower == nickname.strip().lower()).first()
    if other:
        db.query(Friend).filter(
            ((Friend.user_id == u.id) & (Friend.friend_id == other.id))
            | ((Friend.user_id == other.id) & (Friend.friend_id == u.id))).delete(synchronize_session=False)
        db.commit()
    return {"ok": True}


def _wr(correct: int, total: int) -> int:
    return round(correct / total * 100) if total else 0


def friends_board(period: str, league: str, db: Session, u: User) -> dict:
    """Рейтинг среди друзей: показываем всех, даже без прогнозов."""
    users = {p.id: p for p in db.query(User).filter(
        User.id.in_(friend_ids(db, u.id) | {u.id}), User.nickname.isnot(None)).all()}
    if period == "all" and not league:
        stats = {uid: (p.points, p.total, p.correct) for uid, p in users.items()}
    else:
        since = (datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS[period])) if period in PERIOD_DAYS else None
        q = (db.query(Prediction.user_id,
                      func.coalesce(func.sum(Prediction.points_awarded), 0),
                      func.count(Prediction.id),
                      func.sum(case((Prediction.pick == Match.result, 1), else_=0)))
             .join(Match, Match.id == Prediction.match_id)
             .filter(Prediction.user_id.in_(list(users)), Match.settled.is_(True), Match.result.isnot(None)))
        if since:
            q = q.filter(Match.kickoff_at >= since)
        if league:
            q = q.filter(Match.league == league)
        got = {uid: (int(pts), int(n), int(ok or 0)) for uid, pts, n, ok in q.group_by(Prediction.user_id).all()}
        bonus = series_bonuses(db, since, league or None)
        stats = {}
        for uid in users:
            pts, n, ok = got.get(uid, (0, 0, 0))
            stats[uid] = (pts + bonus.get(uid, 0), n, ok)
    order = sorted(stats.items(), key=lambda kv: (-kv[1][0], -(kv[1][2] / kv[1][1] if kv[1][1] else 0), kv[0]))
    rows = [{"place": i + 1, "nickname": users[uid].nickname, "points": pts, "winrate": _wr(ok, n),
             "me": uid == u.id, "rank": rank_info(users[uid].points)["key"]}
            for i, (uid, (pts, n, ok)) in enumerate(order)]
    mine = next(r for r in rows if r["me"])
    return {"min_games": 0, "period": period, "league": league, "scope": "friends", "rows": rows,
            "me": {"place": mine["place"], "points": mine["points"], "winrate": mine["winrate"],
                   "total": stats[u.id][1], "rank": rank_info(u.points)["key"]},
            "friends_count": len(users) - 1,
            "leagues": [{"code": c, "name": n} for c, n in LEAGUES.items()]}
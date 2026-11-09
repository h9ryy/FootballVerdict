import hashlib, hmac, json, time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from .config import BOT_TOKEN, DEV_MODE
from .db import get_db
from .models import User


def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict | None:
    """Проверка подписи Telegram. Возвращает данные пользователя или None."""
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received = parsed.pop("hash", None)
    if not received or not bot_token:
        return None

    # строка для проверки: все поля по алфавиту, каждое с новой строки
    check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc, received):
        return None
    # данные старше суток считаем просроченными
    if time.time() - int(parsed.get("auth_date", "0")) > max_age:
        return None
    try:
        return json.loads(parsed["user"])
    except (KeyError, ValueError):
        return None


def identity(
    request: Request,
    x_init_data: str = Header(default=""),
    x_dev_user: str = Header(default=""),
) -> int:
    """Кто делает запрос (id в Telegram). В базу ничего не пишет."""
    host = request.headers.get("host", "").split(":")[0]
    local = host in ("127.0.0.1", "localhost") and "x-forwarded-for" not in request.headers
    if DEV_MODE and local and x_dev_user.isdigit():
        return int(x_dev_user)  # только для локальной проверки в браузере
    info = validate_init_data(x_init_data, BOT_TOKEN)
    if not info or "id" not in info:
        raise HTTPException(401, "Откройте приложение из Telegram")
    return int(info["id"])


def current_user(tg_id: int = Depends(identity), db: Session = Depends(get_db)) -> User:
    """Зарегистрированный игрок. Записи о человеке до принятия условий не существует."""
    user = db.query(User).filter_by(telegram_id=tg_id).first()
    if not user:
        raise HTTPException(403, "Сначала примите условия и выберите ник")
    now = datetime.now(timezone.utc)
    seen = user.last_seen_at
    if seen is not None and seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    if seen is None or seen < now - timedelta(hours=24):
        user.last_seen_at = now  # «последняя активность»: обновляем не чаще раза в сутки
        db.commit()
    return user
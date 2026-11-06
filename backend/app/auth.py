import hashlib, hmac, json, time
from urllib.parse import parse_qsl
from fastapi import Depends, Header, HTTPException
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


def current_user(
    x_init_data: str = Header(default=""),
    x_dev_user: str = Header(default=""),
    db: Session = Depends(get_db),
) -> User:
    """Определяет, кто делает запрос. Создаёт пользователя при первом входе."""
    if DEV_MODE and x_dev_user.isdigit():
        tg_id = int(x_dev_user)  # только для локальной проверки в браузере
    else:
        info = validate_init_data(x_init_data, BOT_TOKEN)
        if not info or "id" not in info:
            raise HTTPException(401, "Откройте приложение из Telegram")
        tg_id = int(info["id"])

    user = db.query(User).filter_by(telegram_id=tg_id).first()
    if not user:
        user = User(telegram_id=tg_id)
        db.add(user)
        db.commit()
    return user
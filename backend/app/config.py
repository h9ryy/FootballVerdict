import os
from dotenv import load_dotenv

# читает файл .env и кладёт значения в переменные окружения
load_dotenv()

APP_NAME = os.getenv("APP_NAME", "FootballVerdict")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
DEV_MODE = os.getenv("DEV_MODE", "0") == "1"
if DEV_MODE and not DATABASE_URL.startswith("sqlite"):
    # тестовый вход под любым ID разрешён только на локальной SQLite
    raise RuntimeError("DEV_MODE=1 разрешён только с локальной SQLite. Поставь DEV_MODE=0.")
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")

# лига: код в football-data.org -> название, которое увидит человек
LEAGUES = {
    "PL": "Премьер-лига",
    "PD": "Ла Лига",
    "SA": "Серия А",
    "BL1": "Бундеслига",
    "FL1": "Лига 1",
    "CL": "Лига чемпионов",
}

INACTIVE_DELETE_DAYS = int(os.getenv("INACTIVE_DELETE_DAYS", "365"))  # через сколько дней без входа профиль удаляется
RETENTION_CHECK_SECONDS = int(os.getenv("RETENTION_CHECK_SECONDS", str(24 * 3600)))  # как часто искать неактивных
CONSENT_VERSION = "2026-11-14"  # версия текста согласия и политики: меняй вместе с privacy.html
LEADERBOARD_MIN_GAMES = 10  # сколько прогнозов с итогом нужно для рейтинга (на время проверки 3, потом вернуть 20)
PERIOD_MIN_GAMES = 5  # порог для рейтингов за неделю/месяц и по лиге
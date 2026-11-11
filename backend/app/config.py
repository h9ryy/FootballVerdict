import os
from dotenv import load_dotenv

# читает файл .env и кладёт значения в переменные окружения
load_dotenv()

APP_NAME = os.getenv("APP_NAME", "FootballVerdict")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
DEV_MODE = os.getenv("DEV_MODE", "0") == "1"
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
CONSENT_VERSION = "2026-11-08"  # версия текста согласия: меняй, когда меняешь consent.html
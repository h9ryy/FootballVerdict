import os
from dotenv import load_dotenv

# читает файл .env и кладёт значения в переменные окружения
load_dotenv()

APP_NAME = os.getenv("APP_NAME", "FootballVerdict")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
DEV_MODE = os.getenv("DEV_MODE", "0") == "1"

# лига: код в football-data.org -> название, которое увидит человек
LEAGUES = {
    "PL": "Премьер-лига",
    "PD": "Ла Лига",
    "SA": "Серия А",
    "BL1": "Бундеслига",
    "FL1": "Лига 1",
    "CL": "Лига чемпионов",
}
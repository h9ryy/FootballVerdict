from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import DATABASE_URL

# для SQLite нужна эта настройка, для Postgres не нужна
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
def ensure_columns():
    """Лёгкая миграция: добавляет новые колонки в уже созданную таблицу users."""
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    with engine.begin() as conn:
        if "notify_enabled" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN notify_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
        if "notify_last_day" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN notify_last_day VARCHAR(10)"))
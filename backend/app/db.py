from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import DATABASE_URL

# для SQLite нужна эта настройка, для Postgres не нужна
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
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
    add = {
        "notify_enabled": "BOOLEAN NOT NULL DEFAULT FALSE",
        "notify_last_day": "VARCHAR(10)",
        "ref_code": "VARCHAR(12)",
        "invited_by": "INTEGER",
        "invite_rewarded": "BOOLEAN NOT NULL DEFAULT FALSE",
    }
    with engine.begin() as conn:
        for name, ddl in add.items():
            if name not in cols:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_ref_code ON users (ref_code)"))
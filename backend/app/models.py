from datetime import datetime, timezone
from sqlalchemy import String, Integer, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    """Храним минимум: telegram_id (нужен для входа) и придуманный ник.
    Имя, username и фото из Telegram НЕ сохраняем."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(16), nullable=True)
    nickname_lower: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    adult_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)      # сыграно прогнозов
    correct: Mapped[int] = mapped_column(Integer, default=0)    # угадано
    streak: Mapped[int] = mapped_column(Integer, default=0)     # стрик: верные подряд
    best_streak: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    


class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[int] = mapped_column(unique=True)
    league: Mapped[str] = mapped_column(String(8), index=True)
    matchday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    home: Mapped[str] = mapped_column(String(64))
    away: Mapped[str] = mapped_column(String(64))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="SCHEDULED")
    result: Mapped[str | None] = mapped_column(String(1), nullable=True)  # H / D / A
    home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)  # счёт за 90 минут
    away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    settled: Mapped[bool] = mapped_column(default=False)
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="match")


class Prediction(Base):
    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    pick: Mapped[str] = mapped_column(String(1))  # H / D / A
    pred_home: Mapped[int | None] = mapped_column(Integer, nullable=True)  # прогноз точного счёта
    pred_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    match: Mapped[Match] = relationship(back_populates="predictions")
    __table_args__ = (
        UniqueConstraint("user_id", "match_id"),
        Index("ix_pred_match", "match_id"),
    )


class Series(Base):
    """Серия дня: 3-5 матчей, бонус, если угаданы все."""
    __tablename__ = "series"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[str] = mapped_column(String(10))                    # день сбора по UTC: ГГГГ-ММ-ДД
    status: Mapped[str] = mapped_column(String(8), default="open")  # open / won / lost / void
    bonus_awarded: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    items: Mapped[list["SeriesMatch"]] = relationship(back_populates="series")
    __table_args__ = (UniqueConstraint("user_id", "day"),)


class SeriesMatch(Base):
    __tablename__ = "series_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    series: Mapped[Series] = relationship(back_populates="items")
    match: Mapped[Match] = relationship()
    __table_args__ = (UniqueConstraint("series_id", "match_id"),)
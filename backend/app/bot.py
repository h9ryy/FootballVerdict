import logging
import re
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (BotCommand, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, MenuButtonWebApp, Message, WebAppInfo)

from .config import APP_NAME, BOT_TOKEN, WEBAPP_URL
from .db import SessionLocal
from .models import Match, Prediction, User

log = logging.getLogger("bot")
router = Router()
router.message.filter(F.chat.type == "private")  # кнопки Mini App работают только в личке

MSK = timezone(timedelta(hours=3))
TOP_MIN_GAMES = 3  # в рейтинг бота попадают игроки с 3+ прогнозами

WELCOME = (
    f"Привет! Это {APP_NAME}: игра в прогнозы на футбол.\n\n"
    "Выбирай матчи АПЛ, Ла Лиги, Серии А, Бундеслиги, Лиги 1 и Лиги чемпионов, "
    "угадывай исход и копи виртуальные очки.\n\n"
    "🔞 Только для 18+. Это не ставки: денег и призов здесь нет, очки виртуальные."
)

ABOUT = (
    "О проекте\n\n"
    "• Только для совершеннолетних (18+).\n"
    "• Это не азартная игра и не букмекер: ставок, денег, выигрышей и призов нет.\n"
    "• Очки виртуальные: их нельзя вывести, обменять, продать или передать.\n"
    "• Мы не пропагандируем ставки на спорт и не рекламируем букмекеров.\n"
    "• Данные о матчах: Football-Data.org. Названия клубов и турниров принадлежат "
    "их владельцам, проект с ними не связан.\n"
    "• Мы храним только ник, технический ID Telegram, прогнозы и очки. "
    "Данные можно удалить в приложении: Профиль → «Удалить мои данные»."
)

HELP = (
    "Что умеет бот:\n"
    "/profile: твои очки и винрейт\n"
    "/top: топ игроков\n"
    "/today: ближайшие матчи\n"
    "/about: правила и условия\n\n"
    "Сами прогнозы ставятся в приложении."
)

_NOISE = re.compile(
    r"\b(FC|AFC|CF|BC|SC|SK|KV|FK|UD|AC|AS|SS|US|RC|SV|VfB|VfL|SSC|ACF)\b\.?"
    r"|\b(1[89]\d\d|20\d\d|0\d)\b")


def short_name(n: str) -> str:
    s = re.sub(r"^\d+\.\s*", "", n)
    s = re.sub(r"\s+", " ", _NOISE.sub("", s)).strip()
    return s or n


def open_kb():
    if not WEBAPP_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚽ Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])


def main_kb():
    rows = []
    if WEBAPP_URL:
        rows.append([InlineKeyboardButton(text="⚽ Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))])
    rows.append([InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
                 InlineKeyboardButton(text="🏆 Рейтинг", callback_data="top")])
    rows.append([InlineKeyboardButton(text="📅 Матчи", callback_data="today"),
                 InlineKeyboardButton(text="ℹ️ Правила", callback_data="about")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_text(tg_id: int) -> str:
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(telegram_id=tg_id).first()
        if not u or not u.nickname:
            return "Ты ещё не в игре. Открой приложение и выбери ник."
        wr = round(u.correct / u.total * 100) if u.total else 0
        return (f"👤 {u.nickname}\n\n"
                f"Очки: {u.points}\n"
                f"Винрейт: {wr}% (угадано {u.correct} из {u.total})\n"
                f"Серия: {u.streak} (лучшая {u.best_streak})")
    finally:
        db.close()


def top_text() -> str:
    db = SessionLocal()
    try:
        rows = (db.query(User)
                .filter(User.nickname.isnot(None), User.total >= TOP_MIN_GAMES)
                .all())
        rows.sort(key=lambda r: (-r.points, -(r.correct / r.total if r.total else 0), r.id))
        rows = rows[:10]
        if not rows:
            return f"Пока в рейтинге никого. Нужно сделать хотя бы {TOP_MIN_GAMES} прогноза с итогом."
        medals = ["🥇", "🥈", "🥉"]
        lines = ["🏆 Топ игроков\n"]
        for i, r in enumerate(rows):
            mark = medals[i] if i < 3 else f"{i + 1}."
            wr = round(r.correct / r.total * 100) if r.total else 0
            lines.append(f"{mark} {r.nickname}: {r.points} очков ({wr}%)")
        return "\n".join(lines)
    finally:
        db.close()


def today_text(tg_id: int) -> str:
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        matches = (db.query(Match)
                   .filter(Match.kickoff_at > now, Match.kickoff_at <= now + timedelta(hours=36))
                   .order_by(Match.kickoff_at).limit(12).all())
        if not matches:
            return "В ближайшие сутки матчей нет."
        u = db.query(User).filter_by(telegram_id=tg_id).first()
        picked = set()
        if u:
            picked = {p.match_id for p in db.query(Prediction).filter_by(user_id=u.id).all()}
        today = now.astimezone(MSK).date()
        lines = ["📅 Ближайшие матчи (время МСК)"]
        last = None
        for m in matches:
            k = m.kickoff_at if m.kickoff_at.tzinfo else m.kickoff_at.replace(tzinfo=timezone.utc)
            k = k.astimezone(MSK)
            day = "Сегодня" if k.date() == today else "Завтра" if k.date() == today + timedelta(days=1) \
                else k.strftime("%d.%m")
            if day != last:
                lines.append(f"\n{day}")
                last = day
            mark = "✅" if m.id in picked else "⬜"
            lines.append(f"{mark} {k.strftime('%H:%M')} {short_name(m.home)} — {short_name(m.away)}")
        lines.append("\n✅ прогноз сделан, ⬜ ещё нет")
        return "\n".join(lines)
    finally:
        db.close()


@router.message(CommandStart())
async def cmd_start(m: Message):
    await m.answer(WELCOME, reply_markup=main_kb())


@router.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer(HELP, reply_markup=main_kb())


@router.message(Command("about"))
async def cmd_about(m: Message):
    await m.answer(ABOUT, reply_markup=open_kb())


@router.message(Command("profile"))
async def cmd_profile(m: Message):
    await m.answer(profile_text(m.from_user.id), reply_markup=open_kb())


@router.message(Command("top"))
async def cmd_top(m: Message):
    await m.answer(top_text(), reply_markup=open_kb())


@router.message(Command("today"))
async def cmd_today(m: Message):
    await m.answer(today_text(m.from_user.id), reply_markup=open_kb())


@router.callback_query(F.data == "profile")
async def cb_profile(c: CallbackQuery):
    await c.message.answer(profile_text(c.from_user.id), reply_markup=open_kb())
    await c.answer()


@router.callback_query(F.data == "top")
async def cb_top(c: CallbackQuery):
    await c.message.answer(top_text(), reply_markup=open_kb())
    await c.answer()


@router.callback_query(F.data == "today")
async def cb_today(c: CallbackQuery):
    await c.message.answer(today_text(c.from_user.id), reply_markup=open_kb())
    await c.answer()


@router.callback_query(F.data == "about")
async def cb_about(c: CallbackQuery):
    await c.message.answer(ABOUT, reply_markup=open_kb())
    await c.answer()


@router.message()
async def other(m: Message):
    await m.answer("Я понимаю команды /start, /profile, /top, /today, /about и /help. "
                   "Остальное: в приложении 👇", reply_markup=main_kb())


async def run_bot():
    if not BOT_TOKEN:
        log.warning("BOT_TOKEN не задан: бот выключен")
        return
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Начать"),
            BotCommand(command="profile", description="Мои очки и винрейт"),
            BotCommand(command="top", description="Топ игроков"),
            BotCommand(command="today", description="Ближайшие матчи"),
            BotCommand(command="about", description="О проекте и правила (18+)"),
            BotCommand(command="help", description="Помощь"),
        ])
        if WEBAPP_URL:
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
                text="Играть", web_app=WebAppInfo(url=WEBAPP_URL)))
        else:
            log.warning("WEBAPP_URL не задан: кнопки открытия приложения не будет")
        await dp.start_polling(bot, handle_signals=False)
    except Exception:
        log.exception("Бот остановился с ошибкой")
    finally:
        await bot.session.close()
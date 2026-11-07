import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (BotCommand, InlineKeyboardButton, InlineKeyboardMarkup,
                           MenuButtonWebApp, Message, WebAppInfo)
from .config import APP_NAME, BOT_TOKEN, WEBAPP_URL

log = logging.getLogger("bot")
router = Router()
router.message.filter(F.chat.type == "private")  # кнопки Mini App работают только в личке

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


def open_kb():
    if not WEBAPP_URL:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚽ Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])


@router.message(CommandStart())
async def cmd_start(m: Message):
    await m.answer(WELCOME, reply_markup=open_kb())


@router.message(Command("about"))
async def cmd_about(m: Message):
    await m.answer(ABOUT, reply_markup=open_kb())


@router.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer("Нажми «Открыть приложение», выбери лигу и матч и поставь прогноз.\n"
                   "/about: правила и условия", reply_markup=open_kb())


@router.message()
async def other(m: Message):
    await m.answer("Я понимаю команды /start, /about и /help. Остальное: в приложении 👇",
                   reply_markup=open_kb())


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
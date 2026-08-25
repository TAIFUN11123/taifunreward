import logging
import os
import html
import asyncio

from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)


# =========================================================
# НАСТРОЙКИ
# =========================================================

BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    "ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER"
)

# ID администратора бота
ADMIN_ID = 1800089290

# ЧАТ ДЛЯ РОЗЫГРЫША
RAFFLE_CHAT = "@Chattaifunn"

# Длительность розыгрыша
RAFFLE_DURATION = 180  # 3 минуты

# Предупреждение за
WARNING_SECONDS = 30


# =========================================================
# ЛОГИ
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# СОСТОЯНИЕ АДМИНА
# =========================================================

setup_state = {
    "step": None,
    "photo": None,
    "description": None,
}


# =========================================================
# СОСТОЯНИЕ РОЗЫГРЫША
# =========================================================

raffle = {
    "active": False,

    "chat_id": None,

    "photo": None,
    "description": None,

    "started_at": None,
    "ends_at": None,

    "leader_id": None,
    "leader_name": None,
    "leader_username": None,

    "warning_sent": False,

    "end_task": None,
}


# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def get_mention(user) -> str:
    """
    Красивое кликабельное упоминание пользователя.
    """

    if user.username:
        return f"@{html.escape(user.username)}"

    name = html.escape(
        user.full_name or "Пользователь"
    )

    return (
        f'<a href="tg://user?id={user.id}">'
        f"{name}"
        f"</a>"
    )


def time_left() -> int:
    """
    Сколько секунд осталось.
    """

    if not raffle["ends_at"]:
        return 0

    seconds = int(
        (
            raffle["ends_at"] - datetime.now()
        ).total_seconds()
    )

    return max(0, seconds)


def minutes_left() -> int:
    """
    Сколько минут показывать пользователю.
    """

    seconds = time_left()

    if seconds <= 0:
        return 0

    return (seconds + 59) // 60


def reset_setup():
    setup_state["step"] = None
    setup_state["photo"] = None
    setup_state["description"] = None


def reset_raffle():
    task = raffle.get("end_task")

    if task and not task.done():
        task.cancel()

    raffle["active"] = False

    raffle["chat_id"] = None

    raffle["photo"] = None
    raffle["description"] = None

    raffle["started_at"] = None
    raffle["ends_at"] = None

    raffle["leader_id"] = None
    raffle["leader_name"] = None
    raffle["leader_username"] = None

    raffle["warning_sent"] = False

    raffle["end_task"] = None


# =========================================================
# /START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not user:
        return

    if not is_admin(user.id):
        await update.message.reply_text(
            "⛔ У тебя нет доступа."
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "🎁 Запустить NFT-розыгрыш",
                callback_data="raffle_start",
            )
        ]
    ]

    await update.message.reply_text(
        "⚙️ <b>Панель администратора</b>\n\n"
        "Чат: <b>@Chattaifunn</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================================================
# КНОПКА "ЗАПУСТИТЬ РОЗЫГРЫШ"
# =========================================================

async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    if not is_admin(user.id):
        return

    if query.data != "raffle_start":
        return

    if raffle["active"]:
        await query.message.reply_text(
            "⚠️ Сейчас уже идёт розыгрыш."
        )
        return

    reset_setup()

    setup_state["step"] = "photo"

    await query.message.reply_text(
        "📸 <b>Пришли фотографию NFT.</b>\n\n"
        "После фотографии я попрошу описание.",
        parse_mode="HTML",
    )


# =========================================================
# ФОТО ОТ АДМИНА
# =========================================================

async def handle_admin_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not user:
        return

    if not is_admin(user.id):
        return

    if setup_state["step"] != "photo":
        return

    if not update.message.photo:
        return

    photo = update.message.photo[-1]

    setup_state["photo"] = photo.file_id
    setup_state["step"] = "description"

    await update.message.reply_text(
        "✅ Фото получено.\n\n"
        "📝 <b>Теперь пришли описание розыгрыша.</b>",
        parse_mode="HTML",
    )


# =========================================================
# ОПИСАНИЕ ОТ АДМИНА
# =========================================================

async def handle_admin_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if not user:
        return

    if not is_admin(user.id):
        return

    if setup_state["step"] != "description":
        return

    if not update.message.text:
        return

    description = update.message.text.strip()

    if not description:
        await update.message.reply_text(
            "❌ Описание не может быть пустым."
        )
        return

    setup_state["description"] = description

    await start_raffle(
        update,
        context,
        setup_state["photo"],
        setup_state["description"],
    )

    reset_setup()


# =========================================================
# ЗАПУСК РОЗЫГРЫША
# =========================================================

async def start_raffle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    photo_file_id: str,
    description: str,
):

    if raffle["active"]:
        await update.message.reply_text(
            "⚠️ Розыгрыш уже идёт."
        )
        return

    now = datetime.now()

    end_time = (
        now +
        timedelta(seconds=RAFFLE_DURATION)
    )

    # Сохраняем состояние
    raffle["active"] = True

    raffle["chat_id"] = None

    raffle["photo"] = photo_file_id
    raffle["description"] = description

    raffle["started_at"] = now
    raffle["ends_at"] = end_time

    raffle["leader_id"] = None
    raffle["leader_name"] = None
    raffle["leader_username"] = None

    raffle["warning_sent"] = False

    text = (
        "🎁 <b>NFT РОЗЫГРЫШ</b>\n\n"

        f"{html.escape(description)}\n\n"

        "⚡ <b>Правила:</b>\n"
        "Пиши любое сообщение в чат и становись лидером.\n"
        "Следующий участник может перебить тебя своим сообщением.\n\n"

        "⏱ <b>Длительность: 3 минуты</b>\n\n"

        "🏆 <b>Победит тот, кто будет последним лидером "
        "на момент окончания розыгрыша.</b>"
    )

    try:

        # Отправляем NFT в игровой чат
        sent_message = await context.bot.send_photo(
            chat_id=RAFFLE_CHAT,
            photo=photo_file_id,
            caption=text,
            parse_mode="HTML",
        )

        # Сохраняем реальный числовой ID чата
        raffle["chat_id"] = sent_message.chat.id

        logger.info(
            "Розыгрыш запущен в чате %s",
            sent_message.chat.id,
        )

        # Запускаем таймер
        raffle["end_task"] = asyncio.create_task(
            raffle_timer(context)
        )

        await update.message.reply_text(
            "✅ <b>Розыгрыш запущен!</b>\n\n"
            "Чат — <b>@Chattaifunn</b>\n"
            "⏱ Длительность — <b>3 минуты</b>",
            parse_mode="HTML",
        )

    except Exception as e:

        logger.exception(
            "Ошибка при запуске розыгрыша"
        )

        reset_raffle()

        await update.message.reply_text(
            "❌ <b>Не удалось запустить розыгрыш.</b>\n\n"
            f"<code>{html.escape(str(e))}</code>",
            parse_mode="HTML",
        )


# =========================================================
# ОБРАБОТКА СООБЩЕНИЙ УЧАСТНИКОВ
# =========================================================

async def raffle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not raffle["active"]:
        return

    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    # Только нужный чат
    if raffle["chat_id"] is None:
        return

    if chat.id != raffle["chat_id"]:
        return

    # Боты не участвуют
    if user.is_bot:
        return

    # Команды не участвуют
    if (
        message.text
        and message.text.startswith("/")
    ):
        return

    # Время закончилось
    if time_left() <= 0:
        return

    # Проверяем, был ли предыдущий лидер
    previous_leader = raffle["leader_id"]

    # Новый лидер
    raffle["leader_id"] = user.id
    raffle["leader_name"] = user.full_name
    raffle["leader_username"] = user.username

    mention = get_mention(user)

    left_seconds = time_left()

    minutes = left_seconds // 60
    seconds = left_seconds % 60

    if previous_leader is None:

        text = (
            "👑 <b>НОВЫЙ ЛИДЕР!</b>\n\n"
            f"{mention}\n\n"
            f"⏱ Осталось: "
            f"<b>{minutes}:{seconds:02d}</b>"
        )

    else:

        text = (
            "⚡ <b>ЛИДЕР СМЕНИЛСЯ!</b>\n\n"
            f"👑 Новый лидер: {mention}\n\n"
            f"⏱ Осталось: "
            f"<b>{minutes}:{seconds:02d}</b>"
        )

    try:

        await message.reply_text(
            text,
            parse_mode="HTML",
        )

    except Exception:

        logger.exception(
            "Ошибка отправки сообщения о лидере"
        )


# =========================================================
# ТАЙМЕР
# =========================================================

async def raffle_timer(
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        # Ждём до предупреждения
        await asyncio.sleep(
            RAFFLE_DURATION - WARNING_SECONDS
        )

        if not raffle["active"]:
            return

        # Предупреждение за 30 секунд
        if raffle["leader_id"] is not None:

            leader_name = (
                raffle["leader_name"]
                or "Текущий лидер"
            )

            if raffle["leader_username"]:

                leader = (
                    "@"
                    + html.escape(
                        raffle["leader_username"]
                    )
                )

            else:

                leader = (
                    f'<a href="tg://user?id='
                    f'{raffle["leader_id"]}">'
                    f'{html.escape(leader_name)}'
                    f"</a>"
                )

            warning_text = (
                "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
                "До конца розыгрыша осталось "
                "<b>30 секунд</b>!\n\n"
                f"👑 Текущий лидер: {leader}\n\n"
                "Кто успеет написать сообщение "
                "последним — тот победит!"
            )

        else:

            warning_text = (
                "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
                "До конца розыгрыша осталось "
                "<b>30 секунд</b>!\n\n"
                "Пока лидера нет."
            )

        await context.bot.send_message(
            chat_id=raffle["chat_id"],
            text=warning_text,
            parse_mode="HTML",
        )

        raffle["warning_sent"] = True

        # Ждём оставшиеся 30 секунд
        await asyncio.sleep(WARNING_SECONDS)

        if not raffle["active"]:
            return

        # =================================================
        # ЗАВЕРШЕНИЕ
        # =================================================

        if raffle["leader_id"] is None:

            result_text = (
                "🏁 <b>РОЗЫГРЫШ ЗАВЕРШЁН!</b>\n\n"
                "❌ Никто не участвовал."
            )

        else:

            leader_name = (
                raffle["leader_name"]
                or "Победитель"
            )

            if raffle["leader_username"]:

                winner = (
                    "@"
                    + html.escape(
                        raffle["leader_username"]
                    )
                )

            else:

                winner = (
                    f'<a href="tg://user?id='
                    f'{raffle["leader_id"]}">'
                    f'{html.escape(leader_name)}'
                    f"</a>"
                )

            result_text = (
                "🏆 <b>РОЗЫГРЫШ ЗАВЕРШЁН!</b>\n\n"
                f"🎉 Победитель:\n"
                f"👑 {winner}\n\n"
                "🎁 Поздравляем!"
            )

        await context.bot.send_message(
            chat_id=raffle["chat_id"],
            text=result_text,
            parse_mode="HTML",
        )

    except asyncio.CancelledError:

        logger.info(
            "Таймер розыгрыша отменён."
        )

        return

    except Exception:

        logger.exception(
            "Ошибка таймера розыгрыша"
        )

    finally:

        raffle["active"] = False
        raffle["end_task"] = None


# =========================================================
# ОШИБКИ
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.exception(
        "Ошибка Telegram:",
        exc_info=context.error,
    )


# =========================================================
# ЗАПУСК
# =========================================================

def main():

    if (
        not BOT_TOKEN
        or BOT_TOKEN.startswith("ВСТАВЬ")
    ):
        raise RuntimeError(
            "Не указан BOT_TOKEN."
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # /start
    application.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    # Кнопки
    application.add_handler(
        CallbackQueryHandler(
            admin_callback
        )
    )

    # Фото администратора
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_admin_photo,
        )
    )

    # Текст администратора
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_admin_description,
        ),
        group=0,
    )

    # Сообщения участников
    application.add_handler(
        MessageHandler(
            filters.ALL,
            raffle_message,
        ),
        group=10,
    )

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Бот запущен."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    main()

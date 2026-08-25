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
    CommandHandler,
    MessageHandler,
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

# Telegram ID администратора
ADMIN_ID = 1800089290

# Чат, где проходит розыгрыш
RAFFLE_CHAT = "@Chattaifunn"

# Длительность розыгрыша
RAFFLE_DURATION = 180  # 3 минуты

# Предупреждение за 30 секунд
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
# СОСТОЯНИЕ СОЗДАНИЯ РОЗЫГРЫША
# =========================================================

setup_state = {
    "step": None,
    "photo": None,
    "description": None,
}


# =========================================================
# СОСТОЯНИЕ ТЕКУЩЕГО РОЗЫГРЫША
# =========================================================

raffle = {
    "active": False,

    # Реальный числовой ID чата
    "chat_id": None,

    # Данные NFT
    "photo": None,
    "description": None,

    # Время
    "started_at": None,
    "ends_at": None,

    # Текущий лидер
    "leader_id": None,
    "leader_name": None,
    "leader_username": None,

    # Предупреждение
    "warning_sent": False,

    # Задача таймера
    "end_task": None,
}


# =========================================================
# ПРОВЕРКА АДМИНА
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# =========================================================
# УПОМИНАНИЕ ПОЛЬЗОВАТЕЛЯ
# =========================================================

def get_mention(user) -> str:
    """
    Если есть username:
        @username

    Если username нет:
        кликабельное имя пользователя.
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


# =========================================================
# СКОЛЬКО ОСТАЛОСЬ СЕКУНД
# =========================================================

def time_left() -> int:

    if not raffle["ends_at"]:
        return 0

    seconds = int(
        (
            raffle["ends_at"]
            - datetime.now()
        ).total_seconds()
    )

    return max(0, seconds)


# =========================================================
# СКОЛЬКО ОСТАЛОСЬ МИНУТ
# =========================================================

def minutes_left() -> int:

    seconds = time_left()

    if seconds <= 0:
        return 0

    return (seconds + 59) // 60


# =========================================================
# СБРОС СОЗДАНИЯ
# =========================================================

def reset_setup():

    setup_state["step"] = None
    setup_state["photo"] = None
    setup_state["description"] = None


# =========================================================
# СБРОС РОЗЫГРЫША
# =========================================================

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

    if not user or not update.message:
        return

    # =====================================================
    # ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ
    # =====================================================

    if not is_admin(user.id):

        await update.message.reply_text(
            "💬 <b>Чат для участия:</b>\n\n"
            "Чат — @Chattaifunn",
            parse_mode="HTML",
        )

        return

    # =====================================================
    # АДМИН
    # =====================================================

    keyboard = [
        [
            InlineKeyboardButton(
                "🎁 Запустить NFT-розыгрыш",
                callback_data="raffle_start",
            )
        ],
        [
            InlineKeyboardButton(
                "🛑 Остановить розыгрыш",
                callback_data="raffle_stop",
            )
        ],
    ]

    if raffle["active"]:
        status = (
            "🟢 <b>Розыгрыш сейчас идёт.</b>"
        )
    else:
        status = (
            "⚪ <b>Розыгрыш сейчас не идёт.</b>"
        )

    await update.message.reply_text(
        "⚙️ <b>Панель администратора</b>\n\n"
        "💬 <b>Чат:</b> @Chattaifunn\n\n"
        f"{status}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# АДМИНСКИЕ КНОПКИ
# =========================================================

async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    # Только админ
    if not is_admin(user.id):
        return

    # =====================================================
    # ЗАПУСК
    # =====================================================

    if query.data == "raffle_start":

        if raffle["active"]:

            await query.message.reply_text(
                "⚠️ Сейчас уже идёт розыгрыш."
            )

            return

        reset_setup()

        setup_state["step"] = "photo"

        await query.message.reply_text(
            "📸 <b>Пришли фотографию NFT.</b>\n\n"
            "После этого я попрошу описание.",
            parse_mode="HTML",
        )

        return

    # =====================================================
    # СТОП
    # =====================================================

    if query.data == "raffle_stop":

        if not raffle["active"]:

            await query.message.reply_text(
                "⚪ Сейчас розыгрыш не идёт."
            )

            return

        # Сохраняем лидера до сброса
        leader_id = raffle["leader_id"]
        leader_name = raffle["leader_name"]
        leader_username = raffle[
            "leader_username"
        ]

        # Останавливаем
        reset_raffle()

        if leader_id is None:

            text = (
                "🛑 <b>Розыгрыш остановлен.</b>\n\n"
                "Участников не было.\n\n"
                "❌ Победитель не определён."
            )

        else:

            if leader_username:

                leader = (
                    "@"
                    + html.escape(
                        leader_username
                    )
                )

            else:

                leader = (
                    f'<a href="tg://user?id={leader_id}">'
                    f'{html.escape(leader_name or "Участник")}'
                    f"</a>"
                )

            text = (
                "🛑 <b>Розыгрыш остановлен.</b>\n\n"
                f"Последний лидер: {leader}\n\n"
                "❌ Победитель не определён."
            )

        await query.message.reply_text(
            text,
            parse_mode="HTML",
        )

        return


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

    # Берём самое большое фото
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

    description = (
        update.message.text.strip()
    )

    if not description:

        await update.message.reply_text(
            "❌ Описание не может быть пустым."
        )

        return

    setup_state["description"] = description

    # Запускаем розыгрыш
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

    # =====================================================
    # ВРЕМЯ
    # =====================================================

    now = datetime.now()

    end_time = (
        now
        + timedelta(
            seconds=RAFFLE_DURATION
        )
    )

    # =====================================================
    # СОСТОЯНИЕ
    # =====================================================

    raffle["active"] = True

    # Пока None.
    # После отправки сообщения получим реальный chat.id.
    raffle["chat_id"] = None

    raffle["photo"] = photo_file_id

    raffle["description"] = description

    raffle["started_at"] = now

    raffle["ends_at"] = end_time

    raffle["leader_id"] = None
    raffle["leader_name"] = None
    raffle["leader_username"] = None

    raffle["warning_sent"] = False

    # =====================================================
    # ТЕКСТ РОЗЫГРЫША
    # =====================================================

    text = (
        "🎁 <b>NFT РОЗЫГРЫШ</b>\n\n"

        f"{html.escape(description)}\n\n"

        "⚡ <b>Правила:</b>\n"
        "Пиши любое сообщение в чат и становись лидером.\n"
        "Следующий участник может перебить тебя "
        "своим сообщением.\n\n"

        "⏱ <b>Длительность: 3 минуты</b>\n\n"

        "🏆 <b>Победит тот, кто будет последним "
        "лидером на момент окончания розыгрыша.</b>"
    )

    try:

        # =================================================
        # ОТПРАВЛЯЕМ NFT В @Chattaifunn
        # =================================================

        sent_message = (
            await context.bot.send_photo(
                chat_id=RAFFLE_CHAT,
                photo=photo_file_id,
                caption=text,
                parse_mode="HTML",
            )
        )

        # Получаем настоящий числовой ID
        raffle["chat_id"] = (
            sent_message.chat.id
        )

        logger.info(
            "Розыгрыш запущен в чате %s",
            sent_message.chat.id,
        )

        # =================================================
        # ЗАПУСКАЕМ ТАЙМЕР
        # =================================================

        raffle["end_task"] = (
            asyncio.create_task(
                raffle_timer(context)
            )
        )

        # =================================================
        # ОТВЕТ АДМИНУ
        # =================================================

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
# СООБЩЕНИЯ УЧАСТНИКОВ
# =========================================================

async def raffle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    # Розыгрыш не идёт
    if not raffle["active"]:
        return

    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message:
        return

    if not user:
        return

    if not chat:
        return

    # =====================================================
    # ПРОВЕРЯЕМ ЧАТ
    # =====================================================

    if raffle["chat_id"] is None:
        return

    if chat.id != raffle["chat_id"]:
        return

    # =====================================================
    # БОТЫ НЕ УЧАСТВУЮТ
    # =====================================================

    if user.is_bot:
        return

    # =====================================================
    # КОМАНДЫ НЕ УЧАСТВУЮТ
    # =====================================================

    if (
        message.text
        and message.text.startswith("/")
    ):
        return

    # =====================================================
    # ВРЕМЯ
    # =====================================================

    if time_left() <= 0:
        return

    # =====================================================
    # ПРЕДЫДУЩИЙ ЛИДЕР
    # =====================================================

    previous_leader = (
        raffle["leader_id"]
    )

    # =====================================================
    # НОВЫЙ ЛИДЕР
    # =====================================================

    raffle["leader_id"] = user.id

    raffle["leader_name"] = (
        user.full_name
    )

    raffle["leader_username"] = (
        user.username
    )

    mention = get_mention(user)

    # =====================================================
    # ВРЕМЯ
    # =====================================================

    seconds_left = time_left()

    minutes = seconds_left // 60
    seconds = seconds_left % 60

    # =====================================================
    # ПЕРВЫЙ УЧАСТНИК
    # =====================================================

    if previous_leader is None:

        text = (
            "👑 <b>НОВЫЙ ЛИДЕР!</b>\n\n"
            f"{mention}\n\n"
            f"⏱ Осталось: "
            f"<b>{minutes}:{seconds:02d}</b>"
        )

    # =====================================================
    # СЛЕДУЮЩИЙ УЧАСТНИК
    # =====================================================

    else:

        text = (
            "⚡ <b>ЛИДЕР СМЕНИЛСЯ!</b>\n\n"
            f"👑 Новый лидер: {mention}\n\n"
            f"⏱ Осталось: "
            f"<b>{minutes}:{seconds:02d}</b>"
        )

    # =====================================================
    # ОТВЕЧАЕМ В ЧАТ
    # =====================================================

    try:

        await message.reply_text(
            text,
            parse_mode="HTML",
        )

    except Exception:

        logger.exception(
            "Ошибка при отправке сообщения лидера"
        )


# =========================================================
# ТАЙМЕР РОЗЫГРЫША
# =========================================================

async def raffle_timer(
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        # =================================================
        # ЖДЁМ ДО 30 СЕКУНД ДО КОНЦА
        # =================================================

        await asyncio.sleep(
            RAFFLE_DURATION
            - WARNING_SECONDS
        )

        if not raffle["active"]:
            return

        # =================================================
        # ПРЕДУПРЕЖДЕНИЕ
        # =================================================

        if raffle["leader_id"] is not None:

            leader_name = (
                raffle["leader_name"]
                or "Текущий лидер"
            )

            if raffle["leader_username"]:

                leader = (
                    "@"
                    + html.escape(
                        raffle[
                            "leader_username"
                        ]
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

        # =================================================
        # ЖДЁМ ПОСЛЕДНИЕ 30 СЕКУНД
        # =================================================

        await asyncio.sleep(
            WARNING_SECONDS
        )

        if not raffle["active"]:
            return

        # =================================================
        # ОПРЕДЕЛЯЕМ ПОБЕДИТЕЛЯ
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
                        raffle[
                            "leader_username"
                        ]
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
                f"🎉 <b>Победитель:</b>\n"
                f"👑 {winner}\n\n"
                "🎁 Поздравляем!"
            )

        # =================================================
        # ОТПРАВЛЯЕМ РЕЗУЛЬТАТ
        # =================================================

        await context.bot.send_message(
            chat_id=raffle["chat_id"],
            text=result_text,
            parse_mode="HTML",
        )

    except asyncio.CancelledError:

        logger.info(
            "Таймер розыгрыша остановлен."
        )

        return

    except Exception:

        logger.exception(
            "Ошибка таймера розыгрыша."
        )

    finally:

        raffle["active"] = False

        raffle["end_task"] = None


# =========================================================
# ОБРАБОТКА ОШИБОК
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
# ЗАПУСК БОТА
# =========================================================

def main():

    if (
        not BOT_TOKEN
        or BOT_TOKEN.startswith("ВСТАВЬ")
    ):

        raise RuntimeError(
            "Не указан BOT_TOKEN."
        )

    # =====================================================
    # СОЗДАЁМ APPLICATION
    # =====================================================

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # =====================================================
    # /START
    # =====================================================

    application.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    # =====================================================
    # КНОПКИ АДМИНА
    # =====================================================

    application.add_handler(
        CallbackQueryHandler(
            admin_callback,
        )
    )

    # =====================================================
    # ФОТО
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_admin_photo,
        )
    )

    # =====================================================
    # ТЕКСТ
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_admin_description,
        ),
        group=0,
    )

    # =====================================================
    # СООБЩЕНИЯ УЧАСТНИКОВ
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.ALL,
            raffle_message,
        ),
        group=10,
    )

    # =====================================================
    # ОШИБКИ
    # =====================================================

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "===================================="
    )

    logger.info(
        "NFT Raffle Bot запущен"
    )

    logger.info(
        "Чат: %s",
        RAFFLE_CHAT,
    )

    logger.info(
        "Администратор: %s",
        ADMIN_ID,
    )

    logger.info(
        "===================================="
    )

    # =====================================================
    # ЗАПУСК POLLING
    # =====================================================

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    main()

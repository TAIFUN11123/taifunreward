import logging
import html
import asyncio
import os
import math
import random

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

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Telegram ID владельца / администратора
ADMIN_ID = 1800089290

# Чат, куда всегда публикуется розыгрыш
TARGET_CHAT_USERNAME = "@Chattaifunn"

# Длительность NFT-розыгрыша
RAFFLE_DURATION = 180

# Предупреждение за 30 секунд
WARNING_SECONDS = 30

# =========================================================
# МИШКА
# =========================================================

# 0.010 = 1% шанс на каждое сообщение
MISHKA_WIN_CHANCE = 0.001

# Кто выдаёт мишку
MISHKA_FROM = "@xxiwk"


# =========================================================
# ЛОГИ
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# СОСТОЯНИЕ СОЗДАНИЯ
# =========================================================

setup_state = {
    "step": None,
    "chat_id": None,
    "chat_title": None,
    "photo": None,
    "description": None,
}


# =========================================================
# СОСТОЯНИЕ NFT-РОЗЫГРЫША
# =========================================================

raffle = {
    "active": False,

    "chat_id": None,
    "chat_title": None,
    "chat_username": None,

    "photo": None,
    "description": None,

    "started_at": None,
    "ends_at": None,

    "leader_id": None,
    "leader_name": None,
    "leader_username": None,

    "end_task": None,
    "warning_task": None,

    # Версия таймера.
    # Нужна, чтобы старый отменённый таймер
    # не смог повлиять на новый.
    "timer_generation": 0,
}


# =========================================================
# ПРОВЕРКА АДМИНА
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# =========================================================
# НАЗВАНИЕ ЧАТА
# =========================================================

def get_chat_name(chat) -> str:

    if chat.username:
        return f"@{chat.username}"

    if chat.title:
        return chat.title

    if chat.full_name:
        return chat.full_name

    return str(chat.id)


# =========================================================
# УПОМИНАНИЕ ПОЛЬЗОВАТЕЛЯ
# =========================================================

def get_mention(user) -> str:

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
# ОСТАЛОСЬ СЕКУНД
# =========================================================

def time_left() -> int:

    if not raffle["ends_at"]:
        return 0

    seconds = math.ceil(
        (
            raffle["ends_at"]
            - datetime.now()
        ).total_seconds()
    )

    return max(0, seconds)


# =========================================================
# СБРОС СОЗДАНИЯ
# =========================================================

def reset_setup():

    setup_state["step"] = None
    setup_state["chat_id"] = None
    setup_state["chat_title"] = None
    setup_state["photo"] = None
    setup_state["description"] = None


# =========================================================
# ОТМЕНА ТАЙМЕРА
# =========================================================

def cancel_raffle_tasks():

    end_task = raffle.get("end_task")
    warning_task = raffle.get("warning_task")

    if end_task and not end_task.done():
        end_task.cancel()

    if warning_task and not warning_task.done():
        warning_task.cancel()

    raffle["end_task"] = None
    raffle["warning_task"] = None


# =========================================================
# СБРОС РОЗЫГРЫША
# =========================================================

def reset_raffle():

    cancel_raffle_tasks()

    # Увеличиваем поколение таймера.
    # Старые задачи после этого становятся недействительными.
    raffle["timer_generation"] += 1

    raffle["active"] = False

    raffle["chat_id"] = None
    raffle["chat_title"] = None
    raffle["chat_username"] = None

    raffle["photo"] = None
    raffle["description"] = None

    raffle["started_at"] = None
    raffle["ends_at"] = None

    raffle["leader_id"] = None
    raffle["leader_name"] = None
    raffle["leader_username"] = None


# =========================================================
# ЗАПУСК НОВОГО ТАЙМЕРА
# =========================================================

def restart_raffle_timer(context):

    # Отменяем старый таймер
    old_task = raffle.get("end_task")

    if old_task and not old_task.done():
        old_task.cancel()

    # Новое поколение таймера
    raffle["timer_generation"] += 1

    generation = raffle["timer_generation"]

    # Новый дедлайн = сейчас + 3 минуты
    now = datetime.now()

    raffle["ends_at"] = (
        now
        + timedelta(
            seconds=RAFFLE_DURATION
        )
    )

    # Запускаем новый таймер
    task = asyncio.create_task(
        raffle_end_timer(
            context,
            generation,
        )
    )

    raffle["end_task"] = task


# =========================================================
# /START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message

    if not user or not chat or not message:
        return

    # =====================================================
    # ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ
    # =====================================================

    if not is_admin(user.id):

        await message.reply_text(
            f"💬 Чат — {TARGET_CHAT_USERNAME}"
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

        current_chat = (
            raffle["chat_title"]
            or str(raffle["chat_id"])
        )

        status = (
            "🟢 Розыгрыш идёт\n\n"
            f"Чат — {current_chat}\n"
            f"⏱ Осталось — {time_left()} сек."
        )

    else:

        status = (
            "⚪ Розыгрыш не идёт\n\n"
            f"Чат — {TARGET_CHAT_USERNAME}"
        )

    await message.reply_text(
        "⚙️ <b>Панель администратора</b>\n\n"
        f"{status}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# КНОПКИ АДМИНА
# =========================================================

async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user = query.from_user
    chat = query.message.chat

    if not is_admin(user.id):
        return

    # =====================================================
    # ЗАПУСК
    # =====================================================

    if query.data == "raffle_start":

        if raffle["active"]:

            await query.message.reply_text(
                "⚠️ Розыгрыш уже идёт."
            )

            return

        reset_setup()

        setup_state["step"] = "photo"

        # Запоминаем чат, где админ нажал кнопку
        setup_state["chat_id"] = chat.id

        setup_state["chat_title"] = (
            get_chat_name(chat)
        )

        await query.message.reply_text(
            "📸 Пришли фотографию NFT."
        )

        return

    # =====================================================
    # СТОП
    # =====================================================

    if query.data == "raffle_stop":

        if not raffle["active"]:

            await query.message.reply_text(
                "⚪ Розыгрыш сейчас не идёт."
            )

            return

        # Сохраняем данные текущего лидера
        leader_id = raffle["leader_id"]
        leader_name = raffle["leader_name"]
        leader_username = raffle["leader_username"]

        # Останавливаем
        reset_raffle()

        if leader_id is None:

            text = (
                "🛑 <b>Розыгрыш остановлен.</b>\n\n"
                "Победитель не определён."
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
                "Победитель не определён."
            )

        await query.message.reply_text(
            text,
            parse_mode="HTML",
        )

        return


# =========================================================
# ПОЛУЧЕНИЕ ФОТО
# =========================================================

async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat

    if not user or not message or not chat:
        return

    if not is_admin(user.id):
        return

    if setup_state["step"] != "photo":
        return

    # Фото должно быть в том же чате,
    # где админ начал создание
    if chat.id != setup_state["chat_id"]:
        return

    if not message.photo:
        return

    photo = message.photo[-1]

    setup_state["photo"] = photo.file_id
    setup_state["step"] = "description"

    await message.reply_text(
        "✅ Фото получено.\n\n"
        "📝 Пришли описание."
    )


# =========================================================
# ПОЛУЧЕНИЕ ОПИСАНИЯ
# =========================================================

async def handle_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat

    if not user or not message or not chat:
        return

    if not is_admin(user.id):
        return

    if setup_state["step"] != "description":
        return

    if chat.id != setup_state["chat_id"]:
        return

    if not message.text:
        return

    description = message.text

    setup_state["description"] = description

    await start_raffle(
        context=context,
        chat_id=setup_state["chat_id"],
        chat_title=setup_state["chat_title"],
        photo=setup_state["photo"],
        description=description,
        admin_message=message,
    )

    reset_setup()


# =========================================================
# ЗАПУСК NFT-РОЗЫГРЫША
# =========================================================

async def start_raffle(
    context,
    chat_id,
    chat_title,
    photo,
    description,
    admin_message,
):

    if raffle["active"]:

        await admin_message.reply_text(
            "⚠️ Розыгрыш уже идёт."
        )

        return

    # =====================================================
    # РЕЗОЛВИМ ЦЕЛЕВОЙ ЧАТ
    # =====================================================

    try:

        target_chat = await context.bot.get_chat(
            TARGET_CHAT_USERNAME
        )

    except Exception as e:

        logger.exception(
            "Не удалось найти целевой чат"
        )

        await admin_message.reply_text(
            "❌ Не удалось найти чат "
            f"{TARGET_CHAT_USERNAME}.\n\n"
            "Проверь, что бот добавлен в этот чат "
            "как участник/админ.\n\n"
            f"{str(e)}"
        )

        return

    real_chat_id = target_chat.id
    real_chat_title = get_chat_name(target_chat)

    now = datetime.now()

    # =====================================================
    # СОХРАНЯЕМ РОЗЫГРЫШ
    # =====================================================

    raffle["active"] = True

    raffle["chat_id"] = real_chat_id
    raffle["chat_title"] = real_chat_title

    raffle["photo"] = photo
    raffle["description"] = description

    raffle["started_at"] = now

    raffle["leader_id"] = None
    raffle["leader_name"] = None
    raffle["leader_username"] = None

    # Сбрасываем старые задачи/поколение
    cancel_raffle_tasks()

    raffle["timer_generation"] += 1

    # Первый дедлайн
    raffle["ends_at"] = (
        now
        + timedelta(
            seconds=RAFFLE_DURATION
        )
    )

    caption = description

    try:

        # =================================================
        # ПУБЛИКУЕМ NFT
        # =================================================

        await context.bot.send_photo(
            chat_id=real_chat_id,
            photo=photo,
            caption=caption,
        )

        logger.info(
            "Розыгрыш запущен: %s",
            real_chat_title,
        )

        # =================================================
        # ЗАПУСКАЕМ ТАЙМЕР
        # =================================================

        generation = raffle["timer_generation"]

        raffle["end_task"] = (
            asyncio.create_task(
                raffle_end_timer(
                    context,
                    generation,
                )
            )
        )

        # =================================================
        # ОТВЕТ АДМИНУ
        # =================================================

        await admin_message.reply_text(
            "✅ Розыгрыш запущен!\n\n"
            f"Чат — {real_chat_title}\n"
            "⏱ Время — 3 минуты"
        )

    except Exception as e:

        logger.exception(
            "Ошибка запуска"
        )

        reset_raffle()

        await admin_message.reply_text(
            "❌ Не удалось запустить розыгрыш.\n\n"
            f"{str(e)}"
        )


# =========================================================
# МИШКА — СЛУЧАЙНЫЙ ПРИЗ
# =========================================================

async def try_mishka(
    context,
    message,
    user,
):

    # Случайный шанс на каждое сообщение.
    #
    # random.random() возвращает число от 0.0 до 1.0.
    #
    # При MISHKA_WIN_CHANCE = 0.010:
    # вероятность = 1%.

    if random.random() >= MISHKA_WIN_CHANCE:
        return False

    mention = get_mention(user)

    text = (
        "🎉 <b>Поздравляю!</b>\n\n"
        f"🎁 {mention} выиграл МИШКА 🧸 "
        f"от {html.escape(MISHKA_FROM)}\n"
        "✅ Подарок отправлен.\n\n"
        "🚨 Пишите сообщения в чате, и "
        "получайте возможность так же залутать подарки"
    )

    try:

        await message.reply_text(
            text,
            parse_mode="HTML",
        )

        logger.info(
            "МИШКА выигран: user_id=%s username=%s",
            user.id,
            user.username,
        )

        return True

    except Exception:

        logger.exception(
            "Не удалось отправить сообщение о мишке"
        )

        return False


# =========================================================
# СООБЩЕНИЕ УЧАСТНИКА
# =========================================================

async def raffle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    # Боты не участвуют
    if user.is_bot:
        return

    # Команды не считаются сообщением
    if (
        message.text
        and message.text.startswith("/")
    ):
        return

    # =====================================================
    # МИШКА
    # =====================================================

    # Мишка работает независимо от NFT-розыгрыша.
    #
    # Поэтому проверка идёт ДО:
    # if not raffle["active"]:
    #
    # Пользователь может выиграть мишку просто
    # за сообщение в нужном чате.

    if chat.id == raffle["chat_id"] or chat.username == TARGET_CHAT_USERNAME.lstrip("@"):

        await try_mishka(
            context=context,
            message=message,
            user=user,
        )

    # =====================================================
    # NFT-РОЗЫГРЫШ
    # =====================================================

    if not raffle["active"]:
        return

    # Только текущий чат NFT-розыгрыша
    if chat.id != raffle["chat_id"]:
        return

    # Время закончилось
    if time_left() <= 0:
        return

    # Если пишет уже текущий лидер:
    # для NFT-лидерства ничего не делаем.
    #
    # Но мишка выше всё равно проверился.
    if raffle["leader_id"] == user.id:
        return

    # =====================================================
    # НОВЫЙ ЛИДЕР
    # =====================================================

    previous_leader = raffle["leader_id"]

    raffle["leader_id"] = user.id
    raffle["leader_name"] = user.full_name
    raffle["leader_username"] = user.username

    # =====================================================
    # СБРАСЫВАЕМ ТАЙМЕР
    # =====================================================

    #
    # ВАЖНО:
    #
    # Каждый новый лидер получает новые 3 минуты.
    #
    # Старый timer отменяется.
    # ends_at становится NOW + 180 секунд.
    # Создаётся новый timer.
    #

    restart_raffle_timer(context)

    mention = get_mention(user)

    # =====================================================
    # КОРРЕКТНОЕ ОТОБРАЖЕНИЕ МИНУТ
    # =====================================================

    seconds_left = time_left()

    # 179 секунд -> 3 минуты
    # 180 секунд -> 3 минуты
    # 121 секунда -> 3 минуты
    # 120 секунд -> 2 минуты
    minutes = math.ceil(
        seconds_left / 60
    )

    # =====================================================
    # СООБЩЕНИЕ О ЛИДЕРЕ
    # =====================================================

    LEADER_EMOJI = (
        '<tg-emoji emoji-id="5350356823528455446">'
        '✨'
        '</tg-emoji>'
    )

    if previous_leader is None:

        text = (
            f"{LEADER_EMOJI} <b>Новый лидер!</b>\n\n"
            f"Новый лидер: {mention}. "
            f"До конца: {minutes} мин."
        )

    else:

        text = (
            f"{LEADER_EMOJI} <b>Перебито!</b>\n\n"
            f"Новый лидер: {mention}. "
            f"До конца: {minutes} мин."
        )

    try:

        await message.reply_text(
            text,
            parse_mode="HTML",
        )

    except Exception:

        logger.exception(
            "Не удалось отправить сообщение лидера"
        )


# =========================================================
# ТАЙМЕР NFT-РОЗЫГРЫША
# =========================================================

async def raffle_end_timer(
    context,
    generation,
):

    current_task = asyncio.current_task()

    try:

        # =================================================
        # ЖДЁМ ДО 30 СЕКУНД
        # =================================================

        await asyncio.sleep(
            max(
                0,
                RAFFLE_DURATION
                - WARNING_SECONDS,
            )
        )

        # =================================================
        # ПРОВЕРКА АКТУАЛЬНОСТИ
        # =================================================

        if not raffle["active"]:
            return

        if raffle["timer_generation"] != generation:
            return

        # Если этот task уже не является текущим
        if raffle["end_task"] is not current_task:
            return

        # =================================================
        # ПРЕДУПРЕЖДЕНИЕ
        # =================================================

        await context.bot.send_message(
            chat_id=raffle["chat_id"],
            text=(
                "⚠️ <b>30 секунд до конца!</b>"
            ),
            parse_mode="HTML",
        )

        # =================================================
        # ПОСЛЕДНИЕ 30 СЕКУНД
        # =================================================

        await asyncio.sleep(
            WARNING_SECONDS
        )

        # =================================================
        # ПРОВЕРКА ПОСЛЕ ОЖИДАНИЯ
        # =================================================

        if not raffle["active"]:
            return

        if raffle["timer_generation"] != generation:
            return

        if raffle["end_task"] is not current_task:
            return

        # Дополнительная проверка реального времени.
        # Это защищает от небольших задержек event loop.

        if time_left() > 0:

            await asyncio.sleep(
                time_left()
            )

            if not raffle["active"]:
                return

            if raffle["timer_generation"] != generation:
                return

            if raffle["end_task"] is not current_task:
                return

        # =================================================
        # ПОБЕДИТЕЛЬ
        # =================================================

        if raffle["leader_id"] is None:

            await context.bot.send_message(
                chat_id=raffle["chat_id"],
                text=(
                    "🏁 <b>Розыгрыш завершён.</b>\n\n"
                    "Никто не участвовал."
                ),
                parse_mode="HTML",
            )

        else:

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
                    f'{html.escape(raffle["leader_name"] or "Победитель")}'
                    f"</a>"
                )

            await context.bot.send_message(
                chat_id=raffle["chat_id"],
                text=(
                    "🏆 <b>РОЗЫГРЫШ ЗАВЕРШЁН!</b>\n\n"
                    f"🎉 Победитель: {winner}\n\n"
                    "🎁 Поздравляем!"
                ),
                parse_mode="HTML",
            )

    except asyncio.CancelledError:

        # Это нормальная ситуация:
        # новый лидер отменил старый таймер.
        logger.info(
            "Старый таймер отменён: generation=%s",
            generation,
        )

        return

    except Exception:

        logger.exception(
            "Ошибка таймера."
        )

    finally:

        # Очень важно:
        # старый timer НЕ должен обнулить end_task
        # нового лидера.

        if (
            raffle.get("end_task") is current_task
            and raffle.get("timer_generation") == generation
        ):
            raffle["end_task"] = None

            if raffle["active"]:
                raffle["active"] = False


# =========================================================
# ОШИБКИ
# =========================================================

async def error_handler(
    update,
    context,
):

    logger.exception(
        "Ошибка:",
        exc_info=context.error,
    )


# =========================================================
# ЗАПУСК
# =========================================================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "Переменная окружения BOT_TOKEN не найдена. "
            "Проверь имя переменной в настройках BotHost."
        )

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
    # КНОПКИ
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
            handle_photo,
        ),
        group=0,
    )

    # =====================================================
    # ТЕКСТ
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_description,
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
        "================================"
    )

    logger.info(
        "NFT Raffle Bot запущен"
    )

    logger.info(
        "Администратор: %s",
        ADMIN_ID,
    )

    logger.info(
        "Шанс мишки: %.3f (%.2f%%)",
        MISHKA_WIN_CHANCE,
        MISHKA_WIN_CHANCE * 100,
    )

    logger.info(
        "================================"
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    main()

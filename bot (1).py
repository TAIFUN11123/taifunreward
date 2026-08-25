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

# ID администратора
ADMIN_ID = 1800089290

# Чат, где проходит розыгрыш
RAFFLE_CHAT_ID = os.environ.get(
    "RAFFLE_CHAT_ID",
    "@taifun_official"
)

# Длительность розыгрыша
RAFFLE_DURATION = 180  # 3 минуты

# Предупреждение
WARNING_SECONDS = 30


# =========================================================
# ЛОГИ
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# =========================================================
# СОСТОЯНИЕ
# =========================================================

# Процесс создания розыгрыша админом
setup_state = {
    "step": None,
    "photo": None,
    "description": None,
}

# Текущий розыгрыш
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


def get_display_name(user) -> str:
    """
    Получаем красивое имя пользователя.
    """
    if user.username:
        return f"@{user.username}"

    name = user.full_name or "Пользователь"
    return name


def get_mention(user) -> str:
    """
    Упоминание пользователя.
    Если есть username — показываем @username.
    Если username нет — делаем кликабельное упоминание.
    """
    if user.username:
        return f"@{html.escape(user.username)}"

    name = html.escape(user.full_name or "Пользователь")

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
        (raffle["ends_at"] - datetime.now()).total_seconds()
    )

    return max(0, seconds)


def minutes_left() -> int:
    """
    Показываем минуты как на скрине.
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
    old_task = raffle.get("end_task")

    if old_task and not old_task.done():
        old_task.cancel()

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
# АДМИНСКОЕ МЕНЮ
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not user or not is_admin(user.id):
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "🎁 Запустить NFT-розыгрыш",
                callback_data="raffle_start"
            )
        ]
    ]

    await update.message.reply_text(
        "⚙️ <b>Панель администратора</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# НАЖАТИЕ "ЗАПУСТИТЬ РОЗЫГРЫШ"
# =========================================================

async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    user = query.from_user

    await query.answer()

    if not is_admin(user.id):
        return

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
            parse_mode="HTML"
        )


# =========================================================
# ПОЛУЧЕНИЕ ФОТО ОТ АДМИНА
# =========================================================

async def handle_admin_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not user or not is_admin(user.id):
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
        parse_mode="HTML"
    )


# =========================================================
# ПОЛУЧЕНИЕ ОПИСАНИЯ
# =========================================================

async def handle_admin_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not user or not is_admin(user.id):
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

    # Запускаем розыгрыш
    await start_raffle(
        update,
        context,
        setup_state["photo"],
        setup_state["description"]
    )

    reset_setup()


# =========================================================
# ЗАПУСК РОЗЫГРЫША
# =========================================================

async def start_raffle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    photo_file_id: str,
    description: str
):
    # На всякий случай
    if raffle["active"]:
        await update.message.reply_text(
            "⚠️ Розыгрыш уже идёт."
        )
        return

    now = datetime.now()
    end_time = now + timedelta(seconds=RAFFLE_DURATION)

    raffle["active"] = True
    raffle["chat_id"] = RAFFLE_CHAT_ID
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
        "Другой участник может перебить тебя своим сообщением.\n\n"
        "⏱ <b>Длительность: 3 минуты</b>"
    )

    try:
        # Публикуем фотографию + описание
        await context.bot.send_photo(
            chat_id=RAFFLE_CHAT_ID,
            photo=photo_file_id,
            caption=text,
            parse_mode="HTML"
        )

        logger.info(
            "Розыгрыш запущен в %s",
            RAFFLE_CHAT_ID
        )

        # Запускаем таймер
        raffle["end_task"] = asyncio.create_task(
            raffle_timer(context)
        )

        await update.message.reply_text(
            "✅ <b>Розыгрыш запущен!</b>\n\n"
            f"Канал/чат: {html.escape(str(RAFFLE_CHAT_ID))}\n"
            "⏱ Длительность: 3 минуты",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.exception("Ошибка при запуске розыгрыша")

        reset_raffle()

        await update.message.reply_text(
            "❌ Не удалось запустить розыгрыш.\n\n"
            f"<code>{html.escape(str(e))}</code>",
            parse_mode="HTML"
        )


# =========================================================
# ОБРАБОТКА ЛЮБОГО СООБЩЕНИЯ В ЧАТЕ
# =========================================================

async def raffle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    Любое сообщение пользователя во время активного розыгрыша
    делает его новым лидером.
    """

    if not raffle["active"]:
        return

    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    # Только нужный чат
    if str(chat.id) != str(raffle["chat_id"]):
        # Если RAFFLE_CHAT_ID задан как @username,
        # chat.id будет числом, поэтому отдельно разрешаем
        # сообщения из текущего активного чата.
        if raffle["chat_id"] != chat.id:
            return

    # Боты не участвуют
    if user.is_bot:
        return

    # Команды не считаем участием
    if message.text and message.text.startswith("/"):
        return

    # Время закончилось
    if time_left() <= 0:
        return

    # Новый лидер
    raffle["leader_id"] = user.id
    raffle["leader_name"] = user.full_name
    raffle["leader_username"] = user.username

    mention = get_mention(user)
    left = minutes_left()

    # =====================================================
    # ПЕРВЫЙ УЧАСТНИК
    # =====================================================

    # Это можно определить по предыдущему состоянию.
    # Если лидер был None — первый участник.
    # Но мы уже перезаписали его выше, поэтому определяем
    # через сохранённый ID.

    # Эта часть исправляется ниже через отдельную проверку.

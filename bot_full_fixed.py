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

# Длительность NFT-розыгрыша / мини-ивента
RAFFLE_DURATION = 180

# Предупреждение за 30 секунд
WARNING_SECONDS = 30

# =========================================================
# МИШКА
# =========================================================

# 0.010 = 1% шанс на каждое сообщение
MISHKA_WIN_CHANCE = 0.000

# Кто выдаёт мишку
MISHKA_FROM = "@xxiwk"


# =========================================================
# РЕДКИЕ МИШКИ (ДЖЕКПОТ)
# =========================================================

# Шанс каждой редкой мишки — независимо от обычной,
# значительно меньше её. Обычная мишка при этом
# не меняется.
RARE_MISHKA_CHANCE = 0.00005

# Кто выдаёт редкие мишки
RARE_MISHKA_FROM = "@bogkm"

# Эмодзи для джекпот-сообщения (💥) и галочки (✅)
JACKPOT_EMOJI = (
    '<tg-emoji emoji-id="5276032951342088188">'
    '💥'
    '</tg-emoji>'
)

CHECK_EMOJI = (
    '<tg-emoji emoji-id="5348095454527635884">'
    '✅'
    '</tg-emoji>'
)

# =========================================================
# КАСТОМНЫЕ ЭМОДЗИ ДЛЯ ОБЫЧНОЙ МИШКИ
# =========================================================

# Перед "@ровов выиграл МИШКА 🧸 от @xxiwk"
MISHKA_WIN_EMOJI = (
    '<tg-emoji emoji-id="5348404473129614535">'
    '✅'
    '</tg-emoji>'
)

# Перед "Поздравляю!" (мишка) / перед "У нас есть победитель!" (мини-ивент)
CONGRATS_EMOJI = (
    '<tg-emoji emoji-id="5350626912546865231">'
    '‼️'
    '</tg-emoji>'
)

# Перед "Подарок отправлен." (мишка) / перед "Приз:" (мини-ивент, финал)
GIFT_SENT_EMOJI = (
    '<tg-emoji emoji-id="5350572310627632617">'
    '✅'
    '</tg-emoji>'
)

# Перед "Пишите сообщения в чате..."
MESSAGE_CTA_EMOJI = (
    '<tg-emoji emoji-id="5348232622898167572">'
    '♥️'
    '</tg-emoji>'
)

# =========================================================
# КАСТОМНЫЕ ЭМОДЗИ ДЛЯ МИНИ-ИВЕНТА
# =========================================================

# Перед "Мини ивент!" / "Приз поставлен в очередь" / "Ивент завершён!"
EVENT_FIRE_EMOJI = (
    '<tg-emoji emoji-id="5348529413728256481">'
    '🔥'
    '</tg-emoji>'
)

# Перед "Пишите свои варианты в чат"
EVENT_SPARKLE_EMOJI = (
    '<tg-emoji emoji-id="5348275460901977184">'
    '💫'
    '</tg-emoji>'
)

# Перед "Первый кто угадает..."
EVENT_LIGHTNING_EMOJI = (
    '<tg-emoji emoji-id="5350618807943576963">'
    '⚡'
    '</tg-emoji>'
)

# Список всех редких мишек: имя + кастомный эмодзи
RARE_MISHKAS = [
    {
        "name": "НГ",
        "emoji_id": "5379850840691476775",
        "emoji_char": "🎁",
    },
    {
        "name": "14 февраля",
        "emoji_id": "5393309541620291208",
        "emoji_char": "🎁",
    },
    {
        "name": "Терр",
        "emoji_id": "5470129614439362117",
        "emoji_char": "🎂",
    },
    {
        "name": "Пасхальная",
        "emoji_id": "5393309541620291208",
        "emoji_char": "🎁",
    },
    {
        "name": "1 мая",
        "emoji_id": "5447213743417105726",
        "emoji_char": "🎁",
    },
    {
        "name": "Клоун",
        "emoji_id": "5359736160224586485",
        "emoji_char": "🎁",
    },
    {
        "name": "Футбольная",
        "emoji_id": "5397971251878732060",
        "emoji_char": "🧸",
    },
    {
        "name": "Лепрекон",
        "emoji_id": "5317000922096769303",
        "emoji_char": "🎁",
    },
    {
        "name": "8 марта",
        "emoji_id": "5289761157173775507",
        "emoji_char": "🧸",
    },
]


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
    "type": None,  # "nft" / "number" / "event"
    "chat_id": None,
    "chat_title": None,
    "photo": None,
    "description": None,
    "number": None,
    "min_number": None,
    "max_number": None,
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
# СОСТОЯНИЕ ИГРЫ "УГАДАЙ ЧИСЛО"
# =========================================================

number_game = {
    "active": False,

    "chat_id": None,
    "chat_title": None,
    "chat_username": None,

    "photo": None,
    "description": None,

    "number": None,

    "started_at": None,

    "winner_id": None,
    "winner_name": None,
    "winner_username": None,
}


# =========================================================
# СОСТОЯНИЕ МИНИ-ИВЕНТА
# (угадай число в диапазоне + лидерство/таймер как у NFT)
# =========================================================

mini_event = {
    "active": False,

    "chat_id": None,
    "chat_title": None,

    "min_number": None,
    "max_number": None,
    "number": None,

    "photo": None,
    "description": None,

    "started_at": None,
    "ends_at": None,

    "leader_id": None,
    "leader_name": None,
    "leader_username": None,

    "end_task": None,

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
# ОСТАЛОСЬ СЕКУНД (NFT-РОЗЫГРЫШ)
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
# ОСТАЛОСЬ СЕКУНД (МИНИ-ИВЕНТ)
# =========================================================

def time_left_event() -> int:

    if not mini_event["ends_at"]:
        return 0

    seconds = math.ceil(
        (
            mini_event["ends_at"]
            - datetime.now()
        ).total_seconds()
    )

    return max(0, seconds)


# =========================================================
# СБРОС СОЗДАНИЯ
# =========================================================

def reset_setup():

    setup_state["step"] = None
    setup_state["type"] = None
    setup_state["chat_id"] = None
    setup_state["chat_title"] = None
    setup_state["photo"] = None
    setup_state["description"] = None
    setup_state["number"] = None
    setup_state["min_number"] = None
    setup_state["max_number"] = None


# =========================================================
# ОТМЕНА ТАЙМЕРА (NFT-РОЗЫГРЫШ)
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
# СБРОС РОЗЫГРЫША (NFT)
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
# СБРОС ИГРЫ "УГАДАЙ ЧИСЛО"
# =========================================================

def reset_guess_game():

    number_game["active"] = False

    number_game["chat_id"] = None
    number_game["chat_title"] = None
    number_game["chat_username"] = None

    number_game["photo"] = None
    number_game["description"] = None

    number_game["number"] = None

    number_game["started_at"] = None

    number_game["winner_id"] = None
    number_game["winner_name"] = None
    number_game["winner_username"] = None


# =========================================================
# ОТМЕНА ТАЙМЕРА (МИНИ-ИВЕНТ)
# =========================================================

def cancel_event_tasks():

    end_task = mini_event.get("end_task")

    if end_task and not end_task.done():
        end_task.cancel()

    mini_event["end_task"] = None


# =========================================================
# СБРОС МИНИ-ИВЕНТА
# =========================================================

def reset_event():

    cancel_event_tasks()

    mini_event["timer_generation"] += 1

    mini_event["active"] = False

    mini_event["chat_id"] = None
    mini_event["chat_title"] = None

    mini_event["min_number"] = None
    mini_event["max_number"] = None
    mini_event["number"] = None

    mini_event["photo"] = None
    mini_event["description"] = None

    mini_event["started_at"] = None
    mini_event["ends_at"] = None

    mini_event["leader_id"] = None
    mini_event["leader_name"] = None
    mini_event["leader_username"] = None


# =========================================================
# ЗАПУСК НОВОГО ТАЙМЕРА (NFT-РОЗЫГРЫШ)
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
# ЗАПУСК НОВОГО ТАЙМЕРА (МИНИ-ИВЕНТ)
# =========================================================

def restart_event_timer(context):

    old_task = mini_event.get("end_task")

    if old_task and not old_task.done():
        old_task.cancel()

    mini_event["timer_generation"] += 1

    generation = mini_event["timer_generation"]

    now = datetime.now()

    mini_event["ends_at"] = (
        now
        + timedelta(
            seconds=RAFFLE_DURATION
        )
    )

    task = asyncio.create_task(
        event_end_timer(
            context,
            generation,
        )
    )

    mini_event["end_task"] = task


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
        [
            InlineKeyboardButton(
                "🔢 Угадай число",
                callback_data="guess_start",
            )
        ],
        [
            InlineKeyboardButton(
                "🛑 Остановить \"Угадай число\"",
                callback_data="guess_stop",
            )
        ],
        [
            InlineKeyboardButton(
                "🔥 Запустить Мини-ивент",
                callback_data="event_start",
            )
        ],
        [
            InlineKeyboardButton(
                "🛑 Остановить Мини-ивент",
                callback_data="event_stop",
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

    if number_game["active"]:

        guess_chat = (
            number_game["chat_title"]
            or str(number_game["chat_id"])
        )

        guess_status = (
            "🟢 \"Угадай число\" идёт\n\n"
            f"Чат — {guess_chat}"
        )

    else:

        guess_status = (
            "⚪ \"Угадай число\" не идёт"
        )

    if mini_event["active"]:

        event_chat = (
            mini_event["chat_title"]
            or str(mini_event["chat_id"])
        )

        event_status = (
            "🟢 Мини-ивент идёт\n\n"
            f"Чат — {event_chat}\n"
            f"Диапазон — {mini_event['min_number']}–{mini_event['max_number']}\n"
            f"⏱ Осталось — {time_left_event()} сек."
        )

    else:

        event_status = (
            "⚪ Мини-ивент не идёт"
        )

    await message.reply_text(
        "⚙️ <b>Панель администратора</b>\n\n"
        f"{status}\n\n"
        f"{guess_status}\n\n"
        f"{event_status}",
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
    # ЗАПУСК NFT
    # =====================================================

    if query.data == "raffle_start":

        if raffle["active"]:

            await query.message.reply_text(
                "⚠️ Розыгрыш уже идёт."
            )

            return

        reset_setup()

        setup_state["step"] = "photo"
        setup_state["type"] = "nft"

        # Запоминаем чат, где админ нажал кнопку
        setup_state["chat_id"] = chat.id

        setup_state["chat_title"] = (
            get_chat_name(chat)
        )

        await query.message.reply_text(
            "📸 Пришли фотографию NFT.\n\n"
            "Или отправь «-», если без фото."
        )

        return

    # =====================================================
    # СТОП NFT
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

    # =====================================================
    # УГАДАЙ ЧИСЛО — ЗАПУСК
    # =====================================================

    if query.data == "guess_start":

        if number_game["active"]:

            await query.message.reply_text(
                "⚠️ Игра \"Угадай число\" уже идёт."
            )

            return

        reset_setup()

        setup_state["step"] = "number_input"
        setup_state["type"] = "number"

        setup_state["chat_id"] = chat.id

        setup_state["chat_title"] = (
            get_chat_name(chat)
        )

        await query.message.reply_text(
            "🔢 Пришли число, которое нужно угадать."
        )

        return

    # =====================================================
    # УГАДАЙ ЧИСЛО — СТОП
    # =====================================================

    if query.data == "guess_stop":

        if not number_game["active"]:

            await query.message.reply_text(
                "⚪ Игра \"Угадай число\" сейчас не идёт."
            )

            return

        reset_guess_game()

        await query.message.reply_text(
            "🛑 <b>Игра \"Угадай число\" остановлена.</b>\n\n"
            "Победитель не определён.",
            parse_mode="HTML",
        )

        return

    # =====================================================
    # МИНИ-ИВЕНТ — ЗАПУСК
    # =====================================================

    if query.data == "event_start":

        if mini_event["active"]:

            await query.message.reply_text(
                "⚠️ Мини-ивент уже идёт."
            )

            return

        reset_setup()

        setup_state["step"] = "event_min"
        setup_state["type"] = "event"

        setup_state["chat_id"] = chat.id

        setup_state["chat_title"] = (
            get_chat_name(chat)
        )

        await query.message.reply_text(
            "🔢 Пришли минимальное число диапазона."
        )

        return

    # =====================================================
    # МИНИ-ИВЕНТ — СТОП
    # =====================================================

    if query.data == "event_stop":

        if not mini_event["active"]:

            await query.message.reply_text(
                "⚪ Мини-ивент сейчас не идёт."
            )

            return

        reset_event()

        await query.message.reply_text(
            f"{EVENT_FIRE_EMOJI} <b>Мини-ивент остановлен.</b>\n\n"
            "Победитель не определён.",
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

    if setup_state["type"] == "event":

        await message.reply_text(
            "✅ Фото получено.\n\n"
            "📝 Пришли описание приза."
        )

    else:

        await message.reply_text(
            "✅ Фото получено.\n\n"
            "📝 Пришли описание."
        )


# =========================================================
# ПРОПУСК ФОТО (ТЕКСТОМ "-")
# =========================================================

async def handle_skip_photo(
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

    if chat.id != setup_state["chat_id"]:
        return

    if not message.text:
        return

    if message.text.strip() != "-":
        return

    setup_state["photo"] = None
    setup_state["step"] = "description"

    if setup_state["type"] == "event":

        await message.reply_text(
            "✅ Без фото.\n\n"
            "📝 Пришли описание приза."
        )

    else:

        await message.reply_text(
            "✅ Без фото.\n\n"
            "📝 Пришли описание."
        )


# =========================================================
# ПОЛУЧЕНИЕ ЧИСЛА (ИГРА "УГАДАЙ ЧИСЛО")
# =========================================================

async def handle_number_input(
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

    if setup_state["step"] != "number_input":
        return

    if chat.id != setup_state["chat_id"]:
        return

    if not message.text:
        return

    raw = message.text.strip()

    if not raw.lstrip("-").isdigit():

        await message.reply_text(
            "⚠️ Это не похоже на число. "
            "Пришли число ещё раз."
        )

        return

    setup_state["number"] = int(raw)
    setup_state["step"] = "photo"

    await message.reply_text(
        "✅ Число сохранено.\n\n"
        "📸 Пришли фото (по желанию).\n\n"
        "Или отправь «-», если без фото."
    )


# =========================================================
# МИНИ-ИВЕНТ: МИНИМАЛЬНОЕ ЧИСЛО ДИАПАЗОНА
# =========================================================

async def handle_event_min(
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

    if setup_state["step"] != "event_min":
        return

    if chat.id != setup_state["chat_id"]:
        return

    if not message.text:
        return

    raw = message.text.strip()

    if not raw.lstrip("-").isdigit():

        await message.reply_text(
            "⚠️ Это не похоже на число. "
            "Пришли минимальное число ещё раз."
        )

        return

    setup_state["min_number"] = int(raw)
    setup_state["step"] = "event_max"

    await message.reply_text(
        "✅ Минимальное число сохранено.\n\n"
        "🔢 Теперь пришли максимальное число диапазона."
    )


# =========================================================
# МИНИ-ИВЕНТ: МАКСИМАЛЬНОЕ ЧИСЛО ДИАПАЗОНА
# =========================================================

async def handle_event_max(
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

    if setup_state["step"] != "event_max":
        return

    if chat.id != setup_state["chat_id"]:
        return

    if not message.text:
        return

    raw = message.text.strip()

    if not raw.lstrip("-").isdigit():

        await message.reply_text(
            "⚠️ Это не похоже на число. "
            "Пришли максимальное число ещё раз."
        )

        return

    max_number = int(raw)

    if max_number <= setup_state["min_number"]:

        await message.reply_text(
            "⚠️ Максимальное число должно быть больше минимального. "
            "Пришли максимальное число ещё раз."
        )

        return

    setup_state["max_number"] = max_number
    setup_state["step"] = "event_number"

    await message.reply_text(
        "✅ Диапазон сохранён.\n\n"
        "🎯 Теперь пришли число, которое ты загадал "
        f"(от {setup_state['min_number']} до {setup_state['max_number']})."
    )


# =========================================================
# МИНИ-ИВЕНТ: ЗАГАДАННОЕ ЧИСЛО
# =========================================================

async def handle_event_number(
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

    if setup_state["step"] != "event_number":
        return

    if chat.id != setup_state["chat_id"]:
        return

    if not message.text:
        return

    raw = message.text.strip()

    if not raw.lstrip("-").isdigit():

        await message.reply_text(
            "⚠️ Это не похоже на число. "
            "Пришли загаданное число ещё раз."
        )

        return

    number = int(raw)

    if not (setup_state["min_number"] <= number <= setup_state["max_number"]):

        await message.reply_text(
            "⚠️ Число должно быть в диапазоне "
            f"{setup_state['min_number']}–{setup_state['max_number']}. "
            "Пришли ещё раз."
        )

        return

    setup_state["number"] = number
    setup_state["step"] = "photo"

    await message.reply_text(
        "✅ Число сохранено.\n\n"
        "📸 Пришли фото приза (по желанию).\n\n"
        "Или отправь «-», если без фото."
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

    # text_html сохраняет кастомные эмодзи (и другое форматирование)
    # в виде HTML-тегов <tg-emoji>, в отличие от обычного message.text,
    # где кастомный эмодзи превращается в обычный юникод-символ.
    description = message.text_html

    setup_state["description"] = description

    if setup_state["type"] == "number":

        await start_guess_game(
            context=context,
            chat_id=setup_state["chat_id"],
            chat_title=setup_state["chat_title"],
            photo=setup_state["photo"],
            description=description,
            number=setup_state["number"],
            admin_message=message,
        )

    elif setup_state["type"] == "event":

        await start_mini_event(
            context=context,
            chat_id=setup_state["chat_id"],
            chat_title=setup_state["chat_title"],
            photo=setup_state["photo"],
            description=description,
            number=setup_state["number"],
            min_number=setup_state["min_number"],
            max_number=setup_state["max_number"],
            admin_message=message,
        )

    else:

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
# ДИСПЕТЧЕР ТЕКСТОВЫХ СООБЩЕНИЙ АДМИНА
# =========================================================
#
# В группе 0 срабатывает только один подходящий по фильтру
# хендлер, поэтому все текстовые шаги настройки
# (пропуск фото / число / описание / шаги мини-ивента)
# разведены здесь по текущему setup_state["step"],
# а не отдельными хендлерами.

async def handle_admin_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    step = setup_state["step"]

    if step == "photo":
        await handle_skip_photo(update, context)
        return

    if step == "number_input":
        await handle_number_input(update, context)
        return

    if step == "event_min":
        await handle_event_min(update, context)
        return

    if step == "event_max":
        await handle_event_max(update, context)
        return

    if step == "event_number":
        await handle_event_number(update, context)
        return

    if step == "description":
        await handle_description(update, context)
        return


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
        # (фото не обязательно)
        # =================================================

        if photo:

            await context.bot.send_photo(
                chat_id=real_chat_id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
            )

        else:

            await context.bot.send_message(
                chat_id=real_chat_id,
                text=caption,
                parse_mode="HTML",
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
# ЗАПУСК ИГРЫ "УГАДАЙ ЧИСЛО"
# =========================================================

async def start_guess_game(
    context,
    chat_id,
    chat_title,
    photo,
    description,
    number,
    admin_message,
):

    if number_game["active"]:

        await admin_message.reply_text(
            "⚠️ Игра \"Угадай число\" уже идёт."
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
    # СОХРАНЯЕМ ИГРУ
    # =====================================================

    reset_guess_game()

    number_game["active"] = True

    number_game["chat_id"] = real_chat_id
    number_game["chat_title"] = real_chat_title

    number_game["photo"] = photo
    number_game["description"] = description

    number_game["number"] = number

    number_game["started_at"] = now

    caption = description

    try:

        # =================================================
        # ПУБЛИКУЕМ ПОСТ ИГРЫ
        # (фото не обязательно)
        # =================================================

        if photo:

            await context.bot.send_photo(
                chat_id=real_chat_id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
            )

        else:

            await context.bot.send_message(
                chat_id=real_chat_id,
                text=caption,
                parse_mode="HTML",
            )

        logger.info(
            "Игра \"Угадай число\" запущена: %s",
            real_chat_title,
        )

        # =================================================
        # ОТВЕТ АДМИНУ
        # =================================================

        await admin_message.reply_text(
            "✅ Игра \"Угадай число\" запущена!\n\n"
            f"Чат — {real_chat_title}"
        )

    except Exception as e:

        logger.exception(
            "Ошибка запуска игры \"Угадай число\""
        )

        reset_guess_game()

        await admin_message.reply_text(
            "❌ Не удалось запустить игру.\n\n"
            f"{str(e)}"
        )


# =========================================================
# ЗАПУСК МИНИ-ИВЕНТА
# =========================================================

async def start_mini_event(
    context,
    chat_id,
    chat_title,
    photo,
    description,
    number,
    min_number,
    max_number,
    admin_message,
):

    if mini_event["active"]:

        await admin_message.reply_text(
            "⚠️ Мини-ивент уже идёт."
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
    # СОХРАНЯЕМ МИНИ-ИВЕНТ
    # =====================================================

    reset_event()

    mini_event["active"] = True

    mini_event["chat_id"] = real_chat_id
    mini_event["chat_title"] = real_chat_title

    mini_event["min_number"] = min_number
    mini_event["max_number"] = max_number
    mini_event["number"] = number

    mini_event["photo"] = photo
    mini_event["description"] = description

    mini_event["started_at"] = now

    mini_event["leader_id"] = None
    mini_event["leader_name"] = None
    mini_event["leader_username"] = None

    cancel_event_tasks()

    mini_event["timer_generation"] += 1

    mini_event["ends_at"] = (
        now
        + timedelta(
            seconds=RAFFLE_DURATION
        )
    )

    caption = (
        f'{EVENT_FIRE_EMOJI} <b>Мини-ивент "Угадай число"!</b>\n\n'
        f"{CONGRATS_EMOJI} Я загадал число от "
        f"{min_number} до {max_number}.\n"
        f"{EVENT_SPARKLE_EMOJI} Пишите свои варианты в чат!\n\n"
        f"{EVENT_LIGHTNING_EMOJI} Первый, кто угадает, "
        f"получит NFT: {description}"
    )

    try:

        # =================================================
        # ПУБЛИКУЕМ ПОСТ МИНИ-ИВЕНТА
        # (фото не обязательно)
        # =================================================

        if photo:

            await context.bot.send_photo(
                chat_id=real_chat_id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
            )

        else:

            await context.bot.send_message(
                chat_id=real_chat_id,
                text=caption,
                parse_mode="HTML",
            )

        logger.info(
            "Мини-ивент запущен: %s",
            real_chat_title,
        )

        # =================================================
        # ЗАПУСКАЕМ ТАЙМЕР
        # =================================================

        generation = mini_event["timer_generation"]

        mini_event["end_task"] = (
            asyncio.create_task(
                event_end_timer(
                    context,
                    generation,
                )
            )
        )

        # =================================================
        # ОТВЕТ АДМИНУ
        # =================================================

        await admin_message.reply_text(
            "✅ Мини-ивент запущен!\n\n"
            f"Чат — {real_chat_title}\n"
            f"Диапазон — {min_number}–{max_number}\n"
            "⏱ Время — 3 минуты"
        )

    except Exception as e:

        logger.exception(
            "Ошибка запуска мини-ивента"
        )

        reset_event()

        await admin_message.reply_text(
            "❌ Не удалось запустить мини-ивент.\n\n"
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

    mention = get_mention(user)

    # =====================================================
    # РЕДКИЕ МИШКИ (ДЖЕКПОТ)
    # =====================================================
    #
    # Каждая редкая мишка проверяется отдельным,
    # независимым броском — с намного меньшим шансом,
    # чем у обычной. Если выпала редкая — обычная в этом
    # сообщении уже не проверяется.

    for rare in RARE_MISHKAS:

        if random.random() >= RARE_MISHKA_CHANCE:
            continue

        mishka_emoji = (
            f'<tg-emoji emoji-id="{rare["emoji_id"]}">'
            f'{rare["emoji_char"]}'
            f'</tg-emoji>'
        )

        text = (
            f"{JACKPOT_EMOJI} <b>ДЖЕКПОООТ!</b>\n\n"
            f"{mishka_emoji} {mention} выиграл мишку "
            f"«{rare['name']}» {mishka_emoji} "
            f"от {html.escape(RARE_MISHKA_FROM)}\n"
            f"{CHECK_EMOJI} Подарок отправлен."
        )

        try:

            await message.reply_text(
                text,
                parse_mode="HTML",
            )

            logger.info(
                "РЕДКАЯ МИШКА выигран: user_id=%s "
                "username=%s name=%s",
                user.id,
                user.username,
                rare["name"],
            )

            return True

        except Exception:

            logger.exception(
                "Не удалось отправить сообщение "
                "о редкой мишке"
            )

            return False

    # =====================================================
    # ОБЫЧНАЯ МИШКА
    # =====================================================

    # Случайный шанс на каждое сообщение.
    #
    # random.random() возвращает число от 0.0 до 1.0.
    #
    # При MISHKA_WIN_CHANCE = 0.010:
    # вероятность = 1%.

    if random.random() >= MISHKA_WIN_CHANCE:
        return False

    text = (
        f"{CONGRATS_EMOJI} <b>Поздравляю!</b>\n\n"
        f"{MISHKA_WIN_EMOJI} {mention} выиграл МИШКА 🧸 "
        f"от {html.escape(MISHKA_FROM)}\n"
        f"{GIFT_SENT_EMOJI} Подарок отправлен.\n\n"
        f"{MESSAGE_CTA_EMOJI} Пишите сообщения в чате, и "
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

    # Редактирование старого сообщения НЕ считается новым сообщением.
    # При этом мишка также не проверяется повторно при редактировании.
    if update.edited_message or update.edited_channel_post:
        return

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
    # МИНИ-ИВЕНТ
    # (угадай число в диапазоне + держать лидерство)
    # =====================================================
    #
    # Работает независимо от NFT-розыгрыша и "Угадай число".
    #
    # Логика такая же, как у NFT-розыгрыша:
    # каждый верный ответ делает игрока лидером
    # и сбрасывает таймер на 3 минуты.
    # Если 3 минуты никто больше не угадал —
    # ивент завершается, лидер объявляется победителем.

    if (
        mini_event["active"]
        and not is_admin(user.id)
        and chat.id == mini_event["chat_id"]
        and message.text
        and time_left_event() > 0
    ):

        guess = message.text.strip()

        if (
            guess.lstrip("-").isdigit()
            and int(guess) == mini_event["number"]
            and mini_event["leader_id"] != user.id
        ):

            mini_event["leader_id"] = user.id
            mini_event["leader_name"] = user.full_name
            mini_event["leader_username"] = user.username

            restart_event_timer(context)

            mention = get_mention(user)

            text = (
                f"{CONGRATS_EMOJI} <b>У нас есть победитель!</b>\n\n"
                f"{mention} первым угадал число: "
                f"<b>{mini_event['number']}</b>\n"
                f"{EVENT_FIRE_EMOJI} Приз: {mini_event['description']} "
                "поставлен в очередь!"
            )

            try:

                await message.reply_text(
                    text,
                    parse_mode="HTML",
                )

            except Exception:

                logger.exception(
                    "Не удалось отправить сообщение "
                    "о победителе мини-ивента"
                )

    # =====================================================
    # УГАДАЙ ЧИСЛО
    # =====================================================
    #
    # Работает независимо от NFT-розыгрыша, как и МИШКА.
    #
    # Редактирование сообщений сюда никогда не попадает —
    # оно отсекается ещё в самом начале функции
    # (update.edited_message / update.edited_channel_post).
    # Поэтому если первая попытка была неверной,
    # исправление её редактированием НЕ засчитывается.

    if (
        number_game["active"]
        and not is_admin(user.id)
        and chat.id == number_game["chat_id"]
        and message.text
    ):

        guess = message.text.strip()

        if (
            guess.lstrip("-").isdigit()
            and int(guess) == number_game["number"]
        ):

            number_game["active"] = False

            number_game["winner_id"] = user.id
            number_game["winner_name"] = user.full_name
            number_game["winner_username"] = user.username

            mention = get_mention(user)

            text = (
                "🎉 <b>У нас есть победитель!</b>\n\n"
                f"{mention} первым угадал число: "
                f"<b>{number_game['number']}</b>"
            )

            try:

                await message.reply_text(
                    text,
                    parse_mode="HTML",
                )

            except Exception:

                logger.exception(
                    "Не удалось отправить сообщение "
                    "о победителе \"Угадай число\""
                )

    # =====================================================
    # NFT-РОЗЫГРЫШ
    # =====================================================

    if not raffle["active"]:
        return

    # Админы могут получать МИШКУ выше,
    # но не могут участвовать в NFT-розыгрыше
    # и перебивать лидера.
    if is_admin(user.id):
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
    # (ниже — оригинальный код сообщения о лидере)
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
# ТАЙМЕР МИНИ-ИВЕНТА
# =========================================================

async def event_end_timer(
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

        if not mini_event["active"]:
            return

        if mini_event["timer_generation"] != generation:
            return

        if mini_event["end_task"] is not current_task:
            return

        # =================================================
        # ПРЕДУПРЕЖДЕНИЕ
        # =================================================

        await context.bot.send_message(
            chat_id=mini_event["chat_id"],
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

        if not mini_event["active"]:
            return

        if mini_event["timer_generation"] != generation:
            return

        if mini_event["end_task"] is not current_task:
            return

        # Дополнительная проверка реального времени.

        if time_left_event() > 0:

            await asyncio.sleep(
                time_left_event()
            )

            if not mini_event["active"]:
                return

            if mini_event["timer_generation"] != generation:
                return

            if mini_event["end_task"] is not current_task:
                return

        # =================================================
        # ПОБЕДИТЕЛЬ
        # =================================================

        if mini_event["leader_id"] is None:

            await context.bot.send_message(
                chat_id=mini_event["chat_id"],
                text=(
                    f"{EVENT_FIRE_EMOJI} <b>Ивент завершён.</b>\n\n"
                    "Никто не угадал число."
                ),
                parse_mode="HTML",
            )

        else:

            if mini_event["leader_username"]:

                winner = (
                    "@"
                    + html.escape(
                        mini_event["leader_username"]
                    )
                )

            else:

                winner = (
                    f'<a href="tg://user?id='
                    f'{mini_event["leader_id"]}">'
                    f'{html.escape(mini_event["leader_name"] or "Победитель")}'
                    f"</a>"
                )

            await context.bot.send_message(
                chat_id=mini_event["chat_id"],
                text=(
                    f"{EVENT_FIRE_EMOJI} <b>Ивент завершён!</b>\n\n"
                    f"{MISHKA_WIN_EMOJI} Победитель: {winner}.\n"
                    f"{GIFT_SENT_EMOJI} Приз: "
                    f"{mini_event['description'] or ''}"
                ),
                parse_mode="HTML",
            )

    except asyncio.CancelledError:

        logger.info(
            "Старый таймер мини-ивента отменён: generation=%s",
            generation,
        )

        return

    except Exception:

        logger.exception(
            "Ошибка таймера мини-ивента."
        )

    finally:

        if (
            mini_event.get("end_task") is current_task
            and mini_event.get("timer_generation") == generation
        ):
            mini_event["end_task"] = None

            if mini_event["active"]:
                mini_event["active"] = False


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
            handle_admin_text,
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
        "Шанс каждой редкой мишки: %.5f (%.4f%%), всего типов: %s",
        RARE_MISHKA_CHANCE,
        RARE_MISHKA_CHANCE * 100,
        len(RARE_MISHKAS),
    )

    logger.info(
        "================================"
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    main()

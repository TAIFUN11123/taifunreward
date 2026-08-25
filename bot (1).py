import logging
import random
import os
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

# Длительность розыгрыша
RAFFLE_DURATION = 180  # 3 минуты

# За сколько секунд предупредить о конце
WARNING_SECONDS = 30

# Название приза
RAFFLE_PRIZE = "Nail Bracelet #118"

# Текст приза
RAFFLE_PRIZE_TEXT = "NFT Nail Bracelet #118"

# Картинка NFT.
# Если не нужна — оставь пустым ""
RAFFLE_IMAGE = ""

# =========================================================


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# СОСТОЯНИЕ РОЗЫГРЫША
# =========================================================

raffles = {}

# Структура:
#
# raffles[chat_id] = {
#     "active": True,
#     "participants": {
#         user_id: {
#             "name": "...",
#             "username": "...",
#             "messages": 10
#         }
#     },
#     "message_id": 123,
#     "end_time": datetime(...)
# }


# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================

def get_display_name(user):
    if user.username:
        return f"@{user.username}"

    return user.first_name or "Участник"


def get_mention(user):
    return user.mention_html()


def get_leader(chat_id):
    raffle = raffles.get(chat_id)

    if not raffle:
        return None, 0

    participants = raffle["participants"]

    if not participants:
        return None, 0

    leader = max(
        participants.values(),
        key=lambda x: x["messages"]
    )

    return leader, leader["messages"]


def get_remaining_seconds(chat_id):
    raffle = raffles.get(chat_id)

    if not raffle:
        return 0

    remaining = (
        raffle["end_time"] - datetime.utcnow()
    ).total_seconds()

    return max(0, int(remaining))


# =========================================================
# АДМИН-МЕНЮ
# =========================================================

async def cmd_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    user = update.effective_user

    if not user:
        return

    if user.id != ADMIN_ID:
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "🎁 Запустить NFT-розыгрыш",
                callback_data="raffle_start"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Статус розыгрыша",
                callback_data="raffle_status"
            )
        ],
        [
            InlineKeyboardButton(
                "🛑 Остановить розыгрыш",
                callback_data="raffle_stop"
            )
        ],
    ]

    await update.message.reply_text(
        "👑 <b>Панель администратора</b>\n\n"
        "🎁 Здесь можно управлять NFT-розыгрышем.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# КНОПКИ АДМИН-МЕНЮ
# =========================================================

async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    query = update.callback_query

    if not query:
        return

    user = query.from_user

    if user.id != ADMIN_ID:
        await query.answer(
            "⛔ У вас нет доступа.",
            show_alert=True
        )
        return

    await query.answer()

    chat_id = query.message.chat.id

    # -----------------------------------------------------
    # ЗАПУСК
    # -----------------------------------------------------

    if query.data == "raffle_start":

        if chat_id in raffles and raffles[chat_id]["active"]:
            await query.answer(
                "❗ В этом чате уже идёт розыгрыш.",
                show_alert=True
            )
            return

        end_time = (
            datetime.utcnow()
            + timedelta(seconds=RAFFLE_DURATION)
        )

        raffles[chat_id] = {
            "active": True,
            "participants": {},
            "message_id": None,
            "end_time": end_time,
            "warning_sent": False,
        }

        keyboard = [
            [
                InlineKeyboardButton(
                    "🎁 ПОКАЗАТЬ ПОДАРОК",
                    callback_data="show_prize"
                )
            ]
        ]

        text = (
            "🎉 <b>Ивент начался!</b>\n\n"
            "💬 Пишите сообщения в чате, "
            "чтобы участвовать в розыгрыше.\n\n"
            f"🎁 <b>Приз:</b> {RAFFLE_PRIZE}\n\n"
            "🏆 Победит участник, который "
            "наберёт больше всего сообщений.\n\n"
            "⏱ <b>До конца: 3 мин.</b>"
        )

        if RAFFLE_IMAGE and os.path.exists(RAFFLE_IMAGE):

            with open(RAFFLE_IMAGE, "rb") as photo:

                sent = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )

        else:

            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        raffles[chat_id]["message_id"] = sent.message_id

        asyncio.create_task(
            raffle_timer(
                context,
                chat_id
            )
        )

        logger.info(
            f"Raffle started chat={chat_id}"
        )

    # -----------------------------------------------------
    # СТАТУС
    # -----------------------------------------------------

    elif query.data == "raffle_status":

        raffle = raffles.get(chat_id)

        if not raffle or not raffle["active"]:

            await query.answer(
                "Сейчас розыгрыш не идёт.",
                show_alert=True
            )
            return

        leader, count = get_leader(chat_id)
        remaining = get_remaining_seconds(chat_id)

        if leader:

            status = (
                f"🏆 Лидер: {leader['name']}\n"
                f"💬 Сообщений: {count}\n"
                f"👥 Участников: "
                f"{len(raffle['participants'])}\n"
                f"⏱ Осталось: {remaining} сек."
            )

        else:

            status = (
                "👥 Участников пока нет.\n"
                f"⏱ Осталось: {remaining} сек."
            )

        await query.answer(
            status,
            show_alert=True
        )

    # -----------------------------------------------------
    # ОСТАНОВКА
    # -----------------------------------------------------

    elif query.data == "raffle_stop":

        raffle = raffles.get(chat_id)

        if not raffle or not raffle["active"]:

            await query.answer(
                "Розыгрыш не запущен.",
                show_alert=True
            )
            return

        raffle["active"] = False

        await context.bot.send_message(
            chat_id=chat_id,
            text="🛑 <b>Розыгрыш остановлен администратором.</b>",
            parse_mode="HTML"
        )

        logger.info(
            f"Raffle stopped chat={chat_id}"
        )

    # -----------------------------------------------------
    # ПОКАЗАТЬ ПРИЗ
    # -----------------------------------------------------

    elif query.data == "show_prize":

        await query.answer(
            f"🎁 Приз: {RAFFLE_PRIZE_TEXT}",
            show_alert=True
        )


# =========================================================
# ТАЙМЕР РОЗЫГРЫША
# =========================================================

async def raffle_timer(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int
) -> None:

    await asyncio.sleep(
        max(
            0,
            RAFFLE_DURATION - WARNING_SECONDS
        )
    )

    raffle = raffles.get(chat_id)

    if not raffle or not raffle["active"]:
        return

    raffle["warning_sent"] = True

    leader, count = get_leader(chat_id)

    if leader:

        leader_text = (
            f"🏆 Лидер: {leader['name']}\n"
            f"💬 Сообщений: {count}\n\n"
        )

    else:

        leader_text = (
            "👥 Пока никто не участвует.\n\n"
        )

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🚨 <b>До конца розыгрыша осталось 30 секунд!</b>\n\n"
            f"{leader_text}"
            "🔥 Пишите сообщения и перебивайте лидера!"
        ),
        parse_mode="HTML"
    )

    await asyncio.sleep(WARNING_SECONDS)

    raffle = raffles.get(chat_id)

    if not raffle or not raffle["active"]:
        return

    await finish_raffle(
        context,
        chat_id
    )


# =========================================================
# ЗАВЕРШЕНИЕ РОЗЫГРЫША
# =========================================================

async def finish_raffle(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int
) -> None:

    raffle = raffles.get(chat_id)

    if not raffle:
        return

    if not raffle["active"]:
        return

    raffle["active"] = False

    participants = raffle["participants"]

    if not participants:

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "😢 <b>Розыгрыш завершён.</b>\n\n"
                "Никто не успел принять участие."
            ),
            parse_mode="HTML"
        )

        return

    max_messages = max(
        participant["messages"]
        for participant in participants.values()
    )

    # Если несколько участников набрали одинаковое
    # количество сообщений — выбираем одного случайно.
    leaders = [
        participant
        for participant in participants.values()
        if participant["messages"] == max_messages
    ]

    winner = random.choice(leaders)

    mention = winner["mention"]

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🏆 <b>РОЗЫГРЫШ ЗАВЕРШЁН!</b>\n\n"
            f"🎉 Победитель: {mention}\n"
            f"🎁 Приз: <b>{RAFFLE_PRIZE}</b>\n\n"
            f"💬 Сообщений: <b>{winner['messages']}</b>\n"
            "✅ Поздравляем с победой!"
        ),
        parse_mode="HTML"
    )

    logger.info(
        f"Raffle winner "
        f"chat={chat_id} "
        f"user={winner['user_id']} "
        f"messages={winner['messages']}"
    )


# =========================================================
# ОБРАБОТКА СООБЩЕНИЙ
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if message is None:
        return

    if chat is None:
        return

    if user is None:
        return

    # Ботов не считаем
    if user.is_bot:
        return

    # Команды не считаем
    if message.text and message.text.startswith("/"):
        return

    raffle = raffles.get(chat.id)

    # Если в этом чате нет активного розыгрыша
    if not raffle:
        return

    if not raffle["active"]:
        return

    # Проверяем время
    if datetime.utcnow() >= raffle["end_time"]:

        await finish_raffle(
            context,
            chat.id
        )

        return

    participants = raffle["participants"]

    # Новый участник
    if user.id not in participants:

        participants[user.id] = {
            "user_id": user.id,
            "name": get_display_name(user),
            "username": user.username,
            "mention": get_mention(user),
            "messages": 1,
        }

        # Первое сообщение участника
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"🎉 <b>У нас первый участник!</b>\n\n"
                f"👤 {get_mention(user)}\n"
                "🔥 Продолжай писать сообщения!"
            ),
            parse_mode="HTML"
        )

    else:

        participants[user.id]["messages"] += 1

    # -----------------------------------------------------
    # ПОКАЗЫВАЕМ ТЕКУЩЕГО ЛИДЕРА
    # -----------------------------------------------------

    leader, count = get_leader(chat.id)

    if leader and leader["user_id"] == user.id:

        # Не отправляем сообщение на каждое сообщение,
        # чтобы чат не заспамился.
        #
        # Но если пользователь перебил предыдущий рекорд,
        # показываем уведомление.

        previous_best = raffle.get("previous_best", 0)

        if count > previous_best:

            raffle["previous_best"] = count

            # Отправляем уведомление только при новом рекорде
            if count > 1:

                await context.bot.send_message(
                    chat_id=chat.id,
                    text=(
                        "🔄 <b>Перебито!</b>\n\n"
                        f"🏆 Новый лидер: {get_mention(user)}\n"
                        f"💬 Сообщений: <b>{count}</b>\n\n"
                        f"⏱ До конца: "
                        f"{get_remaining_seconds(chat.id) // 60} мин."
                    ),
                    parse_mode="HTML"
                )


# =========================================================
# START
# =========================================================

async def cmd_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    await update.message.reply_text(
        "🤖 Бот работает."
    )


# =========================================================
# MAIN
# =========================================================

def main() -> None:

    if not BOT_TOKEN or "ВСТАВЬ" in BOT_TOKEN:

        raise SystemExit(
            "Укажи токен бота в переменной окружения BOT_TOKEN."
        )

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # /start
    app.add_handler(
        CommandHandler(
            "start",
            cmd_start
        )
    )

    # /admin — только ADMIN_ID
    app.add_handler(
        CommandHandler(
            "admin",
            cmd_admin
        )
    )

    # Кнопки
    app.add_handler(
        CallbackQueryHandler(
            admin_callback
        )
    )

    # Сообщения участников
    app.add_handler(
        MessageHandler(
            (
                filters.TEXT
                | filters.PHOTO
                | filters.Sticker.ALL
                | filters.VIDEO
                | filters.Document.ALL
            )
            & ~filters.COMMAND,
            handle_message
        )
    )

    logger.info(
        "🤖 Бот запущен..."
    )

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()

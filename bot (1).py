import logging
import random
import os
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)


# ============ НАСТРОЙКИ ============

BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    "ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER"
)

# Шанс выигрыша на каждое сообщение
# 1.0 = 100%
# 0.001 = 0.1%
WIN_CHANCE = 0.005

# Подарки
GIFTS = [
    ("Мишка", "🧸"),
]

# Кто дарит подарок
GIFT_SENDER_USERNAME = "xxiwk"

# Минимальный интервал между победами
# в одном чате
COOLDOWN_SECONDS = 60


# ============================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# Время последнего выигрыша в каждом чате
last_win_time: dict[int, datetime] = {}


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if message is None or user is None or chat is None:
        return

    # Игнорируем сообщения от ботов
    if user.is_bot:
        return

    # Игнорируем команды
    if message.text and message.text.startswith("/"):
        return

    # Проверяем кулдаун
    now = datetime.utcnow()

    last = last_win_time.get(chat.id)

    if last and (
        now - last
    ) < timedelta(seconds=COOLDOWN_SECONDS):
        return

    # Проверяем шанс
    if random.random() > WIN_CHANCE:
        return

    # ============ ПОБЕДА ============

    last_win_time[chat.id] = now

    gift_name, gift_emoji = random.choice(GIFTS)

    # Упоминание пользователя
    mention = user.mention_html()

    text = (
        f"🎉 Поздравляю!\n"
        f"🎁 {mention} выиграл "
        f"<b>{gift_name} {gift_emoji}</b> "
        f"от @{GIFT_SENDER_USERNAME}\n"
        f"✅ Подарок отправлен.\n\n"
        f"🚨 Пишите сообщения в чате, "
        f"и получайте возможность так же "
        f"залутать подарки"
    )

    # Бот ОТВЕЧАЕТ на сообщение победителя
    await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        parse_mode="HTML",
        reply_to_message_id=message.message_id,
    )

    logger.info(
        f"Win! "
        f"chat={chat.id} "
        f"user={user.id} "
        f"gift={gift_name}"
    )


async def cmd_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    await update.message.reply_text(
        "канал-@taifun_official"
    )


async def cmd_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    await update.message.reply_text(
        f"Текущий шанс выигрыша: "
        f"{WIN_CHANCE * 100:.3f}% "
        f"на каждое сообщение."
    )


def main() -> None:

    if not BOT_TOKEN or "ВСТАВЬ" in BOT_TOKEN:
        raise SystemExit(
            "Укажи токен бота в переменной окружения BOT_TOKEN "
            "(получить у @BotFather в Telegram)."
        )

    app = Application.builder().token(
        BOT_TOKEN
    ).build()

    app.add_handler(
        CommandHandler(
            "start",
            cmd_start
        )
    )

    app.add_handler(
        CommandHandler(
            "stats",
            cmd_stats
        )
    )

    # Ловим обычные сообщения,
    # фотографии и стикеры
    app.add_handler(
        MessageHandler(
            filters.TEXT
            | filters.PHOTO
            | filters.Sticker.ALL,
            handle_message
        )
    )

    logger.info("Бот запущен...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()

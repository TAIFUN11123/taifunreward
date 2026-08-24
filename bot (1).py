import logging
import random
import os
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

# ============ НАСТРОЙКИ ============

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВСТАВЬ_СЮДА_ТОКЕН_ОТ_BOTFATHER")

# Шанс выигрыша на каждое сообщение (0.001 = 0.1%, очень редко)
# ВРЕМЕННО 1.0 (100%) для теста — потом верни маленькое значение типа 0.001
WIN_CHANCE = 1.0

# Список подарков, которые может выдать бот (название + эмодзи)
GIFTS = [
    ("Мишка", "🧸"),
]

# Кто дарит подарки (упомянут в сообщении о победе)
GIFT_SENDER_USERNAME = "bogkm"  # без @, поставь свой юзернейм

# Минимальный интервал между победами в одном чате (в секундах), чтобы не было выигрышей подряд
COOLDOWN_SECONDS = 60

# Путь к картинке, которая отправляется вместе с сообщением о победе
# (файл должен лежать рядом с bot.py, в папке assets)
WIN_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "assets", "winner.png")

# Не засчитывать сообщения от ботов и команды (/start и т.п.)
# =====================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# last_win_time[chat_id] = datetime последнего выигрыша, чтобы не сыпать подряд
last_win_time: dict[int, datetime] = {}


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if message is None or user is None or chat is None:
        return
    if user.is_bot:
        return
    # игнорируем команды типа /start
    if message.text and message.text.startswith("/"):
        return

    # проверка кулдауна, чтобы после победы не сыпалось сразу ещё раз
    now = datetime.utcnow()
    last = last_win_time.get(chat.id)
    if last and (now - last) < timedelta(seconds=COOLDOWN_SECONDS):
        return

    # бросаем кубик
    if random.random() > WIN_CHANCE:
        return  # не повезло, тихо ничего не делаем

    # ПОБЕДА
    last_win_time[chat.id] = now
    gift_name, gift_emoji = random.choice(GIFTS)

    mention = user.mention_html()

    text = (
        f"🎉 Поздравляю!\n"
        f"🎁 {mention} выиграл <b>{gift_name}</b> {gift_emoji} "
        f"от @{GIFT_SENDER_USERNAME}\n"
        f"✅ Подарок отправлен."
    )

    if os.path.exists(WIN_IMAGE_PATH):
        with open(WIN_IMAGE_PATH, "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=photo,
                caption=text,
                parse_mode="HTML",
                reply_to_message_id=message.message_id,
            )
    else:
        # если картинки нет — просто отправляем текст, чтобы бот не падал
        await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            parse_mode="HTML",
            reply_to_message_id=message.message_id,
        )
    logger.info(f"Win! chat={chat.id} user={user.id} gift={gift_name}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("канал-@taifun_official")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # простая команда для проверки, что бот жив
    await update.message.reply_text(f"Текущий шанс выигрыша: {WIN_CHANCE*100:.3f}% на каждое сообщение.")


def main() -> None:
    if not BOT_TOKEN or "ВСТАВЬ" in BOT_TOKEN:
        raise SystemExit(
            "Укажи токен бота в переменной окружения BOT_TOKEN "
            "(получить у @BotFather в Telegram)."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    # ловим все обычные текстовые/медиа сообщения (не команды)
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.Sticker.ALL, handle_message))

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

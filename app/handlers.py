import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.config import Settings
from app.llm import generate_reply
from app.rag import format_citations, format_context, retrieve_chunks
from app.session import (
    ModalMonthlyQuotaExceeded,
    ModalQuotaStoreUnavailable,
    clear_session,
    get_history,
    save_exchange,
)

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat and update.message:
        settings = context.application.bot_data["settings"]
        await clear_session(settings, str(update.effective_chat.id))
        await update.message.reply_text(
            "Hi! I'm your general-purpose AI assistant. Ask me anything, or use /help."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "/start - Start a fresh conversation\n"
            "/help - Show available commands\n"
            "/reset - Clear this conversation"
        )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat and update.message:
        settings = context.application.bot_data["settings"]
        await clear_session(settings, str(update.effective_chat.id))
        await update.message.reply_text("Conversation history cleared.")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_chat:
        return

    settings: Settings = context.application.bot_data["settings"]
    chat_id = str(update.effective_chat.id)
    user_message = update.message.text.strip()
    if not user_message:
        return

    user_id = update.effective_user.id if update.effective_user else "unknown"
    logger.info("Received message from Telegram user %s", user_id)
    messages = await get_history(settings, chat_id)
    messages.append({"role": "user", "content": user_message})

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        chunks = await retrieve_chunks(settings, user_message)
        rag_context = format_context(chunks, settings.rag_context_max_chars)
        reply = await generate_reply(settings, messages, rag_context)
        if chunks:
            reply += format_citations(chunks)
        if not reply:
            reply = "The model returned an empty response. Please try again."
    except ModalMonthlyQuotaExceeded:
        await update.message.reply_text(
            "Đã đạt giới hạn lượt gọi Modal tháng này. Bot sẽ mở lại vào đầu tháng sau."
        )
        return
    except ModalQuotaStoreUnavailable:
        logger.exception("Modal monthly quota store is unavailable for chat %s", chat_id)
        await update.message.reply_text(
            "Mình tạm dừng gọi model để bảo vệ ngân sách vì Valkey chưa sẵn sàng."
        )
        return
    except Exception:
        logger.exception("LLM request failed for chat %s", chat_id)
        await update.message.reply_text(
            "I couldn't reach the AI service just now. Please try again in a moment."
        )
        return

    await update.message.reply_text(reply)
    await save_exchange(settings, chat_id, user_message, reply)
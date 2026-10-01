import logging

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.config import get_settings
from app.handlers import help_command, message_handler, reset_command, start_command
from app.session import close_session_store

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def _shutdown(application: Application) -> None:
    del application
    await close_session_store()


def build_application() -> Application:
    settings = get_settings()
    application = Application.builder().token(settings.bot_token).post_shutdown(_shutdown).build()
    application.bot_data["settings"] = settings
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    return application


def main() -> None:
    load_dotenv()
    build_application().run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
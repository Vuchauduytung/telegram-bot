import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot


async def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()
    webhook_url = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if not token or not webhook_url or not secret:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN, WEBHOOK_URL, and WEBHOOK_SECRET.")
    if not webhook_url.startswith("https://"):
        raise RuntimeError("WEBHOOK_URL must use HTTPS.")

    async with Bot(token) as bot:
        await bot.set_webhook(
            url=f"{webhook_url}/webhook",
            secret_token=secret,
            allowed_updates=["message"],
        )
    print("Telegram webhook configured.")


if __name__ == "__main__":
    asyncio.run(main())
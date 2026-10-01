import hmac
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update
from telegram.ext import Application

from app.handlers import help_command, message_handler, reset_command, start_command
from app.main import build_application
from app.session import close_session_store


def valid_webhook_secret(received: str | None, expected: str) -> bool:
    return bool(received and expected) and hmac.compare_digest(received, expected)


@asynccontextmanager
async def lifespan(web_app: FastAPI) -> AsyncIterator[None]:
    load_dotenv()
    webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if len(webhook_secret) < 32:
        raise RuntimeError("WEBHOOK_SECRET must contain at least 32 characters.")

    application = build_application()
    await application.initialize()
    await application.start()
    web_app.state.telegram_application = application
    web_app.state.webhook_secret = webhook_secret
    try:
        yield
    finally:
        await application.stop()
        await application.shutdown()
        await close_session_store()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def telegram_webhook(
    request: Request,
    secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict[str, bool]:
    expected_secret = request.app.state.webhook_secret
    if not valid_webhook_secret(secret_token, expected_secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        payload = await request.json()
        application: Application = request.app.state.telegram_application
        update = Update.de_json(payload, application.bot)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid Telegram update") from None

    if update is not None:
        await application.process_update(update)
    return {"ok": True}
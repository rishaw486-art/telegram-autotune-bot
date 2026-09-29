from contextlib import asynccontextmanager
import logging
import os

from aiogram import Bot
from fastapi import FastAPI, Header, HTTPException, Request

from .bot import build_dispatcher
from .config import settings
from .db import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("autotune")

bot = Bot(settings.telegram_bot_token)
dp = build_dispatcher()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    public_url = settings.public_bot_url.strip().rstrip("/") or os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if public_url:
        webhook_url = f"{public_url}/telegram/webhook/{settings.webhook_secret}"
        await bot.set_webhook(webhook_url, drop_pending_updates=False, secret_token=settings.webhook_secret)
        info = await bot.get_webhook_info()
        logger.info("Telegram webhook configured: %s (pending=%s, last_error=%s)", webhook_url, info.pending_update_count, info.last_error_message)
    else:
        logger.error("No PUBLIC_BOT_URL or RENDER_EXTERNAL_URL; Telegram commands cannot arrive until a webhook URL is configured")
    yield
    await bot.session.close()


app = FastAPI(title="Telegram Autotune Bot", lifespan=lifespan)


@app.get("/")
async def root():
    return {"service": "telegram-autotune-bot", "status": "ok"}


@app.head("/")
async def root_head():
    return None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.head("/health")
async def health_head():
    return None


@app.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != settings.webhook_secret:
        raise HTTPException(status_code=404)
    update = await request.json()
    await dp.feed_raw_update(bot, update)
    return {"ok": True}

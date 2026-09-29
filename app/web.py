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
    for suffix in (f"/telegram/webhook/{settings.webhook_secret}", "/telegram/webhook"):
        if public_url.endswith(suffix):
            public_url = public_url[: -len(suffix)]
            break
    if public_url:
        webhook_url = f"{public_url}/telegram/webhook"
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


async def _handle_telegram_webhook(request: Request, path_secret: str | None = None):
    header_secret = request.headers.get("x-telegram-bot-api-secret-token")
    if path_secret and path_secret != settings.webhook_secret:
        raise HTTPException(status_code=404)
    if not path_secret and header_secret != settings.webhook_secret:
        raise HTTPException(status_code=404)
    update = await request.json()
    await dp.feed_raw_update(bot, update)
    return {"ok": True}


@app.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    return await _handle_telegram_webhook(request, secret)


@app.post("/telegram/webhook")
async def telegram_webhook_header(request: Request):
    return await _handle_telegram_webhook(request)


@app.get("/telegram/webhook/status")
async def webhook_status():
    info = await bot.get_webhook_info()
    return {
        "url": info.url,
        "expected_url_suffix": "/telegram/webhook",
        "pending_update_count": info.pending_update_count,
        "last_error_message": info.last_error_message,
        "last_error_date": info.last_error_date,
    }

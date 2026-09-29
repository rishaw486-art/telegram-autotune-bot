from contextlib import asynccontextmanager

from aiogram import Bot
from fastapi import FastAPI, Header, HTTPException, Request

from .bot import build_dispatcher
from .config import settings
from .db import init_db

bot = Bot(settings.telegram_bot_token)
dp = build_dispatcher()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    if settings.public_bot_url:
        await bot.set_webhook(f"{settings.public_bot_url.rstrip('/')}/telegram/webhook/{settings.webhook_secret}", drop_pending_updates=False)
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

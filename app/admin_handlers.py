from __future__ import annotations

import csv
import io

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .models import ActivityLog, User

router = Router()


def owner(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == settings.owner_telegram_id)


@router.message(Command("message"))
async def message_user(message: Message, bot: Bot):
    if not owner(message): return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3: return await message.answer("Usage: /message TELEGRAM_ID text")
    await bot.send_message(int(parts[1]), parts[2])
    await message.answer("Message sent.")


@router.message(Command("broadcast"))
async def broadcast(message: Message, bot: Bot):
    if not owner(message): return
    text = (message.text or "").partition(" ")[2].strip()
    if not text: return await message.answer("Usage: /broadcast text")
    async with SessionLocal() as session:
        users = (await session.execute(select(User.telegram_id))).scalars().all()
    sent = 0
    for telegram_id in users:
        try:
            await bot.send_message(telegram_id, text)
            sent += 1
        except Exception:
            continue
    await message.answer(f"Broadcast sent to {sent} users.")


@router.message(Command("premium"))
async def premium(message: Message):
    if not owner(message): return
    parts = (message.text or "").split()
    if len(parts) < 2: return await message.answer("Usage: /premium TELEGRAM_ID")
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == int(parts[1])))).scalar_one_or_none()
        if not user: return await message.answer("User not found")
        user.is_premium = True
        user.paid_credits = max(user.paid_credits, 60)
        session.add(ActivityLog(user_id=user.id, event="admin_premium_grant"))
        await session.commit()
    await message.answer("Premium access granted with 60 credits.")


@router.message(Command("export_db"))
async def export_db(message: Message):
    if not owner(message): return
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["telegram_id", "username", "first_name", "is_owner", "is_premium", "free_credits", "paid_credits", "referral_credits", "created_at"])
    async with SessionLocal() as session:
        users = (await session.execute(select(User).order_by(User.id))).scalars().all()
        for user in users:
            writer.writerow([user.telegram_id, user.username or "", user.first_name or "", user.is_owner, user.is_premium, user.free_credits, user.paid_credits, user.referral_credits, user.created_at.isoformat() if user.created_at else ""])
    await message.answer_document(BufferedInputFile(output.getvalue().encode(), filename="users-export.csv"))


@router.message(lambda message: bool(message.document and message.caption == "/import_db"))
async def import_db(message: Message, bot: Bot):
    if not owner(message): return
    stream = io.BytesIO()
    await bot.download(message.document, destination=stream)
    stream.seek(0)
    rows = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8"))
    imported = 0
    async with SessionLocal() as session:
        for row in rows:
            telegram_id = int(row["telegram_id"])
            user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not user:
                user = User(telegram_id=telegram_id)
                session.add(user)
            user.username = row.get("username") or None
            user.first_name = row.get("first_name") or None
            user.is_owner = row.get("is_owner", "False").lower() == "true"
            user.is_premium = row.get("is_premium", "False").lower() == "true"
            user.free_credits = int(row.get("free_credits", 0))
            user.paid_credits = int(row.get("paid_credits", 0))
            user.referral_credits = int(row.get("referral_credits", 0))
            imported += 1
        await session.commit()
    await message.answer(f"Imported {imported} users. Existing users were updated.")

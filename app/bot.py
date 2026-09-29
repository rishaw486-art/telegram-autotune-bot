from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, LabeledPrice, PreCheckoutQuery
from sqlalchemy import func, select

from .config import settings
from .db import SessionLocal
from .models import ActivityLog, JobMode, JobStatus, MusicTrack, Payment, ProcessingJob, Referral, User

router = Router()


def menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Use my instrumental", callback_data="mode:upload")],
        [InlineKeyboardButton(text="Choose built-in music", callback_data="mode:library")],
        [InlineKeyboardButton(text="Buy 1 song — 10 Stars", callback_data="buy:single")],
        [InlineKeyboardButton(text="Buy 60 songs — 250 Stars", callback_data="buy:pack")],
        [InlineKeyboardButton(text="My credits", callback_data="credits")],
    ])


def mode_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Natural autotune", callback_data="tune:natural")],
        [InlineKeyboardButton(text="Strong autotune", callback_data="tune:strong")],
    ])


async def get_or_create_user(tg_user, referrer_tg_id: int | None = None) -> User:
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == tg_user.id))).scalar_one_or_none()
        if not user:
            referrer = None
            if referrer_tg_id and referrer_tg_id != tg_user.id:
                referrer = (await session.execute(select(User).where(User.telegram_id == referrer_tg_id))).scalar_one_or_none()
            user = User(telegram_id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name,
                        is_owner=tg_user.id == settings.owner_telegram_id, referred_by_id=referrer.id if referrer else None)
            session.add(user)
            await session.flush()
            if referrer:
                referrer.referral_credits += 1
                session.add(Referral(referrer_id=referrer.id, referred_user_id=user.id))
            session.add(ActivityLog(user_id=user.id, event="started", details=json.dumps({"referrer": referrer_tg_id})))
            await session.commit()
        else:
            user.username, user.first_name = tg_user.username, tg_user.first_name
            await session.commit()
        return user


async def credits_text(user: User) -> str:
    if user.is_owner:
        return "Owner access: unlimited songs."
    return f"Free: {user.free_credits} | Referral: {user.referral_credits} | Paid: {user.paid_credits}"


@router.message(CommandStart())
async def start(message: Message, bot: Bot) -> None:
    arg = (message.text or "").split(maxsplit=1)
    referrer = int(arg[1].replace("ref_", "")) if len(arg) > 1 and arg[1].replace("ref_", "").isdigit() else None
    user = await get_or_create_user(message.from_user, referrer)
    await message.answer("Welcome. Send a vocal recording to begin, or choose an option below.\n\n" + await credits_text(user), reply_markup=menu())


@router.callback_query(F.data == "credits")
async def credits(call: CallbackQuery) -> None:
    user = await get_or_create_user(call.from_user)
    await call.message.answer(await credits_text(user), reply_markup=menu())
    await call.answer()


@router.callback_query(F.data.startswith("mode:"))
async def choose_input(call: CallbackQuery) -> None:
    input_mode = call.data.split(":", 1)[1]
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == call.from_user.id))).scalar_one()
        user.pending_input_mode = input_mode
        await session.commit()
    await call.message.answer("Send your vocal recording as a voice message or audio file. Then I will ask for the autotune style." if input_mode == "upload" else "Send your vocal recording and I will let you choose one of the built-in instrumentals.", reply_markup=mode_menu())
    await call.answer()


@router.callback_query(F.data.startswith("tune:"))
async def choose_tune(call: CallbackQuery) -> None:
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == call.from_user.id))).scalar_one()
        user.pending_mode = JobMode(call.data.split(":", 1)[1])
        await session.commit()
    await call.message.answer("Send the vocal recording now. I will use the selected style: " + call.data.split(":", 1)[1])
    await call.answer()


async def enqueue(message: Message, file_id: str, mode: JobMode = JobMode.natural) -> None:
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one()
        active = (await session.execute(select(ProcessingJob).where(ProcessingJob.user_id == user.id, ProcessingJob.status.in_([JobStatus.queued, JobStatus.processing])))).scalar_one_or_none()
        if active:
            await message.answer("You already have a song processing. Please wait for it to finish.")
            return
        selected_mode = user.pending_mode or mode
        if user.pending_vocal_file_id is None:
            user.pending_vocal_file_id = file_id
            if user.pending_input_mode == "upload":
                await session.commit()
                await message.answer("Vocal received. Now send the instrumental audio file.")
                return
            await session.commit()
            tracks = (await session.execute(select(MusicTrack).where(MusicTrack.active == True).limit(8))).scalars().all()
            buttons = [[InlineKeyboardButton(text=t.title, callback_data=f"track:{t.id}")] for t in tracks]
            await message.answer("Vocal received. Choose a built-in instrumental.", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons or [[InlineKeyboardButton(text="No tracks installed", callback_data="credits")]]))
            return
        vocal_file_id = user.pending_vocal_file_id
        user.pending_vocal_file_id = None
        if not user.is_owner:
            if user.free_credits > 0:
                user.free_credits -= 1
                credit_source = "free"
            elif user.referral_credits > 0:
                user.referral_credits -= 1
                credit_source = "referral"
            elif user.paid_credits > 0:
                user.paid_credits -= 1
                credit_source = "paid"
            else:
                await message.answer("You have no song credits. Choose a payment option below.", reply_markup=menu())
                return
        else:
            credit_source = "owner"
        session.add(ProcessingJob(user_id=user.id, vocal_file_id=vocal_file_id, instrumental_file_id=file_id, mode=selected_mode, credit_source=credit_source))
        session.add(ActivityLog(user_id=user.id, event="song_queued"))
        await session.commit()
    await message.answer("Recording received and queued. I will send the finished song here when it is ready.")


@router.callback_query(F.data.startswith("track:"))
async def choose_track(call: CallbackQuery) -> None:
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == call.from_user.id))).scalar_one()
        track_id = int(call.data.split(":", 1)[1])
        track = (await session.execute(select(MusicTrack).where(MusicTrack.id == track_id, MusicTrack.active == True))).scalar_one_or_none()
        if not track or not user.pending_vocal_file_id:
            await call.answer("This track is unavailable", show_alert=True)
            return
        if not user.is_owner:
            if user.free_credits > 0:
                user.free_credits -= 1; source = "free"
            elif user.referral_credits > 0:
                user.referral_credits -= 1; source = "referral"
            elif user.paid_credits > 0:
                user.paid_credits -= 1; source = "paid"
            else:
                await call.message.answer("You have no song credits. Choose a payment option below.", reply_markup=menu())
                await call.answer(); return
        else:
            source = "owner"
        session.add(ProcessingJob(user_id=user.id, vocal_file_id=user.pending_vocal_file_id, library_track_id=track.id, mode=user.pending_mode or JobMode.natural, credit_source=source))
        user.pending_vocal_file_id = None
        await session.commit()
    await call.message.answer(f"Queued with {track.title}. I will send the finished song when ready.")
    await call.answer()


@router.message(F.voice)
async def voice(message: Message) -> None:
    await enqueue(message, message.voice.file_id)


@router.message(F.audio)
async def audio(message: Message) -> None:
    await enqueue(message, message.audio.file_id)


@router.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery, bot: Bot) -> None:
    product = call.data.split(":", 1)[1]
    stars, label = (10, "1 song") if product == "single" else (250, "60 songs")
    await bot.send_invoice(chat_id=call.from_user.id, title=label, description=f"Autotune processing credits: {label}", payload=f"autotune:{product}:{call.from_user.id}", currency="XTR", prices=[LabeledPrice(label=label, amount=stars)])
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, bot: Bot) -> None:
    await bot.answer_pre_checkout_query(query.id, ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    payment = message.successful_payment
    product = payment.invoice_payload.split(":")[1]
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one()
        exists = (await session.execute(select(Payment).where(Payment.telegram_payment_charge_id == payment.telegram_payment_charge_id))).scalar_one_or_none()
        if not exists:
            if product == "single":
                user.paid_credits += 1
            else:
                user.paid_credits += 60
            session.add(Payment(user_id=user.id, telegram_payment_charge_id=payment.telegram_payment_charge_id, invoice_payload=payment.invoice_payload, stars=payment.total_amount, product=product))
            session.add(ActivityLog(user_id=user.id, event="payment", details=payment.invoice_payload))
            await session.commit()
    await message.answer(f"Payment received. {await credits_text(user)}", reply_markup=menu())


async def owner_only(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == settings.owner_telegram_id)


@router.message(Command("status"))
async def status(message: Message) -> None:
    if not await owner_only(message): return
    async with SessionLocal() as session:
        users = (await session.execute(select(func.count(User.id)))).scalar_one()
        jobs = (await session.execute(select(func.count(ProcessingJob.id)).where(ProcessingJob.status == JobStatus.queued))).scalar_one()
        payments = (await session.execute(select(func.count(Payment.id)))).scalar_one()
    await message.answer(f"Users: {users}\nQueued jobs: {jobs}\nPayments: {payments}")


@router.message(Command("grant"))
async def grant(message: Message) -> None:
    if not await owner_only(message): return
    parts = (message.text or "").split()
    if len(parts) < 3: return await message.answer("Usage: /grant TELEGRAM_ID CREDITS")
    async with SessionLocal() as session:
        user = (await session.execute(select(User).where(User.telegram_id == int(parts[1])))).scalar_one_or_none()
        if not user: return await message.answer("User not found")
        user.paid_credits += int(parts[2])
        user.is_premium = True
        await session.commit()
    await message.answer("Access granted.")


@router.message(Command("referral"))
async def referral(message: Message) -> None:
    await message.answer(f"Your referral link:\nhttps://t.me/{(await message.bot.get_me()).username}?start=ref_{message.from_user.id}")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    from .admin_handlers import router as admin_router
    dp.include_router(admin_router)
    return dp

from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from sqlalchemy import select, update

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import ActivityLog, JobStatus, MusicTrack, ProcessingJob, User
from audio.pipeline import process_async


async def claim_job():
    async with SessionLocal() as session:
        async with session.begin():
            job = (await session.execute(select(ProcessingJob).where(ProcessingJob.status == JobStatus.queued).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
            if not job:
                return None
            job.status = JobStatus.processing
            job.started_at = datetime.now(timezone.utc)
            await session.flush()
            return job.id


async def run_job(bot: Bot, job_id: int) -> None:
    work_dir = Path(tempfile.mkdtemp(prefix=f"job-{job_id}-", dir=settings.temp_root))
    try:
        async with SessionLocal() as session:
            job = (await session.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))).scalar_one()
            user = (await session.execute(select(User).where(User.id == job.user_id))).scalar_one()
            track = None
            if job.library_track_id:
                track = (await session.execute(select(MusicTrack).where(MusicTrack.id == job.library_track_id))).scalar_one_or_none()
            vocal_info = await bot.get_file(job.vocal_file_id)
            vocal_path = work_dir / "vocal-input"
            await bot.download_file(vocal_info.file_path, vocal_path)
            instrumental_path = None
            if job.instrumental_file_id:
                inst_info = await bot.get_file(job.instrumental_file_id)
                instrumental_path = work_dir / "instrumental-input"
                await bot.download_file(inst_info.file_path, instrumental_path)
            elif track:
                instrumental_path = Path(track.local_path)
            output = await process_async(vocal_path, instrumental_path, work_dir, job.mode.value)
            sent = await bot.send_audio(user.telegram_id, FSInputFile(output), caption=f"Your {job.mode.value} autotune song is ready.")
            result_file_id = sent.audio.file_id if sent.audio else None
            job.status = JobStatus.completed
            job.finished_at = datetime.now(timezone.utc)
            job.telegram_result_file_id = result_file_id
            session.add(ActivityLog(user_id=user.id, event="song_completed"))
            await session.commit()
    except Exception as exc:
        async with SessionLocal() as session:
            job = (await session.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))).scalar_one()
            job.status = JobStatus.failed
            job.finished_at = datetime.now(timezone.utc)
            job.error_message = str(exc)[-4000:]
            session.add(ActivityLog(user_id=job.user_id, event="song_failed", details=str(exc)[-1000:]))
            await session.commit()
        try:
            async with SessionLocal() as session:
                user = (await session.execute(select(User).join(ProcessingJob, ProcessingJob.user_id == User.id).where(ProcessingJob.id == job_id))).scalar_one()
                job = (await session.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))).scalar_one()
                if not user.is_owner and job.credit_source == "paid":
                    user.paid_credits += 1
                elif not user.is_owner and job.credit_source == "free":
                    user.free_credits += 1
                elif not user.is_owner and job.credit_source == "referral":
                    user.referral_credits += 1
                    await session.commit()
                await bot.send_message(user.telegram_id, "Processing failed, so your credit was restored. Please try a shorter or cleaner recording.")
        except Exception:
            pass
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def main():
    Path(settings.temp_root).mkdir(parents=True, exist_ok=True)
    await init_db()
    bot = Bot(settings.telegram_bot_token)
    try:
        while True:
            job_id = await claim_job()
            if job_id:
                await run_job(bot, job_id)
            else:
                await asyncio.sleep(settings.worker_poll_seconds)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

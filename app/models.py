from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobMode(str, enum.Enum):
    natural = "natural"
    strong = "strong"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    first_name: Mapped[Optional[str]] = mapped_column(String(255))
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    premium_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    free_credits: Mapped[int] = mapped_column(Integer, default=1)
    paid_credits: Mapped[int] = mapped_column(Integer, default=0)
    referral_credits: Mapped[int] = mapped_column(Integer, default=0)
    pending_vocal_file_id: Mapped[Optional[str]] = mapped_column(String(255))
    pending_input_mode: Mapped[Optional[str]] = mapped_column(String(30))
    pending_mode: Mapped[Optional[JobMode]] = mapped_column(Enum(JobMode))
    referred_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    vocal_file_id: Mapped[str] = mapped_column(String(255))
    instrumental_file_id: Mapped[Optional[str]] = mapped_column(String(255))
    library_track_id: Mapped[Optional[int]] = mapped_column(ForeignKey("music_tracks.id"))
    mode: Mapped[JobMode] = mapped_column(Enum(JobMode), default=JobMode.natural)
    credit_source: Mapped[str] = mapped_column(String(30), default="free")
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    telegram_result_file_id: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(255), unique=True)
    invoice_payload: Mapped[str] = mapped_column(String(255))
    stars: Mapped[int] = mapped_column(Integer)
    product: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Referral(Base):
    __tablename__ = "referrals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    rewarded: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MusicTrack(Base):
    __tablename__ = "music_tracks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    genre: Mapped[Optional[str]] = mapped_column(String(100))
    mood: Mapped[Optional[str]] = mapped_column(String(100))
    bpm: Mapped[Optional[int]] = mapped_column(Integer)
    musical_key: Mapped[Optional[str]] = mapped_column(String(30))
    local_path: Mapped[str] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    event: Mapped[str] = mapped_column(String(100), index=True)
    details: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

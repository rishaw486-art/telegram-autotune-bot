# Telegram Autotune Bot

A Render/Neon-ready Telegram bot for singers. Users upload vocals, optionally upload an instrumental or choose a built-in track, select Natural or Strong tuning, and receive a mixed MP3.

## Features

- One free song for every new user
- 10 Telegram Stars for one song
- 250 Telegram Stars for a manually purchased 60-song pack
- Referral link gives the referrer one extra processing credit
- Telegram Stars payment verification and idempotency
- Owner: status, message, broadcast, premium grant, credit grant, CSV export
- PostgreSQL-backed queue and activity logs
- FFmpeg + optional Demucs vocal separation
- CPU-safe pitch correction baseline, vocal compression, reverb, loudness normalization
- Temporary audio files deleted after each job

## Local setup

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg libsndfile1
python3.11 -m venv .venv
. .venv/bin/activate
pip install .
cp .env.example .env
uvicorn app.web:app --reload --port 10000
# separate terminal
python worker.py
```

Set `DATABASE_URL` to a Neon connection string using the `postgresql+asyncpg://` scheme. For Neon, keep `?ssl=require` in the URL.

## Render deployment

Create two services from the repository using `render.yaml`:

1. Web Service: runs `uvicorn app.web:app` and receives the Telegram webhook.
2. Background Worker: runs `python worker.py` and processes queued audio.

Set the same `TELEGRAM_BOT_TOKEN`, `OWNER_TELEGRAM_ID`, `DATABASE_URL`, and `WEBHOOK_SECRET` on both services. Set `PUBLIC_BOT_URL` on the web service to its HTTPS Render URL.

The bot automatically calls `setWebhook` on startup. Telegram requires a public HTTPS webhook endpoint.

## Owner commands

```text
/status
/message TELEGRAM_ID text
/broadcast text
/premium TELEGRAM_ID
/grant TELEGRAM_ID CREDITS
/export_db
/referral
```

## Built-in music

Add licensed/original tracks to `music/` and insert metadata into `music_tracks`:

```sql
INSERT INTO music_tracks(title, genre, mood, bpm, musical_key, local_path, active)
VALUES ('Demo Beat', 'pop', 'upbeat', 100, 'C', './music/demo-beat.mp3', true);
```

The track must be included in the worker image and referenced by the same path.

## Payment and legal operations

This bot sells digital processing services, so invoices use Telegram Stars (`XTR`). The payment handler grants credits only after `successful_payment`, not merely after pre-checkout. Add `/terms` and `/support` pages before public launch, and keep records of Telegram payment charge IDs for refunds/support.

## Production notes

- Do not use Render Free for production: free services sleep and free Render Postgres expires after 30 days.
- Do not rely on self-pinging to keep a free service alive.
- User recordings are downloaded from Telegram just before processing and deleted from `/tmp` afterward.
- Telegram's standard Bot API download limit is 20 MB; enforce short recordings in a later validation pass.
- The included tuner is a CPU-safe MVP baseline. For studio-grade note-by-note correction, replace `pitch_correct` with a neural or Rubber Band-based tuner after benchmarking on your singers' recordings.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install . && pip install demucs
COPY app ./app
COPY audio ./audio
COPY worker.py render.yaml .env.example ./
COPY music ./music
RUN mkdir -p /tmp/autotune
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.web:app --host 0.0.0.0 --port ${PORT:-10000}"]

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    python -m playwright install --with-deps chromium

COPY agent ./agent
COPY backend ./backend

RUN mkdir -p /app/data

EXPOSE 6868

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "6868", "--workers", "1"]

# ---------- web build ----------
FROM node:20-alpine AS web
WORKDIR /w/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# vite writes to ../static (see vite.config.ts), i.e. /w/static
RUN npm run build

# ---------- python runtime ----------
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Tehran \
    DATA_DIR=/app/data \
    CATALOG_PATH=/app/data/catalog.db \
    MARKETS_PATH=/app/data/markets.json \
    CHECKPOINT_PATH=/tmp/checkpoints.db \
    STATIC_DIR=/app/static
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend
COPY data/ ./data
COPY --from=web /w/static ./static

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

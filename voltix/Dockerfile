# Voltix — production image (SPA + FastAPI + SQLite)
FROM node:20-bookworm-slim AS frontend
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY server ./server
COPY --from=frontend /web/dist ./dist

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

WORKDIR /app/server
# Persist SQLite under /app/server/data (attach a Railway volume here)
CMD ["sh", "-c", "mkdir -p /app/server/data && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]

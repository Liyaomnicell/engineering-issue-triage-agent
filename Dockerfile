FROM node:24-bookworm-slim AS frontend
WORKDIR /build
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
COPY frontend/pnpm-workspace.yaml* ./
RUN corepack pnpm install --frozen-lockfile
COPY frontend/ ./
RUN corepack pnpm build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TRIAGE_HOST=0.0.0.0
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py postgres_store.py triage.py migrate_sqlite.py ./
COPY migrations ./migrations
COPY --from=frontend /build/dist/frontend/browser ./frontend/dist/frontend/browser
RUN useradd --create-home --uid 10001 triage && mkdir -p /app/.triage /app/escalations /app/source-colortouch && chown -R triage:triage /app
USER triage
EXPOSE 8765
CMD ["python", "app.py"]

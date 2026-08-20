FROM python:3.11-slim AS base

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
COPY shared/ ./shared/
COPY alembic.ini ./
COPY alembic/ ./alembic/

FROM base AS gateway
COPY gateway/ ./gateway/
CMD ["python", "-m", "gateway.main"]

FROM base AS director
COPY live/director/ ./live/director/
COPY live/__init__.py ./live/__init__.py
CMD ["python", "-m", "live.director.main"]

FROM base AS ai-agent
COPY agent/ ./agent/
COPY ai/__init__.py ./ai/__init__.py
COPY ai/asr/ ./ai/asr/
COPY ai/llm/ ./ai/llm/
COPY ai/tts/ ./ai/tts/
COPY ai/vision/ ./ai/vision/
CMD ["python", "-m", "agent.main"]

FROM base AS gptsovits
COPY ai/gptsovits/ ./ai/gptsovits/
COPY ai/__init__.py ./ai/__init__.py
CMD ["python", "-m", "ai.gptsovits.main"]

FROM base AS avatar
COPY live/avatar/ ./live/avatar/
COPY live/__init__.py ./live/__init__.py
CMD ["python", "-m", "live.avatar.main"]

FROM base AS stream
COPY live/stream/ ./live/stream/
COPY live/__init__.py ./live/__init__.py
CMD ["python", "-m", "live.stream.main"]

FROM base AS extension-host
COPY extensions/host/ ./extensions/host/
COPY extensions/__init__.py ./extensions/__init__.py
CMD ["python", "-m", "extensions.host.main"]

FROM base AS mcp
COPY extensions/mcp/ ./extensions/mcp/
COPY extensions/__init__.py ./extensions/__init__.py
CMD ["python", "-m", "extensions.mcp.main"]

FROM base AS memory
COPY memory/ ./memory/
COPY ai/__init__.py ./ai/__init__.py
COPY ai/llm/ ./ai/llm/
CMD ["python", "-m", "memory.main"]

FROM node:22-alpine AS ops-panel-frontend
WORKDIR /frontend
COPY ops/panel/frontend/package.json ops/panel/frontend/package-lock.json ./
RUN npm ci
COPY ops/panel/frontend/ ./
RUN npm run build

FROM base AS ops-panel
COPY ops/ ./ops/
COPY --from=ops-panel-frontend /frontend/dist ./ops/panel/frontend/dist
CMD ["python", "-m", "ops.panel.backend.main"]

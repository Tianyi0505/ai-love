FROM python:3.11-slim AS base

WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt \
    && pip install --no-cache-dir --no-deps .
COPY shared/ ./shared/
COPY alembic.ini ./
COPY alembic/ ./alembic/

FROM base AS gateway
COPY gateway/ ./gateway/
CMD ["python", "-m", "gateway.gateway_service"]

FROM base AS director
COPY live/director/ ./live/director/
COPY live/__init__.py ./live/__init__.py
CMD ["python", "-m", "live.director.director_service"]

FROM base AS ai-agent
COPY agent/ ./agent/
COPY ai/__init__.py ./ai/__init__.py
COPY ai/tts/ ./ai/tts/
COPY ai/vision/ ./ai/vision/
CMD ["python", "-m", "agent.ai_agent_service"]

FROM base AS gptsovits
COPY ai/gptsovits/ ./ai/gptsovits/
COPY ai/__init__.py ./ai/__init__.py
CMD ["python", "-m", "ai.gptsovits.gpt_sovits_service"]

FROM base AS live-edge
COPY live/ ./live/
CMD ["python", "-m", "live.edge_service"]

FROM base AS extension-host
COPY extensions/host/ ./extensions/host/
COPY extensions/__init__.py ./extensions/__init__.py
CMD ["python", "-m", "extensions.host.extension_host_service"]

FROM base AS mcp
COPY extensions/mcp/ ./extensions/mcp/
COPY extensions/__init__.py ./extensions/__init__.py
CMD ["python", "-m", "extensions.mcp.mcp_server"]

FROM base AS memory
COPY memory/ ./memory/
CMD ["python", "-m", "memory.memory_service"]

FROM node:22-alpine AS ops-panel-frontend
WORKDIR /frontend
COPY admin/console/frontend/package.json admin/console/frontend/package-lock.json ./
RUN npm ci
COPY admin/console/frontend/ ./
RUN npm run build

FROM base AS ops-panel
COPY admin/ ./admin/
COPY --from=ops-panel-frontend /frontend/dist ./admin/console/frontend/dist
CMD ["python", "-m", "admin.console.backend.main"]

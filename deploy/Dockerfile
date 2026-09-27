FROM python:3.11-slim AS base

WORKDIR /app
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps .
COPY shared/ ./shared/
COPY plugin_runtime/ ./plugin_runtime/
COPY plugins/ ./plugins/
COPY alembic.ini ./
COPY alembic/ ./alembic/

FROM base AS gateway
COPY gateway/ ./gateway/
CMD ["python", "-m", "plugin_runtime", "--role", "gateway"]

FROM base AS director
COPY live/director/ ./live/director/
COPY live/__init__.py ./live/__init__.py
CMD ["python", "-m", "plugin_runtime", "--role", "director"]

FROM base AS ai-agent
COPY agent/ ./agent/
COPY memory/ ./memory/
CMD ["python", "-m", "plugin_runtime", "--role", "ai-agent"]

FROM base AS gptsovits
COPY gptsovits/ ./gptsovits/
CMD ["python", "-m", "plugin_runtime", "--role", "gptsovits"]

FROM base AS live-edge
COPY live/ ./live/
CMD ["python", "-m", "plugin_runtime", "--role", "live-edge"]

FROM base AS extension-host
COPY extensions/host/ ./extensions/host/
COPY extensions/__init__.py ./extensions/__init__.py
CMD ["python", "-m", "plugin_runtime", "--role", "extension-host"]

FROM base AS mcp
COPY extensions/mcp/ ./extensions/mcp/
COPY extensions/__init__.py ./extensions/__init__.py
CMD ["python", "-m", "plugin_runtime", "--role", "mcp"]

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

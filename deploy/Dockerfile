FROM python:3.11-slim AS base

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
COPY shared/ ./shared/

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
COPY ai/vision/ ./ai/vision/
CMD ["python", "-m", "agent.main"]

FROM base AS tts
COPY ai/tts/ ./ai/tts/
COPY ai/__init__.py ./ai/__init__.py
CMD ["python", "-m", "ai.tts.main"]

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
CMD ["python", "-m", "memory.main"]

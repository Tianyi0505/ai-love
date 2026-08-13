FROM python:3.11-slim AS base

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
COPY shared/ ./shared/

FROM base AS gateway
COPY gateway/ ./gateway/
CMD ["python", "-m", "gateway.main"]

FROM base AS orchestrator
COPY services/orchestrator/ ./services/orchestrator/
CMD ["python", "-m", "services.orchestrator.main"]

FROM base AS ai-agent
COPY agent/ ./agent/
COPY ai/__init__.py ./ai/__init__.py
COPY ai/llm/ ./ai/llm/
COPY ai/vision/ ./ai/vision/
CMD ["python", "-m", "agent.main"]

FROM base AS tts
COPY ai/tts/ ./ai/tts/
COPY ai/__init__.py ./ai/__init__.py
CMD ["python", "-m", "ai.tts.main"]

FROM base AS avatar
COPY services/avatar/ ./services/avatar/
CMD ["python", "-m", "services.avatar.main"]

FROM base AS stream
COPY services/stream/ ./services/stream/
CMD ["python", "-m", "services.stream.main"]

FROM base AS extension-host
COPY extensions/host/ ./extensions/host/
COPY extensions/__init__.py ./extensions/__init__.py
CMD ["python", "-m", "extensions.host.main"]

FROM base AS mcp-weather
COPY services/mcp_weather/ ./services/mcp_weather/
CMD ["python", "-m", "services.mcp_weather.main"]

FROM base AS memory
COPY memory/ ./memory/
CMD ["python", "-m", "memory.main"]

FROM base AS music
COPY services/music/ ./services/music/
CMD ["python", "-m", "services.music.main"]

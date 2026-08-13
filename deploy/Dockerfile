FROM python:3.11-slim AS base

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
COPY shared/ ./shared/

FROM base AS gateway
COPY services/gateway/ ./services/gateway/
CMD ["python", "-m", "services.gateway.main"]

FROM base AS orchestrator
COPY services/orchestrator/ ./services/orchestrator/
CMD ["python", "-m", "services.orchestrator.main"]

FROM base AS ai-agent
COPY services/ai_agent/ ./services/ai_agent/
CMD ["python", "-m", "services.ai_agent.main"]

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
COPY services/extension_host/ ./services/extension_host/
CMD ["python", "-m", "services.extension_host.main"]

FROM base AS mcp-weather
COPY services/mcp_weather/ ./services/mcp_weather/
CMD ["python", "-m", "services.mcp_weather.main"]

FROM base AS memory
COPY services/memory/ ./services/memory/
CMD ["python", "-m", "services.memory.main"]

FROM base AS music
COPY services/music/ ./services/music/
CMD ["python", "-m", "services.music.main"]

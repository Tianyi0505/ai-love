FROM node:22-bookworm-slim

ENV DSH_HOME=/var/lib/ai-love-dsh \
    AILOVE_DSH_HOST=auto \
    AILOVE_WORKSPACE_DIRECTORY=/workspace

WORKDIR /app
COPY . .

WORKDIR /app/harness
RUN corepack enable \
    && corepack prepare pnpm@11.2.2 --activate \
    && pnpm install --prod --frozen-lockfile

WORKDIR /app
EXPOSE 3080 8090
CMD ["node", "harness/scripts/start.ts", "--no-open", "--port", "3080", "--trusted-host", "localhost:3080", "--trusted-host", "127.0.0.1:3080"]

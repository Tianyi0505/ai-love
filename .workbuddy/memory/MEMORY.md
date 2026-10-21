# 项目长期记忆

## 分支与发布约定

- 远程：`git@github.com:Tianyi0505/ai-love.git`，主干 `main`。
- 提交信息使用约定式提交（`feat|fix|docs|refactor|chore|test`）。
- 生产发布记录写在 `deploy/private/<主题>-<YYYYMMDD>/`（manifest / result / 快照 JSON）。
- 镜像标签惯例：`ailove/<service>:<主题>-<YYYYMMDD>` 或 `<服务>:asd-<短提交>-<日期>`，tag 里带短提交可反查代码版本。
- 合并到 main 时优先用独立 worktree（`D:/ai-love-worktrees/...`），避免打扰主工作区未提交的 live2d 开发。

## 生产环境

- 服务器：`root@106.55.16.95`（k3s 单节点 `ailove-core`，`--tls-san 106.55.16.95`），namespace `ailove`。
- 服务：ai-agent、gateway、director、live-edge、extension-host、gptsovits、mcp、ops-panel、nats、redis。无 live2d 部署。
- 服务器上 kubectl 为 `k3s kubectl`；6443 公网可达。
- 本地调试隧道：`deploy/private/local-debug-tunnel.ps1`，凭据在 `deploy/private/local-debug.env`（PG 15432 / Redis 16379 / NATS 14222）。

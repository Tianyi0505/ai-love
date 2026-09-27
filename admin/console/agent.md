### Agent System

**Ops Panel Service** (`admin/console/backend/main.py`, `admin/console/backend/app.py`):

- 进程入口是 `python -m admin.console.backend.main`；Uvicorn 承载 FastAPI 后端，并由同一进程在根路径提供已构建的前端静态资源。
- `create_app()` 是测试和运行时共用的应用工厂。lifespan 连接 PostgreSQL、Redis 与 Kubernetes 挂载配置，初始化 Agent 定义、登录凭据和只读观测 reader，并在退出时统一关闭依赖。
- 依赖不可用统一转换为 503；业务认证错误由对应 router 处理。不要把数据库、Redis 或 Kubernetes 挂载配置 异常伪装成空数据。

**Authentication** (`admin/console/backend/auth/`):

- 登录凭据存储在 PostgreSQL，密码使用 Argon2；Redis 只保存 session。首次启动创建凭据，发现旧格式时迁移为 Argon2。
- 更新凭据必须校验当前密码并使既有 session 失效。鉴权 cookie 和 session 逻辑集中在 auth 模块，不在观测接口重复实现。

**Observability** (`admin/console/backend/observability/`):

- Personality 从 Kubernetes 挂载配置 Agent 定义读取；self/people memory 从 PostgreSQL 读取。面板是观测入口，不直接调用 Agent 或 Memory 的内部对象。
- Kubernetes Dashboard 快捷入口使用 SSO helper；token、共享密钥和 service-account 文件内容不得写入响应、日志或前端 bundle。

**Runtime Configuration** (`PanelConfig`):

- 配置使用 `PANEL_` 前缀；Kubernetes 挂载配置 auth token、Redis URL/密码通过显式 alias 读取。
- 关键项包括面板端口、目标 `ai_id`、初始凭据、NapCat/Kubernetes 挂载配置/Kubernetes 地址、session 依赖和 people memory 列表上限。
- 前端源码位于 `admin/console/frontend/`；容器构建先执行 `npm ci` / `npm run build`，再把 `dist` 复制进后端镜像。

# 管理控制台运行边界


现有入口为 `python -m admin.console.backend.main`。Uvicorn 承载 FastAPI，根路径提供已构建前端。create_app() 是测试与运行时共用工厂。

## 管理结果

- 应用生命周期拥有 PostgreSQL、Redis、人物定义、凭据和观测 reader。
- 依赖状态通过 503 等真实接口状态表达，认证结果由对应 router 提供。
- 登录凭据保存在 PostgreSQL，密码使用 Argon2，Redis 保存 session。
- 凭据更新资格包含当前密码校验，成功更新对应新的会话授权状态。
- 鉴权 cookie 与 session 由 auth 模块统一管理。
- 人格观测来自 Kubernetes 人物定义，self/people memory 来自 PostgreSQL。
- Kubernetes Dashboard 快捷入口采用 SSO helper，token、共享密钥和 service-account 内容保存在服务端受限资源。

## 配置与产物

PanelConfig 使用 PANEL_ 前缀，连接参数通过显式 alias 提供。配置包含端口、目标 ai_id、初始凭据、平台地址、session 依赖与列表上限。

前端源码位于 admin/console/frontend，生产静态产物为 dist，构建入口为 npm ci 和 npm run build，后端镜像包含该产物。

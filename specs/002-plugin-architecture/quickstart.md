# Quickstart: 本地插件化验收

本文件是**实施后**运行指南；新增脚本/模块目前尚未实现，本次仅验证文档和任务结构。不得把命令存在于文档当作已运行成功。具体入口及 schema 见 [contracts/management.md](contracts/management.md)。

## 1. 前置环境

- Python 3.11、PowerShell、Docker、Node/npm；项目依赖安装到本地开发环境。固定模型响应与脱敏输入，不连接生产账号。
- 仅使用新建 `deployment/local/compose.plugins.yml`；服务为本地 PostgreSQL、NATS JetStream、Redis、Nacos 和模拟平台，所有端口绑定环回；独立 Compose project `ailove-plugin-test`。
- `prepare-local.ps1` 生成测试配置/凭据，校验测试库名以 `_test` 结尾及地址为 localhost/127.0.0.1/::1；禁止继承生产连接。凭据文件权限受限，输出只含路径。
- `build-artifacts.ps1` 准备核心/平台/宿主及 31 插件产物，另收集依赖 wheelhouse；验收安装阶段只使用 `--no-index`，缺依赖明确失败。

## 2. 现有回归命令（需要相应测试依赖）

```powershell
Set-Location D:\ai-love
.\.venv\Scripts\python.exe -m pytest tests/test_model_failover.py tests/test_live_edge_service.py -q
npm --prefix admin/console/frontend run build
```

私聊数据库测试在第 3 节准备本地环境后执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_private_reply_flow.py tests/test_social_delivery_recovery.py tests/test_memory_state.py -q
```

现有 fixture 仍部分模拟总线和 runtime，不覆盖正式插件装载；现有私聊负载不符合新规格负载，不能替代第 5 节。

## 3. 新增环境与独立产物验证（任务实现后）

```powershell
Set-Location D:\ai-love
& ./scripts/plugins/prepare-local.ps1 -OutputDirectory ./output/plugin-architecture/local
docker compose -p ailove-plugin-test -f deployment/local/compose.plugins.yml --env-file output/plugin-architecture/local/.env up -d --wait
. ./output/plugin-architecture/local/test-env.ps1
& ./scripts/plugins/build-artifacts.ps1 -OutputDirectory ./output/plugin-architecture/artifacts
& ./scripts/plugins/test-installed-artifacts.ps1 -ArtifactDirectory ./output/plugin-architecture/artifacts
```

prepare-local 只生成本地 fixture；Nacos 测试初始化由测试启动器写入该本地实例，绝不调用生产初始化脚本。test-env.ps1 仅设置本地测试连接；生成脚本前校验固定键/环回目标，不插入未经校验的可执行输入。

期望：从仓库外临时 cwd、无 PYTHONPATH/可编辑安装/源码挂载启动正式宿主；核心无插件时管理鉴权、诊断可用，业务 readiness 缺失。wheel 中有代码、清单和 schema；core 依赖闭包没有供应商或业务插件。

## 4. MVP 与全部插件的公开入口场景

```powershell
& ./scripts/plugins/test-conformance.ps1 -Catalog ./deployment/manifests/plugin-catalog.json -Plugin speech-gptsovits-client -Cycles 100
& ./scripts/plugins/test-conformance.ps1 -Catalog ./deployment/manifests/plugin-catalog.json -All -Cycles 100
.\.venv\Scripts\python.exe -m pytest tests/plugin_contracts tests/plugin_integration tests/plugin_recovery tests/plugin_architecture -q
```

conformance 脚本启动正式宿主、登录本地管理面，经 API/CLI 执行操作，并从插件业务入口调用。依次验证添加、启用、停用、替换、升级、物理移除；为每种能力提供另一个遵循当前契约的验收实现，明确其测试用途。原插件与核心产物摘要前后比较，无关能力运行控制组流量。

MVP：speech 客户端连接本地模拟语音服务，经正式 synthesize 能力返回音频引用；停用拒绝新调用，资源归零；物理移除后零插件宿主仍可运行。全部插件：QQ 走实际 WS+HTTP 协议模拟，Memory 走真实 JetStream 持久入口及调度，其余按能力公开入口验证；未接通的音乐/舞台执行明确 unsupported。

## 5. 恢复与负载

```powershell
& ./scripts/plugins/test-recovery.ps1 -Catalog ./deployment/manifests/plugin-catalog.json -OutputDirectory ./output/plugin-architecture/recovery
& ./scripts/plugins/test-load.ps1 -Persons 2 -Conversations 20 -EventsPerSecond 10 -DurationSeconds 900 -OutputDirectory ./output/plugin-architecture/load
npm --prefix admin/console/frontend run test:plugins
```

- 恢复：对每生命周期阶段/切换提交前后注入错误及退出，覆盖数据库+KV 联合恢复、旧代次写入拒绝、状态导入失败、发送确认丢失、后台任务停止和候选激活闸门。
- 正常模型响应与有故障场景分开测量；相同脱敏输入和固定响应集，单活动路径产生模拟副作用，控制组不受影响。
- 指标：P95 增量 ≤max(旧基线×10%,20ms)，调用/token 不增加，非注入错误为 0；恢复≤5 分钟，已确认持久状态丢失为 0；100 次启停无残留。
- 前端：固定静态构建中安装/移除贡献，导航刷新、旧页面撤销、鉴权和查询授权有效；测试脚本需任务新增，当前 package.json 尚无此入口。

## 6. 证据与停止

保存机器/依赖信息、核心/插件摘要、操作 ID、配置修订、状态水位、模拟边界、逐插件六项结果和 40 项验收证据到 `output/plugin-architecture/`。环境缺失或跳过的检查不得标通过；生产平台验证需单列后续授权范围。

```powershell
docker compose -p ailove-plugin-test -f deployment/local/compose.plugins.yml --env-file output/plugin-architecture/local/.env stop
```

停止仅针对本地测试 project，不删除数据卷或任何用户/生产数据。临时目录清理由脚本验证绝对路径及自身资源归属后执行，禁止按通配符清空工作区。

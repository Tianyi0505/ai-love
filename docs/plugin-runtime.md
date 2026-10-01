# AI-Love 插件运行时

业务能力由本地 `plugin.json` 清单、稳定契约和统一宿主管理。基础目录包含 17 个插件、7 种宿主；structured-output 的结果工具见 [人设与 MCP 结果](persona-memory-and-mcp-output.md)。管理页为 `#/plugins`（能力工坊）。

## 架构结果

| 边界 | 职责 |
| --- | --- |
| plugin_runtime | 发现、契约、能力解析、生命周期与控制面 |
| plugins/components.py | 现有服务适配 |
| 资源作用域 | 订阅、后台任务、定时器、配置监听、HTTP 与清理回调 |
| 工厂注册表 | 模型、渠道、语音的清单配置与 Python entry points |
| SQLite WAL | 期望状态、修订号与幂等操作记录 |
| 管理外壳 | 登录、同源检查、预检与持久操作查询 |

`context.require()` 返回声明能力，`context.provide()` 导出能力。单宿主依赖以唯一已安装提供者解析。控制面及基础设施由宿主拥有，业务状态可通过独立管理入口查询。

## 基础插件目录

| 宿主 | 插件 ID | 能力 |
| --- | --- | --- |
| ai-agent | agent.environment | Redis、数据库和人物资源 |
| ai-agent | models | 模型策略与创建工厂 |
| ai-agent | memory | 记忆、关系、表情 |
| ai-agent | speech.clients | 语音调用适配器工厂 |
| ai-agent | agent | 对话、私聊、群聊、主动联系与人物运行时 |
| gateway | channels | 平台渠道工厂 |
| gateway | gateway | 平台连接、消息归一化与投递 |
| gptsovits | speech.engines | 语音引擎工厂 |
| gptsovits | speech.server | HTTP / NATS 语音服务 |
| extension-host | tools | 工具发现、授权与调用 |
| mcp | mcp.server | MCP HTTP 服务 |
| mcp | music | 音乐指令记录 |
| mcp | weather | 天气工具 |
| mcp | web-search | 网络搜索 |
| director | director | 直播导演与调度 |
| live-edge | avatar | 形象事件 |
| live-edge | stream | 推流事件 |

具体供应商由工厂插件注册。交付能力以此目录和[验证结果](plugin-validation.md)为准；[独立包架构规格](../specs/002-plugin-architecture/spec.md)描述更完整的目标。

## 运行与管理契约

```powershell
$env:AILOVE_BUS_URL = 'nats://127.0.0.1:4222'
$env:AILOVE_PLUGIN_STATE_DIR = 'data/plugins'
python -m plugin_runtime --role live-edge
```

其他角色为 gateway、ai-agent、gptsovits、extension-host、mcp、director。同一 NATS 环境中，每种角色有一个活动宿主；管理后端使用相同总线地址和凭据。

管理页提供真实状态、依赖、在途回调、操作记录和影响范围。级联停用由显式依赖范围决定。操作 ID 的重复请求对应同一持久结果。

清单 `enabled` 决定首次启动意图，运行状态以持久记录为准。新增目录项的初始状态为 `uninstalled`，业务代码执行资格由安装和启用状态决定。

`install` 登记本地已交付插件；`remove` 的结果保留交付文件、操作历史和业务数据。交付方式为宿主可导入路径中的本地受信任代码。Docker、Compose、Kubernetes 使用统一插件入口、状态卷和控制连接。

## 状态与资源结果

`active` 表示声明能力已完整导出；停止完成表示业务入口闭合、在途工作排空且实例资源释放。控制阶段预算为 30 秒，排空预算为 60 秒。`failed` 保留实例所有权与资源诊断，重试资格由实际状态决定。

单宿主变更采用串行控制。重启后期望状态和操作历史保留，中断操作记录为 `interrupted`。级联操作的结果包含每个插件的实际状态。

MCP 工具目录与工具网关同步，新对话使用最新工具图，当前回合持有自身快照；执行授权以实际活动工具和当前权限为准。普通对话与本地工具具有独立能力边界。

## 插件示例

交付示例位于 `examples/plugin_echo.py` 和 `examples/plugin-catalog/echo/plugin.json`。

```powershell
$env:AILOVE_PLUGIN_PATH = (Resolve-Path 'examples/plugin-catalog').Path
python -m plugin_runtime --role live-edge
```

`--catalog` 可重复指定，显式目录替代内置目录；`AILOVE_PLUGIN_PATH` 追加目录，Windows 使用分号，Linux 使用冒号。每个 entrypoint 位于宿主可导入路径。

```python
from plugin_runtime import Plugin
from plugin_runtime.adapters import ScopedBus

class EchoPlugin(Plugin):
    async def start(self):
        bus = ScopedBus(self.context.ports['bus'], self.context.resources)
        await bus.reply('example.echo', self.echo)
        self.context.provide('example.echo', self)

    async def echo(self, payload):
        return payload
```

`resources.spawn()` 对应托管任务，`defer()` 对应最终清理，`on_quiesce()` 对应入口闭合，`guard()` 对应受管异步回调。资源契约覆盖部分初始化和重复清理。

## 能力范围

- 进程内插件的信任范围为已审核 Python 代码，资源作用域提供生命周期管理。
- 模块发现、安装、启停、移除和实例重建适用于运行中的宿主；已导入代码的替换生效方式为宿主重启。
- 依赖图属于单宿主；跨宿主调用采用 NATS / HTTP 契约。
- 文件锁的作用域为共用本地状态目录的进程，状态目录具有持久化要求。
- 外部动作的确认依据为平台结果；`unknown` 保留定位资料和核实入口。

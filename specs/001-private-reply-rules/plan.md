# Implementation Plan: 私聊必回复、主动联系限额与引用目标修正

**Branch**: `main` | **Date**: 2026-09-10 | **Spec**: [spec.md](spec.md)

**Input**: `specs/001-private-reply-rules/spec.md`

## Summary

保障已接收有效私信的非空回应；主动联系最多连续 3 次未获回复，间隔默认 30 分钟，新私信清零；带引用消息 A 的正常回复引用 A。

保留现有 Python 服务、PostgreSQL、NATS 和群聊流程。新增私聊处理记录与发送结果记录，使用现有数据库提供去重和恢复，NATS 作为快速唤醒；主动计数独立持久化，不改变群聊使用的 Redis SessionManager。仅在既有边界插入必要状态，不引入新服务、通用工作流引擎或新的消息基础设施。

## Technical Context

**Language/Version**: Python >=3.11，按 pyproject.toml；开发环境 PowerShell，运行环境沿用现有服务部署。

**Primary Dependencies**: 仓库 requirements.txt 固定版本的 SQLAlchemy async、asyncpg、Alembic、Pydantic、nats-py、Redis、httpx、LangChain；不升级依赖。

**Storage**: 现有 PostgreSQL 保存私信任务、主动状态、发送结果；Redis 继续承担既有群聊临时状态。新增表使用现有 ORM 与 Alembic。

**Testing**: pytest / unittest.IsolatedAsyncioTestCase；真实 PostgreSQL 事务验证并发与重启；平台、模型采用本地受控替身，单独报告模拟边界。

**Target Platform**: 现有单 QQ 账号，经 Gateway 与 ai-agent；不改直播、空间或游戏。

**Project Type**: 事件驱动多进程服务，Memory 仍在 ai-agent 内。

**Performance Goals**: 隔离环境 10 会话、1 条/秒、600 条；模型 <=2 秒、发送 <=1 秒时 P95 回应 <=10 秒，回应归属 100%，错误/重复/超发为 0。单会话按接收序排队，不将无限积压套用此延迟目标。

**Constraints**: 已确认状态普通重启 RPO=0；依赖恢复后 60 秒内恢复安全待处理任务或显式呈现待核实。平台无幂等发送能力，不能承诺跨平台事务的 exactly-once。发送未知不自动重放。

**Scale/Scope**: 3 个故事；3 张小型业务状态表；现有联系人、消息和账号身份复用。正常文本消息模型调用数不增加，异常采用无模型文字兜底。

## Constitution Check

研究前与设计后均通过以下设计检查；通过不表示实现已验收。

| 条款 | 设计约束与检查结果 |
| --- | --- |
| 持续身份与人格 | 不修改人设；按本次用户要求收窄有效私聊沉默为文字拒绝或澄清，群聊仍可沉默。 |
| 有依据的记忆 | 重复投递不重复触发关系/记忆；不重放可能已执行工具的生成轮次；不改既有记忆流水线。 |
| 多人关系与场景 | 当前消息和历史引用分离；额度以 ai_id + person_id 隔离，路由来自可信完整身份记录；私聊内容不跨场景泄露。 |
| 行动反馈闭环 | prepared/sending/sent/failed/unknown 区分明确；未知发送冻结，禁止自动重发。 |
| 清晰边界与生产保障 | Gateway 管准入、协议和发送结果；Agent 管回应与联系决策；shared 只放跨进程持久契约。无新服务。 |
| 真实调用链 | 验证平台入口→Gateway→Agent→发送；补真实数据库并发与恢复，不用直接调用内部函数冒充复现。 |
| 运维与外部写入 | 仅本地设计；迁移、监测、恢复、回滚见下文，上线与真实发信另需明确授权。 |

当前实现差距已在 research.md 记录，包括准入执行位置、处理去重与发送确认。不存在未解释的宪章例外。

## Project Structure

### Documentation (this feature)

```text
specs/001-private-reply-rules/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/social-reply.md
├── tasks.md
├── validation.md
├── operations.md
└── checklists/requirements.md
```

任务清单、验证记录和运维手册已随实现维护。

### Source Code (repository root)

```text
gateway/
  gateway_message_handler.py       # 私信准入、先保存后增强、唤醒
  social_send_handler.py           # 固定 run_id 的发送状态与结果查询
  qq_channel.py                   # 引用标识保留、补全失败降级、发送结果分类
  gateway_service.py              # 注入仓库、恢复任务、查询处理器
agent/
  ai_agent_service.py              # 恢复扫描与仓库注入
  ai_runtime.py                   # 领取私信、串行完成与生命周期
  social/social_message_handler.py # 必回应和附属功能降级
  social/proactive_private_service.py # 资格判断、预占、提交结果
  social/private_reply_service.py  # 私信任务恢复与兜底
shared/
  database_models.py
  private_interaction_repository.py # 私信和主动状态事务
  social_delivery_repository.py    # Gateway发送结果
  private_reply_observability.py   # 低基数指标和告警日志
  conversation_repository.py
  relationship_repository.py      # 完整可信候选身份选择
  contracts/turn.py
  contracts/rpc/social.py
  contracts/agent.py
  service_settings.py
alembic/versions/                  # 下一可用序号的增量迁移
deploy/nacos/                    # 现有默认配置与服务配置
tests/                           # 既有回归与新增入口/数据库集成测试
```

**Structure Decision**: 在现有职责内增加少量专用模块；不修改所有社交场景共用的 SessionManager 语义。

## Phase 0：研究结论

详见 [research.md](research.md)。未知项已作出可实施决策：PostgreSQL 作为可靠状态来源；NATS 唤醒可重复/可丢但任务不丢；未知发送需要核实；历史主动次数无法重建时保守暂停；30 分钟冷却、6 小时安静期及作息同时保留。

setup-plan.ps1 返回逻辑特性名 `001-private-reply-rules` 作为 BRANCH；`git branch --show-current` 实际是 `main`，脚本没有切换分支。本计划据实际 Git 状态记录。

## Phase 1：实施设计

### 1. 接收、去重与有序恢复

在 Gateway 的私信分支排除自身回流与无平台消息编号等无效事件，解析必要身份、会话与 AI 归属后，先事务保存完整归一化 SocialMessage 快照和固定 run_id。唯一输入键包括平台、账号、会话及平台消息编号；AI 归属固定为首次接收值，账号换绑后的重投仍返回旧任务，不作为新消息。旧 AI 已停用时显式暂停旧任务，不由新 AI 擅自重放。首次插入与主动计数清零在同一事务执行，重复事件返回既有任务，不重新清零、不重复更新关系。

QQ 白名单继续作为优先联系人和关系上限标记，不作为私信准入拦截。无消息编号的协议无效输入不进入可靠任务，记录可定位拒绝原因。

保存后再执行引用补全与实体增强；补全失败保留当前消息，增强失败标记只允许安全澄清，不绕过身份或工具授权。Gateway 每 5 秒限量恢复 accepted 任务；准备完成转 ready。NATS 原主题仅唤醒，Agent 每 5 秒扫描 ready，故提交后发布失败可恢复，不新增 JetStream 消费体系。

同会话以数据库接收序号领取最早任务，状态比较更新防止重复领取，沿用进程内会话锁；同会话后续任务不能越过尚在处理的前项。单次扫描最多 100 条、最多 10 个会话并发，超过部分保留数据库排队。claimed 任务使用 120 秒租约及 15 秒心跳；租约仅用于发现失联，不授权旧 worker 提交或发送，所有提交须匹配领取版本。

中断后若已准备发送，复用原内容与 run_id；若生成/工具执行状态不明确，不重新执行整个代理轮次，而生成无工具故障说明。如此避免恢复导致重复工具副作用。unknown 任务显式结束自动处理并告警，不永久挡住后续有效私信。

### 2. 非空回应与有限降级

保持私聊固定响应决策；生成异常、空白输出、输入理解失败使用配置中的短文字兜底，不额外请求模型。已有模型故障切换保留，总处理预算 45 秒，预算内遵守既有提供方顺序；超时后取消生成，禁止迟到结果再次发送。表情、语音、记忆检索等附属路径失败时优先保留已生成文字，记忆失败不得伪造记忆；关系与记忆附属写入失败不把已送达回复改为未发送。

每条私信只持久保存一个最终发送内容。不可用的语音临时文件仅在尚未创建 SocialDelivery 且从未开始发送时，原子更新 prepared 任务为保存的文字；已有发送记录保持原摘要，无法安全恢复则明确失败，不改内容重发。不能用一次笼统 catch 将“发送已发生”与“生成尚未发送”混为一谈。

### 3. Gateway 发送结果

按 (ai_id, account_id, run_id) 保存不可变目标与内容摘要。首次调用创建 prepared，在同一短事务锁定发送记录及来源任务/主动状态，复核领取版本或有效预占后原子变为 sending，再调用平台；相同键不同目标/内容拒绝，相同键已 sent 返回原 message_id，sending/unknown 不再次调用平台。

平台成功后先记录确认，再补 outbound 会话历史；后续入库或 RPC 返回失败可查询原结果并补写历史，不再发送。发送前明确校验失败标记 failed；网络超时、断连及发送后崩溃无法判断则 unknown。自动恢复只重试确定未发送的安全失败，最多 2 次（5、15 秒），使用相同内容与 run_id；平台业务拒绝、越权、未知结果不重试。已确认“引用目标不可用且未发送”可移除引用后重试一次，结果未知不能降级重发。

新增只读结果查询 RPC，详见 contracts/social-reply.md。当前 QQ 无按客户端操作编号查历史的能力；无 message_id 的 unknown 只能保持待核实并通过受控人工处理，不猜测、不自动释放主动预占。后续新私信可正常回应。

### 4. 主动次数与发送竞争

单独使用持久主动状态 (ai_id, person_id)，上限固定 3；冷却使用已有 private_cooldown_sec，默认从 43200 改 1800，不添加可放宽上限的配置。

联系人身份从一条完整、可信、当前 AI 绑定的 QQ 身份中选择 account/user/person；避免两个独立子查询拼接路由。白名单只参与既有优先级排序和关系上限，不限制已建立关系的可信联系人。不建立新的身份合并机制。

在生成前检查资格；生成后、发送前在短事务内重新检查额度、作息、安静期、冷却和用户回复版本，预占唯一 run_id。事务内不调用模型或平台。空生成不占额度。发送确认与状态提交按数据模型执行；未发出的旧话题遇到用户新私信则取消主动发送。已在发送中的操作与用户回复交错但先后无法证明时，保持待核实并暂停主动联系，不凭 ACK 时间猜测；被动回复不受影响。

### 5. 引用目标

保留 quote_ref 用于历史上下文。QQ 解析保留原始引用存在标记/编号（不能在 hydrate pop 后丢失），执行上下文在当前消息带引用时设置 reply_to_message_id = 当前 message_id。即使历史补全失败仍适用。无引用输入、主动消息及群复读维持原展示规则。仅平台明确拒绝引用且确认未发送时安全退化为普通回应。

## 迁移、观测与发布验收

- 用下一可用 Alembic revision 新建 3 表和索引，不更改长期记忆与人物关系内容；ORM 唯一约束及状态范围校验即可，不增加重复参数校验。
- 旧 Redis 数据和历史 outbound 无法可靠重建主动次数。升级前关闭主动开关，现有联系人建立 suspended 状态，首次新有效私信初始化为 0。可信新建联系人可初始化 0；普通状态缺失不能当作新联系人。旧 Redis key 不清空，群聊继续使用。
- 迁移验证使用隔离数据库，测试旧数据升级、进程重启、备份恢复及反复运行不重置额度。已确认状态普通重启 RPO=0；灾难备份恢复可能落后时统一暂停主动，重新核实后恢复，不假定备份包含最新额度。
- 新增结构化事件包含 run_id、输入键、会话、ai_id、person_id、状态、计数、耗时与原因，不记录凭据和无关正文。指标覆盖 pending 年龄/数量、回复覆盖率、fallback、unknown、超发阻止、模型调用数。
- pending 超过 60 秒、任意 unknown、连续 3 次发送失败或恢复扫描失败触发现有可观测设施的告警；排查顺序为依赖健康→任务/发送状态→权威送达凭证→安全恢复。数据库不可用时停止接收成功确认并告警，不谎称已经可靠接收。
- SC-004 负载按均匀轮转 10 会话执行；测量接收到确认耗时，报告 P95、覆盖率、错误率与调用数。故障场景单独测试，不以平均值掩盖漏回。
- 成本沿用当前模型及已记录 token 使用量，普通文本调用数比值 <=1；异常兜底新增模型调用数为 0。真实货币成本由部署负责人提供当时模型单价，按输入/输出 token 逐项核算；未取得计价数据不得声称成本验收完成。
- 发布顺序：停主动与入口→备份→增量迁移→Gateway/Agent 同版本更新→配置校验→隔离验证→另获授权后真实验证。RpcModel 禁止未知字段，不能假定新旧版本混跑兼容。
- 回滚先停主动和新任务领取，保留新表和未知记录，导出未完成任务清单，在旧代码下保持主动关闭；不得通过 downgrade 删除状态以恢复服务。回滚旧版不再保证本特性，须显式提示运维。

## Complexity Tracking

无未获依据的宪章偏离。3 张专用表分别承担接收恢复、主动额度与平台发送结果，都是当前验收所需；不新增通用任务平台、分布式事务或数据库外的第二份权威计数。


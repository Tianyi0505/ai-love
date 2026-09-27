# 本地验证指南

本指南用于验证已实现的私聊可靠回复。数据结构见 [data-model.md](data-model.md)，接口见 [contracts/social-reply.md](contracts/social-reply.md)，升级与故障处置见 [operations.md](operations.md)。所有自动化测试使用本地替身，不发送真实 QQ 消息。

## 前提

在仓库根目录使用已有 Python >=3.11 虚拟环境。测试使用本地平台/模型替身，禁止连接生产账号；数据库事务测试需要专用可丢弃 PostgreSQL 测试库，由测试夹具明确拒绝非测试目标。不要复用生产 DATABASE URL，不在命令输出中展示凭据。

```powershell
Set-Location -LiteralPath 'D:\ai-love'
& 'D:\ai-love\.venv\Scripts\python.exe' --version
& 'D:\ai-love\.venv\Scripts\python.exe' -m pytest --version
```

测试库连接通过 `AILOVE_TEST_DATABASE_URL` 注入，夹具据此创建并清理隔离 schema，正常路径不依赖真实 Nacos/NapCat。完整 Alembic 迁移应使用带 pgvector 的独立测试库另行演练。

## 既有回归

以下文件当前存在，可在实施后执行：

```powershell
& 'D:\ai-love\.venv\Scripts\python.exe' -m pytest tests/test_agent_runtime.py tests/test_gateway_message_handler.py tests/test_proactive_private_service.py tests/test_model_failover.py tests/test_group_repeat.py tests/test_group_message_json.py tests/test_qq_emoticons.py -q
```

更新仅断言旧 43200 秒冷却或旧主动 SessionManager 的测试，保留其有价值的行为覆盖；不把所有旧断言删除来得到通过结果。

## 入口验收

执行以下已实现的入口、状态、发送、引用和观测测试：

```powershell
& 'D:\ai-love\.venv\Scripts\python.exe' -m pytest tests/test_private_reply_flow.py tests/test_private_contact_persistence.py tests/test_social_delivery_recovery.py tests/test_social_quote_reply.py tests/test_private_reply_observability.py -q
```

| 场景 | 真实入口与故障控制 | 通过条件 |
| --- | --- | --- |
| 必回复 | 平台格式事件→QQ转换→Gateway→Agent→Gateway发送替身 | 工作内外、关系低、额度满、连续消息均非空回应，每个独立输入可关联 |
| 理解/生成/附属失败 | 替身返回合法空计划，或输入增强、模型、表情/TTS异常 | 已生成文字保留，必要时文字兜底；零额外兜底模型调用 |
| 去重与断连 | 相同平台事件重投；数据库提交后丢弃 NATS 唤醒 | 一个任务、一轮回应、一次重置；扫描恢复且不重放工具 |
| 主动上限 | run_once 推进受控时钟与真实状态，渠道记录请求 | 同日第2/3次发送，第4次阻止，30分钟冷却和6小时安静期各自生效 |
| 清零边界 | 私信入口接收新消息；重投旧消息、群消息、其他用户 | 仅新的对应私信清零；被动回复不消耗主动额度 |
| 并发 | 两个独立仓库连接竞争最后额度与领取版本 | 无超发、无旧worker外发、同会话有序 |
| 重启与迁移 | 复用测试数据库重建服务，清除临时Redis；导入旧联系人 | 次数不丢，旧联系人暂停；首次新私信解除初始化暂停 |
| 发送确认丢失 | 平台确认后使历史写入或RPC返回失败 | 查原run_id恢复message_id，不重复外发，历史可补记 |
| 发送结果未知 | 发送后无响应并重启Gateway，或入站与sending交错无法证明顺序 | 标记unknown、冻结主动、无自动重发；后续私信仍获回应 |
| 引用 | A引用B，B引用C，B缺失/补全失败，多会话并发 | 实际发送reply段为A；无引用与群复读行为不变 |
| 准入 | 白名单外、自身事件、无合法消息编号 | 不进入有效任务，不消耗模型或扩大权限 |

并发、唯一键和恢复测试必须使用真实 PostgreSQL，不能全用 AsyncMock 替代 SessionManager 后宣称状态正确。平台及模型始终是本地替身，报告时注明。

## 负载与预算

`tests/test_private_reply_load.py` 通过端到端夹具均匀轮转 10 会话，以 1 条/秒持续 600 秒；模型与平台均使用本地替身。该长测试默认跳过，必须显式启用：

```powershell
$env:AILOVE_RUN_PRIVATE_REPLY_LOAD = '1'
& 'D:\ai-love\.venv\Scripts\python.exe' -m pytest tests/test_private_reply_load.py -q -s
```

要求 600 条全部有回应归属，P95 <=10 秒，错误/重复/超发=0。单独注入故障验证 60 秒内有明确失败或待恢复状态；45 秒生成预算结束后不接受迟到结果。与变更前同样普通文本样本比较，模型调用比值 <=1；货币费用按届时提供方实际单价与token量计算，不能用模拟耗时推断线上成本。

## 恢复与回滚演练

1. 测试库迁移前备份；迁移后现有联系人、人物记忆和关系数据保持原值。
2. 在 accepted、processing、prepared、sending、sent 后逐点停止测试进程并重启，验证安全阶段恢复；sending 不因租约到期变成未发送。
3. 将已确认主动状态备份恢复到另一隔离 schema，核对计数；备份可能落后则主动暂停，不自动清零。
4. 回滚模拟只退应用代码，不删除新增表；保持主动关闭，输出未完成与未知任务清单。
5. pending超过60秒、unknown和恢复扫描失败应能从结构化日志/指标定位输入和run_id，不含凭据或无关正文。

真实部署、真实平台发信与外部写入均不属于本指南的本地执行授权；上线阶段需另有明确请求。

# 私聊本地验收入口与结果

本地环境使用 Python 3.11、环回测试 PostgreSQL 和平台/模型替身。`AILOVE_TEST_DATABASE_URL` 指向名称以 `_test` 结尾的专用数据库，夹具提供隔离 schema。完整迁移环境包含 pgvector。

## 验收入口

```bash
python -m pytest tests/test_private_reply_flow.py tests/test_private_contact_persistence.py tests/test_social_delivery_recovery.py tests/test_social_quote_reply.py tests/test_private_reply_observability.py -q
```

既有 Gateway、Agent、群聊、模型备用路径和 QQ 内容解析具有相应回归项目。

| 场景 | 通过标准 |
| --- | --- |
| 有效私信 | 全时段及各关系状态具有可感知回应 |
| 理解与生成状态 | 合法文字或澄清，兜底额外模型调用数为 0 |
| 去重与恢复 | 一个任务、稳定 run_id、唯一正常回应及扫描恢复结果 |
| 主动轮次 | 最多 3 次成功联系，新有效私信具有清零依据 |
| 冷却与作息 | 30 分钟间隔、6 小时静默及工作时段同时适用 |
| 并发与持久化 | 最后额度具有唯一预占，重启保留计数 |
| 发送凭证 | 平台编号和历史记录可由原 run_id 关联 |
| unknown | 独立核实状态及新的被动回应资格 |
| 引用 | 出站目标为当前 A，历史 B 保留归属 |
| 保留期 | 最小去重凭证、额度与 unknown 定位资料保留 |

## 负载目标

`tests/test_private_reply_load.py` 的启用条件为 `AILOVE_RUN_PRIVATE_REPLY_LOAD=1`。10 会话均匀分配每秒 1 条消息，持续 600 秒；600 条具有完整回应归属，P95 ≤10 秒，模型调用比值 ≤1。平台和模型为本地替身，持久竞争使用真实 PostgreSQL。

恢复验收覆盖各状态、隔离备份库和三张持久表。协议见 [social-reply.md](contracts/social-reply.md)，实测见 [validation.md](validation.md)。生产写入属于相应用户授权范围。
